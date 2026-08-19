"""Acceso al Model Registry de MLflow con aliases y tags.

Problema que resuelve
---------------------
Un modelo entrenado no sirve de nada si el resto del sistema no puede
referenciarlo sin ambiguedad. Hacen falta tres cosas que el filesystem no da:

1. Una **referencia estable** que apunte a "el modelo que atiende produccion
   hoy" sin que la API tenga que conocer el numero de version.
2. Un lugar donde escribir **por que** una version esta ahi (que gate paso, con
   que metricas, contra que holdout).
3. Un **rollback** que no requiera reentrenar ni redeployar.

Los aliases dan (1) y (3); los tags dan (2). El repo anterior resolvia esto
copiando directorios con ``shutil.copytree`` entre modulos, lo que destruia
toda la trazabilidad que el modulo de tracking acababa de ensenar a construir.

Este modulo es una capa delgada sobre ``MlflowClient``. No abstrae MLflow: lo
envuelve para que el nombre del alias, el del tag y el manejo de "todavia no
existe" esten en un solo lugar y no repetidos en el CLI, el gate, la API y el
notebook.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import mlflow
from mlflow.entities.model_registry import ModelVersion
from mlflow.environment_variables import (
    MLFLOW_HTTP_REQUEST_MAX_RETRIES,
    MLFLOW_HTTP_REQUEST_TIMEOUT,
)
from mlflow.exceptions import MlflowException, RestException
from mlflow.tracking import MlflowClient

from taxi import config

logger = logging.getLogger(__name__)


@contextmanager
def fallar_rapido(segundos: int = 3, reintentos: int = 1) -> Iterator[None]:
    """Reduce el timeout y los reintentos HTTP de MLflow dentro del bloque.

    Por defecto mlflow reintenta 7 veces con backoff exponencial y 120 s de
    timeout. Es un default razonable para un pipeline de produccion que quiere
    sobrevivir a un blip de red, y un default terrible para dos casos concretos
    del curso:

    - la model card en modo degradado, que debe emitirse en segundos cuando el
      server no esta levantado (medido: sin esto tarda varios minutos);
    - el gate en CI, donde un tracking server mal configurado colgaria el job en
      lugar de fallar con un mensaje.

    Un fallback que tarda cuatro minutos en activarse no es un fallback.

    Respeta la configuracion explicita del usuario: si las variables de entorno ya
    estan puestas, no se tocan.
    """
    deseados = {
        MLFLOW_HTTP_REQUEST_TIMEOUT.name: str(segundos),
        MLFLOW_HTTP_REQUEST_MAX_RETRIES.name: str(reintentos),
    }
    originales = {clave: os.environ.get(clave) for clave in deseados}
    for clave, valor in deseados.items():
        if originales[clave] is None:
            os.environ[clave] = valor
    try:
        yield
    finally:
        for clave, original in originales.items():
            if original is None:
                os.environ.pop(clave, None)


def cliente(tracking_uri: str | None = None) -> MlflowClient:
    """Devuelve un ``MlflowClient`` apuntado al tracking server del curso.

    Existe para que ningun otro modulo tenga que recordar el puerto 5001 ni
    leer la variable de entorno por su cuenta.
    """
    uri = tracking_uri or config.MLFLOW_TRACKING_URI
    return MlflowClient(tracking_uri=uri, registry_uri=uri)


def registrar_candidato(
    model_uri: str,
    nombre: str = config.MODELO_REGRESION,
    *,
    cliente_mlflow: MlflowClient | None = None,
    descripcion: str | None = None,
) -> ModelVersion:
    """Registra un run como nueva version del modelo y la marca como candidata.

    Registrar y promover son dos actos distintos, y separarlos es el punto
    conceptual: registrar dice "este artefacto existe y es trazable"; promover
    dice "este artefacto atiende trafico". Una version recien registrada recibe
    el alias ``candidate`` y el tag ``validation_status=pending``, de modo que
    nunca hay una version en el registry cuyo estado de validacion sea
    desconocido.

    Args:
        model_uri: URI del artefacto, tipicamente ``runs:/<run_id>/<name>``.
        nombre: nombre del modelo registrado.
        cliente_mlflow: cliente inyectable (facilita los tests).
        descripcion: texto libre para la version.

    Returns:
        La ``ModelVersion`` creada.
    """
    cli = cliente_mlflow or cliente()
    try:
        cli.create_registered_model(nombre)
        logger.info("Modelo registrado creado: %s", nombre)
    except (MlflowException, RestException):
        logger.debug("El modelo registrado %s ya existia", nombre)

    version = mlflow.register_model(model_uri=model_uri, name=nombre)
    numero = str(version.version)
    if descripcion:
        cli.update_model_version(name=nombre, version=numero, description=descripcion)

    asignar_alias(nombre, config.ALIAS_CANDIDATO, numero, cliente_mlflow=cli)
    marcar_validacion(nombre, numero, "pending", cliente_mlflow=cli)
    logger.info("Version %s de %s registrada como @%s", numero, nombre, config.ALIAS_CANDIDATO)
    return version


def asignar_alias(
    nombre: str,
    alias: str,
    version: str | int,
    *,
    cliente_mlflow: MlflowClient | None = None,
) -> None:
    """Apunta un alias a una version concreta.

    Un alias es una referencia **mutable** a una version **inmutable**. Mover el
    alias es la operacion de deploy y, en sentido inverso, la de rollback: no
    copia artefactos, no reentrena, no reconstruye la imagen. Es una escritura
    de metadatos que tarda menos de un segundo.

    Reemplaza al metodo de transicion de stages del cliente, deprecado desde
    MLflow 2.9.0 (ver ``docs/adr/002-aliases-en-vez-de-stages.md``).
    """
    cli = cliente_mlflow or cliente()
    cli.set_registered_model_alias(name=nombre, alias=alias, version=str(version))
    logger.info("Alias @%s de %s -> version %s", alias, nombre, version)


def quitar_alias(
    nombre: str,
    alias: str,
    *,
    cliente_mlflow: MlflowClient | None = None,
) -> None:
    """Elimina un alias.

    Util para retirar ``@candidate`` cuando el candidato ya fue promovido o
    rechazado, y para dejar de servir un modelo sin borrar su version (la
    version se conserva: es la evidencia de lo que estuvo en produccion).
    """
    cli = cliente_mlflow or cliente()
    cli.delete_registered_model_alias(name=nombre, alias=alias)
    logger.info("Alias @%s de %s eliminado", alias, nombre)


def version_por_alias(
    nombre: str,
    alias: str = config.ALIAS_PRODUCCION,
    *,
    cliente_mlflow: MlflowClient | None = None,
) -> ModelVersion | None:
    """Devuelve la version apuntada por el alias, o ``None`` si no existe.

    Devolver ``None`` en lugar de propagar la excepcion es deliberado: "todavia
    no hay champion" es un estado **normal** del sistema, no un error. Es el
    estado del primer dia, y el gate tiene que saber distinguirlo de un fallo de
    conexion. Un ``None`` obliga a quien llama a decidir que hacer.
    """
    cli = cliente_mlflow or cliente()
    try:
        return cli.get_model_version_by_alias(name=nombre, alias=alias)
    except (MlflowException, RestException) as exc:
        logger.info("No hay version con alias @%s en %s (%s)", alias, nombre, type(exc).__name__)
        return None


def ultima_version(
    nombre: str,
    *,
    cliente_mlflow: MlflowClient | None = None,
) -> ModelVersion | None:
    """Devuelve la version con el numero mas alto del modelo registrado.

    Se usa ``search_model_versions`` y no ``get_latest_versions``: el segundo
    esta deprecado porque su semantica dependia de los stages ("la ultima de
    cada stage"), un concepto que ya no existe.

    Nota didactica: "la ultima registrada" es un default de conveniencia para la
    clase. En un CD real el candidato se identifica explicitamente por su
    version o su run_id, porque dos pipelines concurrentes pueden registrar
    versiones y "la ultima" deja de ser deterministica.
    """
    cli = cliente_mlflow or cliente()
    try:
        versiones = cli.search_model_versions(f"name = '{nombre}'")
    except (MlflowException, RestException) as exc:
        logger.warning("No se pudo listar versiones de %s: %s", nombre, exc)
        return None
    if not versiones:
        return None
    return max(versiones, key=lambda v: int(v.version))


def marcar_validacion(
    nombre: str,
    version: str | int,
    estado: str,
    *,
    cliente_mlflow: MlflowClient | None = None,
) -> None:
    """Escribe el tag ``validation_status`` en una version.

    El tag es la evidencia auditable de que el gate corrio y con que resultado.
    Se escribe **antes** de mover el alias: si el proceso muere entre ambas
    operaciones, el estado resultante es "validada pero no promovida", que es
    seguro. El orden inverso dejaria un modelo sirviendo trafico sin registro de
    haber sido validado, que es exactamente el incidente que se quiere evitar.

    Args:
        estado: ``"pending"``, ``"passed"`` o ``"failed"``.
    """
    permitidos = {"pending", "passed", "failed"}
    if estado not in permitidos:
        raise ValueError(f"estado invalido: {estado!r}. Permitidos: {sorted(permitidos)}")
    cli = cliente_mlflow or cliente()
    cli.set_model_version_tag(
        name=nombre, version=str(version), key=config.TAG_VALIDACION, value=estado
    )
    logger.info("%s v%s: %s=%s", nombre, version, config.TAG_VALIDACION, estado)


def cargar_por_alias(
    nombre: str = config.MODELO_REGRESION,
    alias: str = config.ALIAS_PRODUCCION,
) -> Any:
    """Carga el modelo apuntado por el alias como pyfunc.

    Se carga como ``pyfunc`` y no con el flavor nativo (``mlflow.sklearn``,
    ``mlflow.xgboost``) porque quien consume el modelo —la API, el batch, el
    gate— no deberia tener que saber con que libreria se entreno. Si manana el
    champion pasa de sklearn a XGBoost, este codigo no cambia.

    Returns:
        Modelo pyfunc con metodo ``predict``.
    """
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    uri = config.uri_modelo(nombre, alias)
    logger.info("Cargando %s", uri)
    return mlflow.pyfunc.load_model(uri)


def metricas_de_version(
    nombre: str,
    version: str | int,
    *,
    cliente_mlflow: MlflowClient | None = None,
) -> dict[str, float]:
    """Devuelve las metricas del run que produjo esa version del modelo.

    Permite comparar dos versiones sin reentrenar ni recargar los modelos.

    Advertencia importante para el gate: estas metricas se calcularon con el
    codigo y los datos de **ese** run. Si el holdout o la definicion de la
    metrica cambiaron desde entonces, comparar estos numeros con los de un
    candidato nuevo es comparar peras con manzanas. Por eso el gate de
    ``scripts/promote.py`` **recalcula** las metricas del champion sobre el
    holdout actual en lugar de leerlas de aqui, y esta funcion queda para
    inspeccion, para la model card y para el notebook.
    """
    cli = cliente_mlflow or cliente()
    mv = cli.get_model_version(name=nombre, version=str(version))
    if not mv.run_id:
        logger.warning("La version %s de %s no tiene run asociado", version, nombre)
        return {}
    run = cli.get_run(mv.run_id)
    return {k: float(v) for k, v in run.data.metrics.items()}


def explicar_por_que_no_stages() -> str:
    """Texto didactico sobre aliases vs stages.

    Vive en el codigo y no en un markdown para que el notebook y la model card
    impriman **la misma** explicacion: si esta duplicada, en seis meses hay dos
    versiones que se contradicen. Ese fue literalmente el problema del repo
    anterior, donde un modulo ensenaba aliases y otro usaba stages.
    """
    return (
        "Por que aliases + tags y no stages:\n"
        "\n"
        "1. Los stages (None/Staging/Production/Archived) estan deprecados desde\n"
        "   MLflow 2.9.0. El metodo del cliente que los cambiaba todavia existe, pero\n"
        "   la documentacion oficial anuncia su eliminacion en una version mayor.\n"
        "2. Los stages eran un vocabulario cerrado de cuatro palabras. Un equipo real\n"
        "   necesita mas: champion, challenger, shadow, canary, champion-eu. Los\n"
        "   aliases son nombres libres, uno por rol de servicio.\n"
        "3. Un stage mezclaba dos cosas distintas: 'que version sirve' (routing) y\n"
        "   'en que estado de validacion esta' (metadato). Aliases y tags las separan:\n"
        "   el alias @champion enruta, el tag validation_status=passed documenta.\n"
        "4. Solo una version puede tener un alias dado, y eso es una garantia util:\n"
        "   con stages, dos versiones podian quedar en Production a la vez y nadie\n"
        "   sabia cual respondia.\n"
        "5. El rollback se vuelve trivial: mover @champion a la version anterior es\n"
        "   una escritura de metadatos, no un redeploy. La version anterior sigue en\n"
        "   el registry porque las versiones son inmutables.\n"
        "\n"
        "En codigo:\n"
        "    client.set_registered_model_alias('nyc-taxi-duration', 'champion', '7')\n"
        "    client.set_model_version_tag('nyc-taxi-duration', '7', 'validation_status', 'passed')\n"
        "    modelo = mlflow.pyfunc.load_model('models:/nyc-taxi-duration@champion')\n"
    )
