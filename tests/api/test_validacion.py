"""Tests del contrato de entrada.

Cada uno de estos casos es un input que, sin validacion, produciria una
prediccion en lugar de un error. Ese es el punto: el fallo por defecto de un
sistema de ML no es una excepcion, es un numero plausible y equivocado.
"""

from __future__ import annotations

import pytest

from taxi.api.schemas import MAX_VIAJES_POR_LOTE
from tests.api.conftest import VIAJE_VALIDO, cargador_con_modelo


@pytest.fixture
def cliente(crear_cliente):
    """Cliente con modelo cargado: se valida el contrato, no la falta de modelo.

    Si el modelo no estuviera cargado, un 503 podria enmascarar un 422 que nunca
    se comprobo.
    """
    cargador, _ = cargador_con_modelo()
    return crear_cliente(cargador)


def _sin(campo: str) -> dict:
    return {k: v for k, v in VIAJE_VALIDO.items() if k != campo}


def _con(**cambios: object) -> dict:
    return {**VIAJE_VALIDO, **cambios}


def test_falta_un_campo_obligatorio_devuelve_422_con_detalle(cliente) -> None:
    respuesta = cliente.post("/predict", json=_sin("trip_distance"))

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["detalle_validacion"], "el 422 debe explicar que falta"
    campos = {tuple(e["loc"]) for e in cuerpo["detalle_validacion"]}
    assert ("body", "trip_distance") in campos
    # El envelope es el mismo que en los demas errores.
    assert cuerpo["error"]


@pytest.mark.parametrize("zona", [0, -1, 266, 9999])
def test_zona_fuera_de_rango_se_rechaza(cliente, zona) -> None:
    """Las zonas validas de la TLC son 1-265. Fuera de ahi el modelo nunca vio
    ese valor: el ``DictVectorizer`` lo ignoraria y la prediccion saldria como si
    la zona no existiera, sin ninguna senal de error."""
    respuesta = cliente.post("/predict", json=_con(PULocationID=zona))

    assert respuesta.status_code == 422
    assert any(e["loc"][-1] == "PULocationID" for e in respuesta.json()["detalle_validacion"])


def test_zona_de_destino_fuera_de_rango_se_rechaza(cliente) -> None:
    respuesta = cliente.post("/predict", json=_con(DOLocationID=300))

    assert respuesta.status_code == 422


@pytest.mark.parametrize("distancia", [-0.1, -5.0])
def test_distancia_negativa_se_rechaza(cliente, distancia) -> None:
    """Una distancia negativa no tiene interpretacion fisica y el modelo la
    trataria como una feature numerica cualquiera, extrapolando fuera del dominio
    de entrenamiento."""
    respuesta = cliente.post("/predict", json=_con(trip_distance=distancia))

    assert respuesta.status_code == 422


def test_distancia_absurdamente_grande_se_rechaza(cliente) -> None:
    """El tope de 100 millas es el mismo del contrato de datos de la sesion 2.

    Ademas de filtrar errores de captura, es el limite que atrapa un cambio de
    unidades: si un cliente empieza a mandar kilometros, los viajes largos se
    salen del rango y el fallo se vuelve visible.
    """
    respuesta = cliente.post("/predict", json=_con(trip_distance=250.0))

    assert respuesta.status_code == 422


def test_campo_desconocido_se_rechaza(cliente) -> None:
    """``extra="forbid"``: un typo del cliente no debe pasar como default.

    Sin esto, `PULocationId` (i minuscula) se ignoraria en silencio y el request
    fallaria por campo obligatorio ausente, o peor, pasaria con un valor que el
    cliente no eligio.
    """
    respuesta = cliente.post("/predict", json=_con(PU_DO="43_238"))

    assert respuesta.status_code == 422


def test_pickup_con_zona_horaria_se_rechaza(cliente) -> None:
    """El modelo aprendio la hora en horario local de Nueva York.

    Aceptar un timestamp en UTC y convertirlo (o no) en silencio desplaza
    `hora_pickup` varias horas y degrada la prediccion sin ningun error visible.
    """
    respuesta = cliente.post("/predict", json=_con(pickup_datetime="2023-05-15T08:30:00Z"))

    assert respuesta.status_code == 422
    detalle = str(respuesta.json()["detalle_validacion"])
    assert "zona horaria" in detalle


def test_lote_vacio_se_rechaza(cliente) -> None:
    respuesta = cliente.post("/predict/batch", json={"viajes": []})

    assert respuesta.status_code == 422


def test_lote_respeta_el_limite_maximo(cliente) -> None:
    """El tope acota memoria y latencia de cola por request.

    Se verifica el borde exacto: MAX pasa, MAX + 1 se rechaza. Un limite que solo
    se prueba "muy por encima" suele estar mal por uno.
    """
    en_el_limite = cliente.post(
        "/predict/batch", json={"viajes": [VIAJE_VALIDO] * MAX_VIAJES_POR_LOTE}
    )
    assert en_el_limite.status_code == 200
    assert en_el_limite.json()["total"] == MAX_VIAJES_POR_LOTE

    excedido = cliente.post(
        "/predict/batch", json={"viajes": [VIAJE_VALIDO] * (MAX_VIAJES_POR_LOTE + 1)}
    )
    assert excedido.status_code == 422
    assert excedido.json()["detalle_validacion"]
