"""Tests de la API con ``TestClient``.

Se prueban sin modelo cargado a proposito: es el estado en el que arranca la
imagen en CI, y es el que hay que poder verificar sin levantar el registry.
Un test que exige infraestructura no corre en cada PR, y un test que no corre en
cada PR no existe.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

PAYLOAD_VALIDO = {
    "categoria": "A",
    "region": "norte",
    "canal": "web",
    "cantidad": 3.0,
    "precio_unitario": 19990.0,
    "descuento": 0.1,
    "ts": "2024-01-15T08:30:00",
}


def test_health_responde_aunque_no_haya_modelo(cliente: TestClient) -> None:
    """``/health`` responde 200 aunque el modelo no este cargado.

    Y dice que NO lo esta. Un `/health` que devuelve `{"status": "ok"}` sin mirar
    el modelo miente: el proceso esta vivo y el servicio no sirve. Ese es el
    healthcheck que hace que un orquestador mande trafico a un contenedor roto.
    """
    respuesta = cliente.get("/health")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ok"
    assert cuerpo["modelo_cargado"] is False


def test_predict_sin_modelo_devuelve_503(cliente: TestClient) -> None:
    """503 y no 500: "todavia no puedo atender" es distinto de "me rompi".

    La diferencia importa porque un balanceador reintenta un 503 y no un 500.
    """
    respuesta = cliente.post("/predict", json=PAYLOAD_VALIDO)
    assert respuesta.status_code == 503
    assert "modelo" in respuesta.json()["detail"]


def test_rechaza_campo_desconocido(cliente: TestClient) -> None:
    """``extra="forbid"``: un typo en el nombre del campo es un 422, no una
    prediccion calculada con el default silencioso."""
    respuesta = cliente.post("/predict", json={**PAYLOAD_VALIDO, "Region": "norte"})
    assert respuesta.status_code == 422


def test_rechaza_valor_fuera_de_rango(cliente: TestClient) -> None:
    respuesta = cliente.post("/predict", json={**PAYLOAD_VALIDO, "descuento": 1.5})
    assert respuesta.status_code == 422


def test_rechaza_timestamp_con_zona_horaria(cliente: TestClient) -> None:
    """La conversion silenciosa de zona horaria desplaza la feature `hora` y
    degrada la prediccion sin que nada falle."""
    respuesta = cliente.post("/predict", json={**PAYLOAD_VALIDO, "ts": "2024-01-15T08:30:00Z"})
    assert respuesta.status_code == 422


def test_el_lote_tiene_tope(cliente: TestClient) -> None:
    """Un lote sin limite es un vector de DoS y arruina la latencia de cola."""
    respuesta = cliente.post("/predict/batch", json={"items": [PAYLOAD_VALIDO] * 1000})
    assert respuesta.status_code == 422


def test_el_openapi_documenta_los_endpoints(cliente: TestClient) -> None:
    """El contrato y la documentacion son el mismo objeto: si esto falla, la
    documentacion que ve el consumidor esta desalineada."""
    esquema = cliente.get("/openapi.json").json()
    assert "/predict" in esquema["paths"]
    assert "/health" in esquema["paths"]
