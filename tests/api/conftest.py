"""Fixtures de los tests de la API.

Idea central: **ningun test de este paquete toca MLflow ni la red**. El modelo se
sustituye por un doble de prueba a traves de la costura que expone
``CargadorModelo`` (``cargar_pyfunc``), y el cargador se inyecta con
``app.dependency_overrides``, que es el mecanismo de FastAPI para esto.

Por que importa: si los tests de la API necesitaran un registry corriendo,
dejarian de correr en CI, alguien los marcaria como `skip` y la API se quedaria
sin cobertura. Un test que depende de un servicio externo no es un test unitario,
es un test de integracion disfrazado.

Detalle de `TestClient`: se instancia **sin** usarlo como context manager a
proposito. Starlette solo ejecuta el `lifespan` dentro del `with`, y aqui no
queremos que arranque el cargador global (que intentaria resolver el alias real).
El test que si verifica el arranque entra al `with` explicitamente.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from taxi.api import metricas
from taxi.api.main import app
from taxi.api.modelo import CargadorModelo, obtener_cargador, reiniciar_cargador

#: URI por VERSION (inmutable). Se usa en los tests en lugar de la URI por alias
#: porque la version se deduce de la propia cadena y no hace falta preguntarle al
#: registry: el doble de prueba queda completamente offline.
URI_MODELO_FALSO = "models:/nyc-taxi-duration/7"
VERSION_FALSA = "7"
NOMBRE_FALSO = "nyc-taxi-duration"

#: Menor que UMBRAL_VIAJE_LARGO_MIN (30) -> clase "corto".
DURACION_CORTA = 12.5
#: Mayor que el umbral -> clase "largo".
DURACION_LARGA = 45.0

VIAJE_VALIDO: dict[str, Any] = {
    "PULocationID": 43,
    "DOLocationID": 238,
    "trip_distance": 2.4,
    "pickup_datetime": "2023-05-15T08:30:00",
}


class ModeloFalso:
    """Doble de prueba con la misma interfaz que un ``PyFuncModel``.

    Solo necesita ``predict``, porque es lo unico que la API usa del modelo. Eso
    es una senal de que el acoplamiento con MLflow esta bien contenido: si la API
    dependiera de la metadata, del run_id o del flavor, este doble tendria que
    imitar media libreria.
    """

    def __init__(
        self, duracion: float = DURACION_CORTA, excepcion: Exception | None = None
    ) -> None:
        self.duracion = duracion
        self.excepcion = excepcion
        #: Registros recibidos. Permite verificar que la API construye las
        #: features del contrato y no un diccionario improvisado.
        self.recibidos: list[Sequence[dict[str, Any]]] = []

    def predict(self, registros: Sequence[dict[str, Any]]) -> list[float]:
        self.recibidos.append(registros)
        if self.excepcion is not None:
            raise self.excepcion
        return [self.duracion] * len(registros)


@pytest.fixture(autouse=True)
def _aislar_estado(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Deja el proceso limpio antes y despues de cada test.

    ``TAXI_MODELO_URI=ninguno`` es un cinturon de seguridad: si algun test
    construyera el cargador global por descuido, arrancaria degradado en lugar de
    intentar una conexion al registry y colgar el CI durante el timeout.
    """
    monkeypatch.setenv("TAXI_MODELO_URI", "ninguno")
    reiniciar_cargador(None)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    reiniciar_cargador(None)


@pytest.fixture
def crear_cliente() -> Iterator[Callable[[CargadorModelo], TestClient]]:
    """Devuelve una funcion que monta un cliente con el cargador indicado."""

    def _crear(cargador: CargadorModelo) -> TestClient:
        app.dependency_overrides[obtener_cargador] = lambda: cargador
        return TestClient(app)

    yield _crear


def cargador_sin_modelo() -> CargadorModelo:
    """Cargador en modo degradado, como el de la imagen verificada en CI."""
    cargador = CargadorModelo(uri="ninguno")
    cargador.cargar()
    return cargador


def cargador_con_modelo(
    duracion: float = DURACION_CORTA,
    excepcion: Exception | None = None,
) -> tuple[CargadorModelo, ModeloFalso]:
    """Cargador con un modelo falso ya cargado, y el doble para inspeccionarlo.

    Se llama a ``metricas.fijar_modelo`` para replicar lo que hace el `lifespan`:
    sin eso, la info metric no existiria y el test de `/metrics` estaria
    verificando un escenario que en produccion no ocurre.
    """
    falso = ModeloFalso(duracion=duracion, excepcion=excepcion)
    cargador = CargadorModelo(uri=URI_MODELO_FALSO, cargar_pyfunc=lambda _uri: falso)
    assert cargador.cargar() is True
    meta = cargador.metadatos
    assert meta is not None
    metricas.fijar_modelo(meta.nombre, meta.version, meta.uri)
    return cargador, falso
