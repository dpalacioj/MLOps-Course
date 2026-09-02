"""Tests del detector de drift.

Los dos casos que importan son simetricos y hay que probar los dos:

- **detecta** cuando la distribucion cambio de verdad;
- **no grita** cuando no cambio.

Un detector que solo se prueba en el primer caso se calibra hacia los falsos
positivos, y un monitoreo con falsos positivos se apaga a la semana. La fatiga de
alertas es un problema de operacion tan real como el drift.
"""

from __future__ import annotations

import pandas as pd

from miproyecto.features import contract as fc
from miproyecto.monitoring import check_drift


def test_no_detecta_drift_entre_la_misma_particion(df_crudo: pd.DataFrame) -> None:
    df = fc.construir_features(df_crudo.assign(cantidad=df_crudo["cantidad"].fillna(1.0)))
    resultado = check_drift.evaluar_drift(df, df.copy())
    assert resultado.columnas, "el evaluador no comparo ninguna columna"
    assert resultado.columnas_con_drift == []
    assert not resultado.hay_drift


def test_detecta_drift_numerico_y_categorico(
    df_crudo: pd.DataFrame, df_produccion: pd.DataFrame
) -> None:
    ref = fc.construir_features(df_crudo.assign(cantidad=df_crudo["cantidad"].fillna(1.0)))
    pro = fc.construir_features(
        df_produccion.assign(cantidad=df_produccion["cantidad"].fillna(1.0))
    )
    resultado = check_drift.evaluar_drift(ref, pro)

    assert "precio_unitario" in resultado.columnas_con_drift
    assert "canal" in resultado.columnas_con_drift
    assert resultado.hay_drift


def test_p_valor_pequeno_con_efecto_minusculo_no_es_drift() -> None:
    """La trampa del p-valor, hecha test.

    Dos muestras grandes con una diferencia irrelevante dan p muy pequeno. Si el
    criterio fuera solo el p-valor, esto seria una alerta. No lo es.
    """
    ref = pd.Series(range(200_000), name="x", dtype="float64")
    pro = ref + 1.0  # desplazamiento ridiculo frente al rango 0-200000
    resultado = check_drift.drift_numerico(ref, pro)
    assert resultado.efecto < check_drift.EFECTO_MINIMO_KS
    assert not resultado.hay_drift


def test_categoria_nueva_en_produccion_se_detecta() -> None:
    """Una categoria que no existia es el cambio mas facil de esconder."""
    ref = pd.Series(["a"] * 500 + ["b"] * 500, name="c")
    pro = pd.Series(["a"] * 250 + ["b"] * 250 + ["z"] * 500, name="c")
    resultado = check_drift.drift_categorico(ref, pro)
    assert resultado.hay_drift


def test_el_markdown_reporta_el_veredicto(
    df_crudo: pd.DataFrame, df_produccion: pd.DataFrame
) -> None:
    ref = fc.construir_features(df_crudo.assign(cantidad=df_crudo["cantidad"].fillna(1.0)))
    pro = fc.construir_features(
        df_produccion.assign(cantidad=df_produccion["cantidad"].fillna(1.0))
    )
    texto = check_drift.evaluar_drift(ref, pro).a_markdown()
    assert "| columna | test |" in texto
    assert "ACCIONAR" in texto
