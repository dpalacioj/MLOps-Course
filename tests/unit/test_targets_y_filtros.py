"""Calculo de los targets y filtro de duracion, sin red.

Se ejercita ``loaders.preparar_particion`` completo —contratos, target, filtro,
muestreo y features— parcheando unicamente la descarga. Testear el pipeline real
y no una reimplementacion es el punto: una copia de la logica en el test pasaria
verde mientras el codigo de produccion se rompe.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from taxi.config import (
    DURACION_MAX_MIN,
    DURACION_MIN_MIN,
    PARTICION_TEST,
    UMBRAL_VIAJE_LARGO_MIN,
)
from taxi.data import loaders
from taxi.features import contract as fc


@pytest.fixture
def sin_red(monkeypatch: pytest.MonkeyPatch, parquet_crudo: Path) -> Path:
    """Parchea la descarga para que devuelva el parquet local del fixture."""
    monkeypatch.setattr(
        loaders,
        "descargar_particion",
        lambda particion, **kwargs: parquet_crudo,
    )
    return parquet_crudo


def test_duration_se_calcula_en_minutos(sin_red: Path, df_crudo_valido: pd.DataFrame) -> None:
    """duration = (dropoff - pickup) en minutos, no en segundos ni en horas."""
    df = loaders.preparar_particion(PARTICION_TEST, filas=None)
    esperado_medio = (
        (df_crudo_valido[fc.COL_DROPOFF] - df_crudo_valido[fc.COL_PICKUP]).dt.total_seconds() / 60.0
    ).mean()
    assert df[fc.TARGET_REGRESION].mean() == pytest.approx(esperado_medio, rel=1e-9)


def test_el_filtro_de_duracion_elimina_los_extremos(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    df_crudo_con_duraciones_extremas: pd.DataFrame,
) -> None:
    """Viajes de 0.5 min y de 90 min son errores de captura, no viajes.

    Se comprueba que se van (cambia el conteo) y que el resultado queda dentro
    del rango: un filtro que deja pasar el borde superior mete al modelo casos
    que no puede predecir.
    """
    ruta = tmp_path / "extremos.parquet"
    df_crudo_con_duraciones_extremas.to_parquet(ruta, index=False)
    monkeypatch.setattr(loaders, "descargar_particion", lambda particion, **kwargs: ruta)

    df = loaders.preparar_particion(PARTICION_TEST, filas=None)

    assert len(df) == len(df_crudo_con_duraciones_extremas) - 4
    assert df[fc.TARGET_REGRESION].min() >= DURACION_MIN_MIN
    assert df[fc.TARGET_REGRESION].max() <= DURACION_MAX_MIN


def test_viaje_largo_usa_el_umbral_de_config(sin_red: Path) -> None:
    """viaje_largo = 1 si y solo si duration > UMBRAL_VIAJE_LARGO_MIN."""
    df = loaders.preparar_particion(PARTICION_TEST, filas=None)
    esperado = (df[fc.TARGET_REGRESION] > UMBRAL_VIAJE_LARGO_MIN).astype("int8")
    pd.testing.assert_series_equal(
        df[fc.TARGET_CLASIFICACION], esperado, check_names=False, check_dtype=False
    )
    # Umbral estricto: un viaje de exactamente 30 min NO es largo.
    assert (
        df.loc[df[fc.TARGET_REGRESION] <= UMBRAL_VIAJE_LARGO_MIN, fc.TARGET_CLASIFICACION]
        .eq(0)
        .all()
    )


def test_ambas_clases_del_target_binario_estan_presentes(sin_red: Path) -> None:
    """Si el target fuera constante, cualquier clasificador daria 100%."""
    df = loaders.preparar_particion(PARTICION_TEST, filas=None)
    assert set(df[fc.TARGET_CLASIFICACION].unique()) == {0, 1}


def test_preparar_particion_devuelve_solo_las_columnas_del_contrato(sin_red: Path) -> None:
    df = loaders.preparar_particion(PARTICION_TEST, filas=None)
    esperadas = {*fc.FEATURES, fc.TARGET_REGRESION, fc.TARGET_CLASIFICACION, fc.COL_PICKUP}
    assert set(df.columns) == esperadas
