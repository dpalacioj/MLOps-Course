"""Tests de los endpoints operativos: `/health`, `/modelo` y la raiz.

Lo que se protege aqui es la propiedad que el CI necesita: **la imagen debe poder
arrancar y responder sin registry**. Si alguien "arregla" `/health` para que
devuelva 503 sin modelo, el paso `imagen` del CI se cae y el contenedor pasa a ser
imposible de diagnosticar. Estos tests convierten esa decision de diseno en algo
que no se puede romper por accidente.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from taxi.api.main import app
from tests.api.conftest import (
    NOMBRE_FALSO,
    VERSION_FALSA,
    cargador_con_modelo,
    cargador_sin_modelo,
)


def test_health_sin_modelo_responde_200_y_model_loaded_false(crear_cliente) -> None:
    """Liveness check: 200 aunque no haya modelo.

    Es el escenario exacto del CI (`TAXI_MODELO_URI=ninguno` + `curl -sf`). Un
    codigo distinto de 200 rompe la verificacion de la imagen.
    """
    cliente = crear_cliente(cargador_sin_modelo())

    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["model_loaded"] is False
    assert cuerpo["status"] == "degradado"
    assert cuerpo["model_name"] is None
    assert cuerpo["model_version"] is None
    # La URI si se expone: es el dato que hace obvio el error de configuracion.
    assert cuerpo["model_uri"] == "ninguno"
    assert cuerpo["version_api"]


def test_health_con_modelo_reporta_nombre_y_version(crear_cliente) -> None:
    cargador, _ = cargador_con_modelo()
    cliente = crear_cliente(cargador)

    cuerpo = cliente.get("/health").json()

    assert cuerpo["status"] == "ok"
    assert cuerpo["model_loaded"] is True
    assert cuerpo["model_name"] == NOMBRE_FALSO
    assert cuerpo["model_version"] == VERSION_FALSA


def test_modelo_sin_modelo_devuelve_503(crear_cliente) -> None:
    cliente = crear_cliente(cargador_sin_modelo())

    respuesta = cliente.get("/modelo")

    assert respuesta.status_code == 503
    assert "error" in respuesta.json()


def test_modelo_expone_las_features_del_contrato(crear_cliente) -> None:
    """`/modelo` debe declarar las features reales del contrato compartido.

    Sirve de red contra la regresion mas costosa del repo anterior: que la API
    sirviera un subconjunto de features distinto al del entrenamiento.
    """
    from taxi.features.contract import FEATURES

    cargador, _ = cargador_con_modelo()
    cliente = crear_cliente(cargador)

    cuerpo = cliente.get("/modelo").json()

    assert cuerpo["features"] == list(FEATURES)
    assert cuerpo["model_version"] == VERSION_FALSA
    assert cuerpo["umbral_viaje_largo_min"] == 30.0


def test_raiz_redirige_a_docs(crear_cliente) -> None:
    cliente = crear_cliente(cargador_sin_modelo())

    respuesta = cliente.get("/", follow_redirects=False)

    assert respuesta.status_code in (307, 308)
    assert respuesta.headers["location"] == "/docs"


def test_lifespan_arranca_en_modo_degradado_sin_modelo() -> None:
    """El arranque completo (lifespan incluido) no debe fallar sin modelo.

    Aqui SI se usa el context manager: es el unico test que ejercita el
    `lifespan`, que es el codigo que reemplazo al deprecado
    ``@app.on_event("startup")``. El cargador global se resuelve con
    ``TAXI_MODELO_URI=ninguno`` (fixture `_aislar_estado`), asi que no hay red.
    """
    with TestClient(app) as cliente:
        respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json()["model_loaded"] is False
