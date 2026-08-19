"""Tests del contrato de features.

Lo que se protege aqui es la propiedad que evita el train/serving skew: que haya
UNA sola derivacion de features y que sea determinista e idempotente. El dia que
el notebook derive `hora` de una forma y la API de otra, el modelo servira
predicciones peores y nada fallara.
"""

from __future__ import annotations

import pandas as pd
import pytest

from miproyecto.features import contract as fc


def test_construir_features_es_idempotente(df_crudo: pd.DataFrame) -> None:
    """Llamarla dos veces da el mismo resultado.

    Importa porque el orquestador puede cachear el resultado y porque el pipeline
    puede pasar por la funcion mas de una vez sin que nadie lo note.
    """
    una = fc.construir_features(df_crudo)
    dos = fc.construir_features(una)
    pd.testing.assert_frame_equal(una[fc.FEATURES], dos[fc.FEATURES])


def test_falla_con_mensaje_util_si_falta_una_columna(df_crudo: pd.DataFrame) -> None:
    """Fallar temprano diciendo QUE falta, en lugar de un KeyError opaco veinte
    lineas mas abajo."""
    with pytest.raises(KeyError, match="cantidad"):
        fc.construir_features(df_crudo.drop(columns=["cantidad"]))


def test_las_categoricas_no_quedan_numericas(df_crudo: pd.DataFrame) -> None:
    """Si una categorica queda numerica, el vectorizador la trata como magnitud.

    Es un bug silencioso: el modelo entrena, la metrica sale plausible y el
    modelo aprendio que la region 3 es "el triple" de la region 1.
    """
    out = fc.construir_features(df_crudo)
    for col in fc.CRUDAS_CATEGORICAS + fc.DERIVADAS_CATEGORICAS:
        assert out[col].map(type).eq(str).all(), f"{col} no quedo como str"


def test_las_numericas_no_quedan_string(df_crudo: pd.DataFrame) -> None:
    """El error simetrico: castear el dataframe crudo completo a str convierte
    tambien los precios, y el vectorizador los one-hot-encodea."""
    out = fc.construir_features(df_crudo)
    for col in fc.DERIVADAS_NUMERICAS:
        assert pd.api.types.is_numeric_dtype(out[col]), f"{col} deberia ser numerica"


def test_a_diccionarios_exige_features_derivadas(df_crudo: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="construir_features"):
        fc.a_diccionarios(df_crudo)


def test_a_diccionarios_devuelve_todas_las_features(df_crudo: pd.DataFrame) -> None:
    registros = fc.a_diccionarios(fc.construir_features(df_crudo))
    assert len(registros) == len(df_crudo)
    assert set(registros[0]) == set(fc.FEATURES)


def test_no_hay_features_duplicadas() -> None:
    """Una feature repetida en la lista se vectoriza dos veces y falsea la
    importancia de variables."""
    assert len(fc.FEATURES) == len(set(fc.FEATURES))


def test_el_target_no_es_una_feature() -> None:
    """El leakage mas simple y mas comun de todos."""
    assert fc.TARGET not in fc.FEATURES
