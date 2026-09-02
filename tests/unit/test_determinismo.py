"""Reproducibilidad del muestreo y de los generadores aleatorios.

Por que merece tests propios: "reproducible" es la primera promesa del curso y la
mas facil de romper sin darse cuenta. Basta un `df.sample()` sin `random_state`,
o un `np.random.seed()` global que otro modulo pisa, para que dos corridas del
mismo comando den metricas distintas. Cuando eso pasa, ninguna comparacion de
modelos significa nada y el problema tarda semanas en atribuirse.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from taxi.config import PARTICION_TEST, SEMILLA
from taxi.data import loaders
from taxi.features import contract as fc
from tests.conftest import generar_crudos


@pytest.fixture
def sin_red(monkeypatch: pytest.MonkeyPatch, parquet_crudo: Path) -> Path:
    monkeypatch.setattr(loaders, "descargar_particion", lambda particion, **kwargs: parquet_crudo)
    return parquet_crudo


def test_el_muestreo_es_deterministico(sin_red: Path) -> None:
    """Dos preparaciones de la misma particion dan exactamente el mismo dataframe."""
    primera = loaders.preparar_particion(PARTICION_TEST, filas=400)
    segunda = loaders.preparar_particion(PARTICION_TEST, filas=400)
    assert len(primera) == 400
    pd.testing.assert_frame_equal(primera, segunda)


def test_el_muestreo_usa_la_semilla_de_config(sin_red: Path, df_crudo_valido: pd.DataFrame) -> None:
    """La muestra debe coincidir con la que produce config.SEMILLA.

    Si alguien cambia el random_state del loader por otro valor, o lo quita, este
    test falla. Es la unica forma de verificar que la semilla que se documenta es
    la que de verdad se usa.
    """
    df = loaders.preparar_particion(PARTICION_TEST, filas=300)

    esperado = df_crudo_valido.copy()
    esperado[fc.TARGET_REGRESION] = (
        esperado[fc.COL_DROPOFF] - esperado[fc.COL_PICKUP]
    ).dt.total_seconds() / 60.0
    esperado = esperado.reset_index(drop=True).sample(n=300, random_state=SEMILLA)

    assert df[fc.TARGET_REGRESION].sum() == pytest.approx(
        esperado[fc.TARGET_REGRESION].sum(), rel=1e-9
    )


def test_semillas_distintas_dan_muestras_distintas(sin_red: Path) -> None:
    """Control negativo: sin esto, el test anterior pasaria con datos constantes."""
    df = loaders.preparar_particion(PARTICION_TEST, filas=300)
    otra = generar_crudos(filas=1_200, semilla=SEMILLA + 1)
    otra[fc.TARGET_REGRESION] = (
        otra[fc.COL_DROPOFF] - otra[fc.COL_PICKUP]
    ).dt.total_seconds() / 60.0
    assert df[fc.TARGET_REGRESION].sum() != pytest.approx(
        otra.sample(n=300, random_state=SEMILLA + 1)[fc.TARGET_REGRESION].sum(), rel=1e-6
    )


def test_los_fixtures_se_generan_de_forma_reproducible() -> None:
    """El generador de datos de prueba es tan reproducible como el pipeline."""
    pd.testing.assert_frame_equal(generar_crudos(), generar_crudos())
    assert not generar_crudos(semilla=1).equals(generar_crudos(semilla=2))


def test_los_graficos_no_dependen_del_estado_global_de_numpy() -> None:
    """El submuestreo de residuales usa un Generator propio, no np.random.seed().

    Un `np.random.seed()` a nivel de modulo es estado global compartido: el orden
    en que se importan los modulos cambia los resultados, y el bug es
    practicamente indiagnosticable. Aqui se comprueba que alterar el estado
    global no afecta al resultado.
    """
    from taxi.models.train import _figura_residuales

    y_true = np.linspace(1.0, 60.0, 8_000)
    y_pred = y_true * 1.05

    np.random.seed(1)
    primera = _figura_residuales(y_true, y_pred)
    np.random.seed(999)
    segunda = _figura_residuales(y_true, y_pred)

    datos_primera = primera.axes[0].collections[0].get_offsets()
    datos_segunda = segunda.axes[0].collections[0].get_offsets()
    np.testing.assert_array_equal(datos_primera, datos_segunda)
