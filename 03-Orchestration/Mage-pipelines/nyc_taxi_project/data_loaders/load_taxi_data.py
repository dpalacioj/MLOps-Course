"""
Data Loader: Descarga datos de NYC Taxi desde la nube.

Este bloque es el equivalente a read_dataframe() del pipeline Prefect.
En Mage, un @data_loader es el punto de entrada del pipeline.
"""

import pandas as pd

# Guard para que funcione tanto dentro de Mage como standalone
if 'data_loader' not in globals():
    from mage_ai.data_preparation.decorators import data_loader
if 'test' not in globals():
    from mage_ai.data_preparation.decorators import test

import sys
from mage_ai.data_preparation.repo_manager import get_repo_path
sys.path.append(get_repo_path())
from utils.constants import (
    DEFAULT_YEAR, DEFAULT_MONTH,
    CATEGORICAL_FEATURES, MIN_DURATION, MAX_DURATION
)


@data_loader
def load_taxi_data(*args, **kwargs) -> pd.DataFrame:
    """
    Descarga datos de viajes de taxi de NYC desde archivos Parquet publicos.

    - Calcula la duracion del viaje en minutos
    - Filtra viajes entre 1 y 60 minutos
    - Convierte features categoricas a string

    Returns:
        DataFrame con datos de viajes de taxi filtrados.
    """
    year = kwargs.get('year', DEFAULT_YEAR)
    month = kwargs.get('month', DEFAULT_MONTH)

    url = (
        f'https://d37ci6vzurychx.cloudfront.net/trip-data/'
        f'green_tripdata_{year}-{month:02d}.parquet'
    )
    print(f"Descargando datos desde: {url}")

    df = pd.read_parquet(url)

    # Calcular duracion en minutos
    df['duration'] = (
        df.lpep_dropoff_datetime - df.lpep_pickup_datetime
    ).dt.total_seconds() / 60

    # Filtrar por duracion razonable
    registros_antes = len(df)
    df = df[(df.duration >= MIN_DURATION) & (df.duration <= MAX_DURATION)]
    registros_despues = len(df)

    # Convertir features categoricas
    df[CATEGORICAL_FEATURES] = df[CATEGORICAL_FEATURES].astype(str)

    print(f"Registros cargados: {registros_despues:,} "
          f"(filtrados {registros_antes - registros_despues:,})")
    print(f"Periodo: {year}-{month:02d}")
    print(f"Duracion promedio: {df['duration'].mean():.2f} min")

    return df


@test
def test_output(output, *args) -> None:
    """Verifica que el DataFrame no este vacio y tenga las columnas esperadas."""
    assert output is not None, 'El output es None'
    assert len(output) > 0, 'El DataFrame esta vacio'
    assert 'duration' in output.columns, 'Falta la columna duration'
    for col in CATEGORICAL_FEATURES:
        assert col in output.columns, f'Falta la columna {col}'
    print(f"Test OK: {len(output):,} registros cargados correctamente")
