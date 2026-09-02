"""Tests de la instrumentacion Prometheus.

Se testea la instrumentacion por la misma razon por la que se testea el codigo de
negocio: una metrica que no se emite no falla, simplemente deja el dashboard en
blanco. Y un dashboard en blanco es indistinguible de "todo va bien" hasta que
alguien lo mira durante un incidente.

Se leen los valores con ``REGISTRY.get_sample_value``, que es la API publica del
cliente, y siempre por diferencia: el registry es global al proceso y los tests
comparten estado.
"""

from __future__ import annotations

from prometheus_client import REGISTRY

from taxi.api.metricas import TIPOS_ERROR
from tests.api.conftest import (
    DURACION_LARGA,
    NOMBRE_FALSO,
    URI_MODELO_FALSO,
    VERSION_FALSA,
    VIAJE_VALIDO,
    cargador_con_modelo,
    cargador_sin_modelo,
)


def _valor(nombre: str, etiquetas: dict[str, str]) -> float:
    """Valor de una serie, o 0.0 si la serie todavia no existe."""
    bruto = REGISTRY.get_sample_value(nombre, etiquetas)
    return 0.0 if bruto is None else float(bruto)


def test_metrics_expone_las_familias_esperadas(crear_cliente) -> None:
    cargador, _ = cargador_con_modelo()
    cliente = crear_cliente(cargador)
    cliente.post("/predict", json=VIAJE_VALIDO)

    texto = cliente.get("/metrics").text

    # Counter de predicciones etiquetado por version y por clase.
    assert "taxi_predicciones_total" in texto
    assert f'model_version="{VERSION_FALSA}"' in texto
    assert 'clase="corto"' in texto
    # Histogram de latencia: los buckets son lo que permite calcular el p95.
    assert "taxi_inferencia_duracion_segundos_bucket" in texto
    assert "taxi_inferencia_duracion_segundos_count" in texto
    # Counter de errores, pre-inicializado en 0 para todos los tipos.
    assert "taxi_errores_total" in texto
    for tipo in TIPOS_ERROR:
        assert f'tipo="{tipo}"' in texto
    # Info metric del modelo cargado.
    assert "taxi_modelo_info" in texto


def test_prediccion_incrementa_el_contador_de_la_clase_correcta(crear_cliente) -> None:
    cargador, _ = cargador_con_modelo(duracion=DURACION_LARGA)
    cliente = crear_cliente(cargador)
    etiquetas_largo = {"model_version": VERSION_FALSA, "clase": "largo"}
    etiquetas_corto = {"model_version": VERSION_FALSA, "clase": "corto"}
    antes_largo = _valor("taxi_predicciones_total", etiquetas_largo)
    antes_corto = _valor("taxi_predicciones_total", etiquetas_corto)

    cliente.post("/predict/batch", json={"viajes": [VIAJE_VALIDO] * 4})

    # Cuatro predicciones, no un request: para el throughput lo que importa es el
    # volumen de inferencias.
    assert _valor("taxi_predicciones_total", etiquetas_largo) == antes_largo + 4
    assert _valor("taxi_predicciones_total", etiquetas_corto) == antes_corto


def test_la_latencia_se_observa_una_vez_por_llamada_de_inferencia(crear_cliente) -> None:
    """El histogram mide llamadas de inferencia, no predicciones individuales.

    Un lote de 4 viajes es UNA observacion de latencia. Contarlo cuatro veces
    inflaria artificialmente el throughput aparente y aplanaria el p95.
    """
    cargador, _ = cargador_con_modelo()
    cliente = crear_cliente(cargador)
    etiquetas = {"model_version": VERSION_FALSA}
    antes = _valor("taxi_inferencia_duracion_segundos_count", etiquetas)

    cliente.post("/predict/batch", json={"viajes": [VIAJE_VALIDO] * 4})

    assert _valor("taxi_inferencia_duracion_segundos_count", etiquetas) == antes + 1


def test_la_info_metric_publica_la_version_cargada(crear_cliente) -> None:
    """El valor es 1 y la informacion vive en los labels: patron de info metric."""
    cargador, _ = cargador_con_modelo()
    crear_cliente(cargador)

    valor = _valor(
        "taxi_modelo_info",
        {
            "model_name": NOMBRE_FALSO,
            "model_version": VERSION_FALSA,
            "model_uri": URI_MODELO_FALSO,
        },
    )

    assert valor == 1.0


def test_los_errores_se_cuentan_por_tipo(crear_cliente) -> None:
    """Cada clase de fallo va a su propio label, con cardinalidad acotada."""
    cliente_sin = crear_cliente(cargador_sin_modelo())
    antes_503 = _valor("taxi_errores_total", {"tipo": "modelo_no_disponible"})
    antes_422 = _valor("taxi_errores_total", {"tipo": "validacion"})

    cliente_sin.post("/predict", json=VIAJE_VALIDO)
    cliente_sin.post("/predict", json={"PULocationID": 9999})

    assert _valor("taxi_errores_total", {"tipo": "modelo_no_disponible"}) == antes_503 + 1
    assert _valor("taxi_errores_total", {"tipo": "validacion"}) == antes_422 + 1


def test_fallo_de_inferencia_se_cuenta_como_inferencia(crear_cliente) -> None:
    cargador, _ = cargador_con_modelo(excepcion=RuntimeError("boom interno"))
    cliente = crear_cliente(cargador)
    antes = _valor("taxi_errores_total", {"tipo": "inferencia"})

    cliente.post("/predict", json=VIAJE_VALIDO)

    assert _valor("taxi_errores_total", {"tipo": "inferencia"}) == antes + 1
