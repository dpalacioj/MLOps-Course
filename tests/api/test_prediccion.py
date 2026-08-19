"""Tests del camino de inferencia: `/predict` y `/predict/batch`.

Tres propiedades se verifican aqui y las tres son requisitos de operacion, no
detalles esteticos:

1. Sin modelo se responde 503, no 500 ni una prediccion inventada.
2. La respuesta incluye ``model_version``: sin ese campo el sistema no es
   auditable.
3. Un fallo interno NO viaja al cliente. El repo anterior devolvia
   ``str(e)`` y con eso filtraba cadenas de conexion y rutas del servidor.
"""

from __future__ import annotations

from taxi.api.main import MSG_ERROR_INFERENCIA
from taxi.features.contract import FEATURES
from tests.api.conftest import (
    DURACION_CORTA,
    DURACION_LARGA,
    NOMBRE_FALSO,
    VERSION_FALSA,
    VIAJE_VALIDO,
    cargador_con_modelo,
    cargador_sin_modelo,
)


def test_predict_sin_modelo_devuelve_503(crear_cliente) -> None:
    """503 (Service Unavailable) es el codigo correcto: el fallo es temporal.

    Un 500 diria "el request te salio mal a ti"; un 503 dice "vuelve a intentar,
    el servicio todavia no puede atenderte" y es lo que un cliente con reintentos
    y backoff sabe interpretar.
    """
    cliente = crear_cliente(cargador_sin_modelo())

    respuesta = cliente.post("/predict", json=VIAJE_VALIDO)

    assert respuesta.status_code == 503
    cuerpo = respuesta.json()
    assert "modelo" in cuerpo["error"].lower()
    assert cuerpo["detalle_validacion"] is None


def test_predict_devuelve_el_esquema_completo_con_model_version(crear_cliente) -> None:
    cargador, falso = cargador_con_modelo(duracion=DURACION_CORTA)
    cliente = crear_cliente(cargador)

    respuesta = cliente.post("/predict", json=VIAJE_VALIDO)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo == {
        "duration_min": DURACION_CORTA,
        "viaje_largo": False,
        "model_name": NOMBRE_FALSO,
        "model_version": VERSION_FALSA,
        "latencia_ms": cuerpo["latencia_ms"],
    }
    assert cuerpo["latencia_ms"] >= 0.0

    # El modelo recibio EXACTAMENTE las features del contrato compartido, con las
    # derivadas incluidas. Esto es lo que detecta un training/serving skew: si
    # alguien vuelve a armar el diccionario a mano y se olvida de `hora_pickup`,
    # este assert falla.
    (registros,) = falso.recibidos
    assert sorted(registros[0].keys()) == sorted(FEATURES)
    assert registros[0]["PU_DO"] == "43_238"
    assert registros[0]["hora_pickup"] == 8
    # 2023-05-15 fue lunes -> dayofweek 0.
    assert registros[0]["dia_semana_pickup"] == 0


def test_predict_deriva_viaje_largo_del_umbral(crear_cliente) -> None:
    """El booleano no lo decide la API: sale del umbral de ``config.py``."""
    cargador, _ = cargador_con_modelo(duracion=DURACION_LARGA)
    cliente = crear_cliente(cargador)

    cuerpo = cliente.post("/predict", json=VIAJE_VALIDO).json()

    assert cuerpo["duration_min"] == DURACION_LARGA
    assert cuerpo["viaje_largo"] is True


def test_predict_batch_devuelve_una_prediccion_por_viaje(crear_cliente) -> None:
    cargador, falso = cargador_con_modelo()
    cliente = crear_cliente(cargador)

    respuesta = cliente.post("/predict/batch", json={"viajes": [VIAJE_VALIDO] * 3})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 3
    assert len(cuerpo["predicciones"]) == 3
    assert cuerpo["model_version"] == VERSION_FALSA
    assert all(p["model_version"] == VERSION_FALSA for p in cuerpo["predicciones"])
    # Una sola llamada de inferencia para los tres viajes: el lote existe para
    # amortizar el costo fijo, no para iterar `predict` N veces.
    assert len(falso.recibidos) == 1
    assert len(falso.recibidos[0]) == 3


def test_error_interno_no_filtra_el_mensaje_de_la_excepcion(crear_cliente) -> None:
    """El texto de la excepcion se queda en el servidor.

    El mensaje del doble imita lo que de verdad aparece en estos errores: una
    cadena de conexion con credenciales. Si el handler la reenviara, cualquiera
    podria provocarla y leerla.
    """
    secreto = "postgres://mlflow:clave-super-secreta@postgres:5432/mlflow no existe la tabla"
    cargador, _ = cargador_con_modelo(excepcion=RuntimeError(secreto))
    cliente = crear_cliente(cargador)

    respuesta = cliente.post("/predict", json=VIAJE_VALIDO)

    assert respuesta.status_code == 500
    texto = respuesta.text
    assert "clave-super-secreta" not in texto
    assert "postgres" not in texto
    assert "RuntimeError" not in texto
    cuerpo = respuesta.json()
    assert cuerpo["error"] == MSG_ERROR_INFERENCIA
    # Pero SI se devuelve un id de correlacion: sin el, el error es irrastreable
    # y el usuario no puede reportarlo de forma util.
    assert cuerpo["id_correlacion"]
    assert len(cuerpo["id_correlacion"]) == 12


def test_error_interno_en_lote_tampoco_filtra(crear_cliente) -> None:
    """Los dos endpoints comparten el mismo camino de error, y se comprueba.

    En el repo anterior el try/except estaba duplicado y solo una de las copias
    se mantenia al dia.
    """
    cargador, _ = cargador_con_modelo(excepcion=ValueError("ruta interna /srv/app/model"))
    cliente = crear_cliente(cargador)

    respuesta = cliente.post("/predict/batch", json={"viajes": [VIAJE_VALIDO]})

    assert respuesta.status_code == 500
    assert "/srv/app/model" not in respuesta.text
    assert respuesta.json()["error"] == MSG_ERROR_INFERENCIA


def test_predict_sin_pickup_datetime_usa_la_hora_actual(crear_cliente) -> None:
    """El default documentado funciona, y se registra que es una decision.

    El test no fija la hora, asi que no puede afirmar el valor de `hora_pickup`;
    solo que esta en rango. Esa imposibilidad ES la consecuencia documentada en
    el schema: omitir `pickup_datetime` vuelve la prediccion no reproducible.
    """
    cargador, falso = cargador_con_modelo()
    cliente = crear_cliente(cargador)

    viaje = {k: v for k, v in VIAJE_VALIDO.items() if k != "pickup_datetime"}
    respuesta = cliente.post("/predict", json=viaje)

    assert respuesta.status_code == 200
    registro = falso.recibidos[0][0]
    assert 0 <= registro["hora_pickup"] <= 23
    assert 0 <= registro["dia_semana_pickup"] <= 6
