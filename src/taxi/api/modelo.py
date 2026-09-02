"""Carga del modelo desde el Model Registry, encapsulada y perezosa.

Problema que resuelve. La forma intuitiva de llevar un modelo a un servicio es
un script `copy_model.py` que haga ``shutil.copytree`` del directorio de un run
de MLflow hacia ``deploy/web-service/model/``, con un ``COPY model/`` en el
Dockerfile. Funciona el primer dia y despues:

- El artefacto queda versionado por el sistema de archivos, no por el registry.
  Nadie puede decir que version sirve un contenedor en produccion.
- Cambiar de modelo exige reconstruir la imagen.
- El `run_id` de origen acaba hardcodeado, asi que el paso solo funciona en la
  maquina donde se genero ese run.
- Todo el linaje que la sesion de tracking ensena a construir se pierde en el
  `copytree`.

La forma correcta es referirse al modelo por **alias del registry**
(``models:/<nombre>@champion``): una referencia mutable que el gate de promocion
mueve. La imagen no contiene el modelo; contiene el codigo que sabe pedirlo.

Tres decisiones de diseno:

1. **Carga perezosa e idempotente.** ``cargar()`` se puede llamar N veces y solo
   golpea el registry la primera. El lifespan la llama al arrancar para que el
   primer request no pague la descarga (cold start), pero el endpoint tambien
   puede llamarla sin riesgo.
2. **Arranque degradado permitido.** Con ``TAXI_MODELO_URI=ninguno`` el servicio
   levanta sin modelo. Eso permite verificar la imagen en CI —que responda
   `/health`, que no corra como root— sin levantar un registry. Si la URI es
   valida pero la carga falla, tambien se arranca degradado: se registra el error
   y `/health` lo reporta. La alternativa (abortar el arranque) provoca un
   CrashLoopBackOff donde nadie puede consultar el diagnostico.
3. **El cargador de pyfunc es inyectable.** Es la costura que permite testear la
   API con un modelo falso sin montar MLflow. No es un truco para tests: es la
   misma costura que se usa para conectar otro backend de modelos.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import pandas as pd

from taxi.api.schemas import ViajeRequest
from taxi.config import ALIAS_PRODUCCION, MODELO_REGRESION, uri_modelo
from taxi.features.contract import (
    COL_DROPOFF,
    COL_PICKUP,
    a_diccionarios,
    construir_features,
)

logger = logging.getLogger(__name__)

#: Valor centinela de ``TAXI_MODELO_URI`` para arrancar sin modelo.
URI_SIN_MODELO: Final[str] = "ninguno"

#: Valor que se reporta cuando la version no se pudo resolver. Se prefiere una
#: cadena explicita antes que None o "": en Prometheus el label vacio se
#: confunde con "metrica sin etiquetar" y en un dashboard eso es un rato perdido.
VERSION_DESCONOCIDA: Final[str] = "desconocida"

#: ``models:/<nombre>@<alias>`` — referencia MUTABLE. Es la que se usa en
#: produccion: el gate de promocion mueve el alias y el servicio recoge el nuevo
#: modelo al reiniciar, sin rebuild.
_RE_ALIAS = re.compile(r"^models:/(?P<nombre>[^/@]+)@(?P<alias>[^/@]+)$")
#: ``models:/<nombre>/<numero>`` — referencia INMUTABLE. Util cuando se necesita
#: reproducir exactamente lo que sirvio un contenedor historico.
_RE_VERSION = re.compile(r"^models:/(?P<nombre>[^/@]+)/(?P<version>\d+)$")

CargadorPyfunc = Callable[[str], Any]


@dataclass(frozen=True)
class MetadatosModelo:
    """Identidad del modelo que esta sirviendo el proceso."""

    nombre: str
    version: str
    uri: str


def _cargar_pyfunc(uri: str) -> Any:
    """Envoltura fina sobre ``mlflow.pyfunc.load_model``.

    El import de mlflow ocurre aqui, no a nivel de modulo, por dos razones:
    importar mlflow cuesta cientos de milisegundos y arrastra sqlalchemy, y con
    ``TAXI_MODELO_URI=ninguno`` no hace falta pagarlo. El arranque del contenedor
    en CI es medible mas rapido por esto.
    """
    import mlflow.pyfunc

    return mlflow.pyfunc.load_model(uri)


def _resolver_identidad(uri: str) -> tuple[str, str]:
    """Deduce (nombre, version) a partir de la URI del modelo.

    Con una URI por version el dato esta en la propia cadena. Con una URI por
    alias hay que preguntarle al registry cual version apunta el alias **en este
    momento**; es exactamente esa indireccion la que hace util al alias, y
    tambien la que obliga a resolverla y guardarla: si no se registra, en el log
    queda "champion" y no se sabe que artefacto respondio.
    """
    if (m := _RE_VERSION.match(uri)) is not None:
        return m.group("nombre"), m.group("version")

    if (m := _RE_ALIAS.match(uri)) is not None:
        nombre, alias = m.group("nombre"), m.group("alias")
        try:
            from mlflow import MlflowClient

            mv = MlflowClient().get_model_version_by_alias(nombre, alias)
            return nombre, str(mv.version)
        except Exception:
            # No se aborta: el modelo ya se cargo y puede servir. Solo se pierde
            # el numero exacto de version, y eso se reporta como tal.
            logger.warning(
                "No se pudo resolver la version del alias '%s' en el registry; "
                "se sirve el modelo con version=%s",
                alias,
                VERSION_DESCONOCIDA,
                exc_info=True,
            )
            return nombre, VERSION_DESCONOCIDA

    # URIs de tipo runs:/, s3://, file:// o rutas locales. Son validas para
    # depurar, pero no son auditables: no hay nombre ni version de registry.
    logger.warning(
        "La URI '%s' no referencia el Model Registry. Funciona, pero la "
        "prediccion no queda atribuible a una version registrada.",
        uri,
    )
    return MODELO_REGRESION, VERSION_DESCONOCIDA


class CargadorModelo:
    """Encapsula el ciclo de vida del modelo servido.

    Toda la API habla con esta clase y nunca con mlflow directamente. Eso deja un
    solo punto donde cambiar la estrategia de carga (otro registry, cache en
    disco, recarga en caliente) sin tocar los endpoints.
    """

    def __init__(
        self,
        uri: str | None = None,
        *,
        cargar_pyfunc: CargadorPyfunc | None = None,
    ) -> None:
        """
        Args:
            uri: URI del modelo. Si es None se lee de ``TAXI_MODELO_URI`` y, si
                tampoco esta, se usa el alias de produccion de ``config.py``.
            cargar_pyfunc: funcion que recibe la URI y devuelve algo con
                ``.predict``. Inyectable para tests y para backends alternativos.
        """
        self._uri: str = uri if uri is not None else os.getenv("TAXI_MODELO_URI", uri_modelo())
        self._cargar_pyfunc: CargadorPyfunc = cargar_pyfunc or _cargar_pyfunc
        self._modelo: Any | None = None
        self._metadatos: MetadatosModelo | None = None
        self._error: str | None = None

    # -- Estado ---------------------------------------------------------------
    @property
    def uri(self) -> str:
        """URI configurada, tal cual se pidio."""
        return self._uri

    @property
    def habilitado(self) -> bool:
        """False cuando se pidio explicitamente arrancar sin modelo."""
        return self._uri.strip().lower() != URI_SIN_MODELO

    @property
    def cargado(self) -> bool:
        """True solo si hay un modelo listo para predecir."""
        return self._modelo is not None

    @property
    def metadatos(self) -> MetadatosModelo | None:
        """Identidad del modelo cargado, o None si no hay modelo."""
        return self._metadatos

    @property
    def error(self) -> str | None:
        """Motivo por el que no hay modelo, si aplica. Uso interno / logs."""
        return self._error

    # -- Ciclo de vida --------------------------------------------------------
    def cargar(self) -> bool:
        """Carga el modelo si hace falta. Idempotente.

        Returns:
            True si al terminar hay un modelo servible.
        """
        if self._modelo is not None:
            return True

        if not self.habilitado:
            self._error = f"TAXI_MODELO_URI={URI_SIN_MODELO}"
            logger.warning(
                "Arranque SIN modelo (TAXI_MODELO_URI=%s). /health respondera "
                "model_loaded=false y /predict devolvera 503. Este modo existe "
                "para verificar la imagen sin depender del registry.",
                URI_SIN_MODELO,
            )
            return False

        logger.info("Cargando modelo desde %s", self._uri)
        try:
            modelo = self._cargar_pyfunc(self._uri)
        except Exception as exc:
            # Se guarda el tipo, no el texto: el texto puede traer credenciales
            # de la cadena de conexion del registry y este valor se expone en
            # logs y metricas.
            self._error = type(exc).__name__
            logger.exception("Fallo la carga del modelo desde %s; se arranca degradado", self._uri)
            return False

        nombre, version = _resolver_identidad(self._uri)
        self._modelo = modelo
        self._metadatos = MetadatosModelo(nombre=nombre, version=version, uri=self._uri)
        self._error = None
        logger.info(
            "Modelo cargado: uri=%s nombre=%s version=%s",
            self._uri,
            nombre,
            version,
        )
        return True

    # -- Inferencia -----------------------------------------------------------
    def predecir(self, registros: Sequence[dict[str, Any]]) -> list[float]:
        """Ejecuta la inferencia sobre registros ya en formato de features.

        Recibe la salida de ``taxi.features.contract.a_diccionarios``, que es el
        formato que espera el ``DictVectorizer`` del pipeline entrenado. La API
        no construye features por su cuenta: reusa el contrato. Ese reuso es lo
        que evita el training/serving skew, y es la correccion directa del
        anti-patron donde la API armaba ``{'PU_DO': ..., 'trip_distance': ...}``
        a mano y se olvidaba de `hora_pickup` y `dia_semana_pickup`, dos features
        con las que el modelo si habia sido entrenado.

        Raises:
            RuntimeError: si no hay modelo cargado. El endpoint lo traduce a 503.
        """
        if self._modelo is None:
            raise RuntimeError("No hay modelo cargado")

        crudas = self._modelo.predict(list(registros))
        # pyfunc devuelve ndarray, Series, DataFrame o lista segun el flavor del
        # modelo registrado. Se normaliza en un solo sitio para que el resto de la
        # API vea siempre list[float] y no dependa de que flavor gano el gate.
        if hasattr(crudas, "tolist"):
            crudas = crudas.tolist()
        return [float(v) for v in crudas]


# =============================================================================
# Adaptador request -> features del modelo
# =============================================================================
def construir_registros(viajes: Sequence[ViajeRequest]) -> list[dict[str, Any]]:
    """Traduce requests validados al formato que consume el modelo.

    Reusa ``taxi.features.contract`` en lugar de reimplementar las derivaciones.
    Es la decision mas importante de este modulo: el training/serving skew casi
    nunca viene de un bug en el modelo, viene de dos implementaciones distintas
    de la misma feature. Aqui hay una sola.

    Sobre el centinela de dropoff. ``COLUMNAS_CRUDAS_REQUERIDAS`` incluye
    ``lpep_dropoff_datetime`` porque el pipeline de entrenamiento necesita las dos
    puntas para derivar ``duration``. En inferencia el dropoff **es** lo que se
    quiere predecir: por definicion no existe. Se rellena con el pickup para
    satisfacer el contrato compartido, y es seguro porque ninguna feature lo usa
    (``construir_features`` solo lee el pickup para la hora y el dia). La
    alternativa —partir el contrato en "columnas de entrenamiento" y "columnas de
    inferencia"— es mas limpia conceptualmente y es lo que hace un feature store;
    para un curso, un contrato unico con este comentario explicito ensena mas.

    Costo: se construye un DataFrame por request. Son decenas de microsegundos,
    despreciables frente a la inferencia, y es el precio de tener una sola
    definicion de features. Si algun dia dominara el perfil, la respuesta correcta
    es un transformador compartido vectorizado, no duplicar la logica en la API.
    """
    filas: list[dict[str, Any]] = []
    for viaje in viajes:
        # Se resuelve UNA vez por viaje: `pickup_efectivo()` puede devolver
        # `ahora`, y llamarlo dos veces daria dos timestamps distintos.
        pickup = viaje.pickup_efectivo()
        filas.append(
            {
                COL_PICKUP: pickup,
                COL_DROPOFF: pickup,  # centinela; ver docstring
                "PULocationID": viaje.PULocationID,
                "DOLocationID": viaje.DOLocationID,
                "trip_distance": viaje.trip_distance,
            }
        )
    return a_diccionarios(construir_features(pd.DataFrame(filas)))


# =============================================================================
# Instancia de proceso
# =============================================================================
# Un unico cargador por proceso: el modelo pesa y no tiene sentido duplicarlo por
# request. Se expone via funcion (y no como variable global importable) para
# poder sustituirlo con `app.dependency_overrides` en los tests, que es el
# mecanismo idiomatico de FastAPI y no requiere monkeypatch de modulos.
_cargador: CargadorModelo | None = None


def obtener_cargador() -> CargadorModelo:
    """Dependencia de FastAPI: devuelve el cargador del proceso."""
    global _cargador
    if _cargador is None:
        _cargador = CargadorModelo()
    return _cargador


def reiniciar_cargador(cargador: CargadorModelo | None = None) -> CargadorModelo | None:
    """Reemplaza el cargador del proceso.

    Se usa para aislar tests entre si y para forzar una recarga del modelo tras
    una promocion sin reiniciar el contenedor.
    """
    global _cargador
    _cargador = cargador
    return _cargador


def uri_por_defecto() -> str:
    """URI que se usaria si nadie configura nada. Solo para logs y `/modelo`."""
    return os.getenv("TAXI_MODELO_URI", uri_modelo(MODELO_REGRESION, ALIAS_PRODUCCION))
