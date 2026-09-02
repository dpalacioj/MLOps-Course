"""Tests del contrato de features.

Cada test aqui corresponde a un fallo concreto y silencioso del pipeline de
features. No son tests de cobertura: son la prueba de que ese fallo no puede
entrar sin que algo se ponga rojo.
"""

from __future__ import annotations

import pandas as pd
import pytest

from taxi.features import contract as fc


def test_construir_features_es_idempotente(df_crudo_valido: pd.DataFrame) -> None:
    """Llamarla dos veces debe dar el mismo resultado.

    Importa porque el flow de Prefect la cachea: si no fuera idempotente, un
    reintento del task produciria features distintas de las del primer intento y
    el modelo se entrenaria con dos definiciones mezcladas.
    """
    una_vez = fc.construir_features(df_crudo_valido)
    dos_veces = fc.construir_features(una_vez)
    pd.testing.assert_frame_equal(una_vez[fc.FEATURES], dos_veces[fc.FEATURES])


def test_construir_features_no_muta_la_entrada(df_crudo_valido: pd.DataFrame) -> None:
    """Debe trabajar sobre una copia: mutar la entrada rompe el caching."""
    antes = df_crudo_valido.copy()
    fc.construir_features(df_crudo_valido)
    pd.testing.assert_frame_equal(df_crudo_valido, antes)


@pytest.mark.parametrize("columna", ["PULocationID", "DOLocationID", "trip_distance"])
def test_construir_features_lanza_keyerror_con_mensaje_util(
    df_crudo_valido: pd.DataFrame, columna: str
) -> None:
    """EL BUG ORIGINAL.

    `loaders.py` casteaba `['PU_DO', 'trip_distance']` a string sobre el parquet
    CRUDO, donde `PU_DO` todavia no existe, y el pipeline estrella del curso
    fallaba con `KeyError: "['PU_DO'] not in index"`: un mensaje que no dice ni
    que columna falta ni donde deberia haberse creado.

    El requisito no es solo "falla", es "falla diciendo que falta y que hay".
    """
    df = df_crudo_valido.drop(columns=[columna])
    with pytest.raises(KeyError) as excinfo:
        fc.construir_features(df)

    mensaje = str(excinfo.value)
    assert columna in mensaje
    assert "Columnas presentes" in mensaje


def test_a_diccionarios_falla_si_no_se_derivaron_features(
    df_crudo_valido: pd.DataFrame,
) -> None:
    """Sin llamar antes a construir_features, PU_DO y hora_pickup no existen."""
    with pytest.raises(KeyError) as excinfo:
        fc.a_diccionarios(df_crudo_valido)

    mensaje = str(excinfo.value)
    assert fc.COL_RUTA in mensaje
    assert "construir_features" in mensaje


def test_trip_distance_sigue_siendo_numerica(df_procesado_valido: pd.DataFrame) -> None:
    """El otro lado del bug original.

    Si se "arreglaba" el KeyError casteando todo a string, `trip_distance`
    quedaba como texto y `DictVectorizer` la one-hot-encodeaba: miles de columnas
    binarias en lugar de una variable continua. El modelo entrenaba y el error
    era peor sin ninguna senal de que algo estaba mal.
    """
    registros = fc.a_diccionarios(df_procesado_valido)
    valor = registros[0]["trip_distance"]
    assert isinstance(valor, float), f"trip_distance llego como {type(valor).__name__}"
    # Las zonas, en cambio, SI deben ser texto: son categorias.
    assert isinstance(registros[0]["PULocationID"], str)
    assert isinstance(registros[0][fc.COL_RUTA], str)


def test_ruta_tiene_el_formato_del_contrato(df_procesado_valido: pd.DataFrame) -> None:
    """PU_DO debe cumplir el patron que exige ViajesProcesados."""
    assert df_procesado_valido[fc.COL_RUTA].str.fullmatch(r"\d+_\d+").all()


def test_a_diccionarios_devuelve_exactamente_las_features_del_contrato(
    df_procesado_valido: pd.DataFrame,
) -> None:
    """Ni una columna mas ni una menos: es la frontera del modelo.

    Una columna extra que se cuele aqui (por ejemplo el target) seria leakage
    directo, y el vectorizador la aceptaria sin decir nada.
    """
    registros = fc.a_diccionarios(df_procesado_valido)
    assert set(registros[0]) == set(fc.FEATURES)
    assert fc.TARGET_REGRESION not in registros[0]
    assert len(registros) == len(df_procesado_valido)
