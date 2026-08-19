"""Fixtures compartidos.

Dos formas de construir datos de prueba, y las dos hacen falta:

- **sinteticos deterministas** (``df_valido``): rapidos, sin archivos, sirven
  para probar logica.
- **archivos versionados** (``tests/fixtures/*.csv``): documentan como se ve el
  dato real y —el punto importante— permiten tener un fixture ROTO A PROPOSITO
  con el que verificar que el contrato lo rechaza. Un contrato que nunca se ve
  fallar no prueba nada.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

SEMILLA_TEST = 7


@pytest.fixture
def df_crudo() -> pd.DataFrame:
    """Dataframe crudo valido, determinista y con nulos reales.

    Los nulos estan a proposito: un fixture sin nulos hace que la estrategia de
    imputacion no se ejercite nunca y el bug aparezca en produccion.
    """
    rng = np.random.default_rng(SEMILLA_TEST)
    n = 600
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2023-01-01", periods=n, freq="h"),
            "categoria": rng.choice(["A", "B", "C"], size=n),
            "region": rng.choice(["norte", "sur", "centro"], size=n),
            "canal": rng.choice(["web", "tienda"], size=n),
            "cantidad": rng.integers(1, 20, size=n).astype(float),
            "precio_unitario": rng.uniform(1_000, 90_000, size=n).round(2),
            "descuento": rng.choice([0.0, 0.05, 0.1, 0.2], size=n),
        }
    )
    # Nulos reales, en las columnas donde el proveedor los manda de verdad.
    df.loc[df.index[:20], "cantidad"] = np.nan
    df.loc[df.index[30:40], "categoria"] = None
    df["objetivo"] = df["cantidad"].fillna(1) * df["precio_unitario"] * (
        1 - df["descuento"]
    ) + rng.normal(0, 500, size=n)
    return df


@pytest.fixture
def df_produccion(df_crudo: pd.DataFrame) -> pd.DataFrame:
    """Particion de "produccion" con drift deliberado en dos columnas.

    Sirve para verificar que el detector de drift detecta lo que debe y —igual de
    importante— que NO grita por las columnas que no cambiaron.
    """
    rng = np.random.default_rng(SEMILLA_TEST + 1)
    df = df_crudo.copy()
    df["ts"] = df["ts"] + pd.Timedelta(days=180)
    # Drift numerico: el precio sube un 60%.
    df["precio_unitario"] = df["precio_unitario"] * 1.6
    # Drift categorico: aparece un canal nuevo y se desplaza el mix.
    df["canal"] = rng.choice(["web", "tienda", "app"], size=len(df), p=[0.2, 0.2, 0.6])
    return df


@pytest.fixture
def ruta_fixture_valido() -> Path:
    return FIXTURES / "muestra-valida.csv"


@pytest.fixture
def ruta_fixture_roto() -> Path:
    return FIXTURES / "muestra-rota.csv"
