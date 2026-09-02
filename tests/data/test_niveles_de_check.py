"""Tests de los tres niveles de check del contrato de datos crudos.

Estos tests existen por un bug real encontrado al ejecutar el pipeline contra
datos de verdad. El contrato original exigia ``trip_distance <= 100`` **por
fila**, y el parquet de la TLC de 2023-01 trae 37 viajes de mas de 100 millas
(uno de 120.098). El resultado: `taxi data` fallaba con ``SchemaErrors`` en la
primera particion y bloqueaba el curso entero.

La leccion, que ahora esta codificada aqui: una cota por fila y una cota sobre
la distribucion responden preguntas distintas. Confundirlas produce o un
contrato inutilizable (falla por 37 filas de 68.211) o un contrato inutil
(acepta que la columna cambie de significado).
"""

from __future__ import annotations

import pandas as pd
import pytest

from taxi.data import contract as dc

from ..conftest import MILLAS_A_KM, generar_crudos


# =============================================================================
# Nivel 1 — por fila: atrapa registros corruptos, no rechaza la particion
# =============================================================================
def test_outliers_individuales_no_invalidan_la_particion() -> None:
    """Un punado de registros absurdos no debe tumbar el lote completo.

    Reproduce la proporcion real de la TLC: 37 filas de 68.211 (0,054%).
    """
    df = generar_crudos(filas=2_000)
    n_outliers = 1  # 1 de 2.000 = 0,05%, la proporcion real
    df.loc[df.index[:n_outliers], "trip_distance"] = 120_098.84
    dc.validar_crudos(df)  # no debe lanzar


def test_valor_negativo_si_invalida() -> None:
    """Una distancia negativa no es un outlier, es imposible."""
    df = generar_crudos()
    df.loc[df.index[0], "trip_distance"] = -3.0
    with pytest.raises(Exception, match=r"(?i)greater_than_or_equal|schema"):
        dc.validar_crudos(df)


# =============================================================================
# Nivel 2 — por distribucion: atrapa problemas sistematicos
# =============================================================================
def test_fraccion_alta_de_outliers_si_invalida() -> None:
    """Si el 1% supera las 100 millas, la columna cambio de significado."""
    df = generar_crudos(filas=2_000)
    cuantas = int(len(df) * 0.02)  # 2%, muy por encima del umbral de 0,3%
    df.loc[df.index[:cuantas], "trip_distance"] = 150.0
    with pytest.raises(Exception, match="outliers_de_distancia_son_marginales"):
        dc.validar_crudos(df)


def test_cambio_de_unidades_lo_atrapa_el_check_de_distribucion() -> None:
    """El fixture en kilometros falla por la FRACCION, no por una fila.

    Es la diferencia que este archivo defiende: ninguna fila individual del
    dataframe en km es imposible; lo imposible es que el 1% de los viajes de un
    taxi verde pase de 100 millas.
    """
    df = generar_crudos()
    df["trip_distance"] = df["trip_distance"] * MILLAS_A_KM
    with pytest.raises(Exception, match="outliers_de_distancia_son_marginales"):
        dc.validar_crudos(df)


def test_umbral_calibrado_con_la_proporcion_real() -> None:
    """El umbral deja margen sobre lo medido en datos reales.

    Medido en 2023-01: 0,054% de los viajes supera las 100 millas. Si alguien
    baja el umbral por debajo de eso, el pipeline vuelve a romperse con datos
    reales y este test lo dice antes de que pase en clase.
    """
    proporcion_real_medida = 0.00054
    assert proporcion_real_medida * 3 < dc.MAX_FRACCION_OUTLIERS, (
        "el umbral quedo demasiado cerca del ruido real de la TLC"
    )
    assert dc.MAX_FRACCION_OUTLIERS < 0.01, "un umbral tan alto ya no detecta un cambio de unidades"


# =============================================================================
# Nivel 3 — entre columnas: atrapa incoherencias
# =============================================================================
def test_velocidad_implicita_absurda_si_invalida() -> None:
    """Distancias plausibles y duraciones plausibles, relacion imposible.

    Cada columna por separado pasa cualquier check de rango. Solo mirando las
    dos juntas se ve que estos taxis irian a 300 mph.
    """
    df = generar_crudos()
    df[dc.fc.COL_DROPOFF] = df[dc.fc.COL_PICKUP] + pd.Timedelta(seconds=20)
    with pytest.raises(Exception, match="velocidad_implicita_plausible"):
        dc.validar_crudos(df)


def test_velocidad_implicita_del_fixture_valido_es_urbana() -> None:
    """Control positivo: el fixture valido tiene una velocidad de taxi real."""
    df = generar_crudos()
    minutos = (df[dc.fc.COL_DROPOFF] - df[dc.fc.COL_PICKUP]).dt.total_seconds() / 60
    mph = (df["trip_distance"] / (minutos / 60)).median()
    assert 2.0 <= mph <= 45.0, f"mediana de {mph:.1f} mph fuera de rango urbano"


# =============================================================================
# Control negativo: el check mas olvidado de todos
# =============================================================================
def test_el_contrato_no_inventa_fallos() -> None:
    """Tres lotes independientes del fixture valido pasan los tres niveles.

    Un contrato que falla con datos buenos se desactiva en la primera semana.
    """
    for semilla in (1, 2, 3):
        dc.validar_crudos(generar_crudos(semilla=semilla))
