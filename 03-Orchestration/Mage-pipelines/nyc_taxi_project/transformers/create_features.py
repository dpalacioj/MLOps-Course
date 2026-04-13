"""
Transformer: Ingenieria de features.

Este bloque es el equivalente a create_features() del pipeline Prefect.
Usa DictVectorizer para crear matrices sparse a partir de features categoricas.
"""

from typing import Tuple

import pandas as pd
from sklearn.feature_extraction import DictVectorizer

if 'transformer' not in globals():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in globals():
    from mage_ai.data_preparation.decorators import test

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.constants import CATEGORICAL_FEATURES, TARGET_COLUMN


@transformer
def create_features(df: pd.DataFrame, *args, **kwargs) -> Tuple:
    """
    Crea la matriz de features usando DictVectorizer.

    Separa los datos en train/val (datos del mes actual vs siguiente),
    ajusta el DictVectorizer y transforma ambos conjuntos.

    En Mage, retornamos una tupla con todo lo necesario para el
    siguiente bloque (entrenamiento).

    Args:
        df: DataFrame validado con datos de taxi.

    Returns:
        Tupla (X_train, y_train, X_val, y_val, dv) con las matrices
        de features, targets, y el vectorizador ajustado.
    """
    year = kwargs.get('year', 2025)
    month = kwargs.get('month', 1)

    # Calcular periodo de validacion
    next_year = year if month < 12 else year + 1
    next_month = month + 1 if month < 12 else 1

    # Cargar datos de validacion
    val_url = (
        f'https://d37ci6vzurychx.cloudfront.net/trip-data/'
        f'green_tripdata_{next_year}-{next_month:02d}.parquet'
    )
    print(f"Cargando datos de validacion: {next_year}-{next_month:02d}")

    df_val = pd.read_parquet(val_url)
    df_val['duration'] = (
        df_val.lpep_dropoff_datetime - df_val.lpep_pickup_datetime
    ).dt.total_seconds() / 60
    df_val = df_val[(df_val.duration >= 1) & (df_val.duration <= 60)]
    df_val[CATEGORICAL_FEATURES] = df_val[CATEGORICAL_FEATURES].astype(str)

    # Crear diccionarios de features
    train_dicts = df[CATEGORICAL_FEATURES].to_dict(orient='records')
    val_dicts = df_val[CATEGORICAL_FEATURES].to_dict(orient='records')

    # Ajustar DictVectorizer con datos de entrenamiento
    dv = DictVectorizer()
    X_train = dv.fit_transform(train_dicts)
    X_val = dv.transform(val_dicts)

    # Extraer targets
    y_train = df[TARGET_COLUMN].values
    y_val = df_val[TARGET_COLUMN].values

    print(f"Features de entrenamiento: {X_train.shape}")
    print(f"Features de validacion:    {X_val.shape}")
    print(f"Numero de features:        {X_train.shape[1]}")

    return X_train, y_train, X_val, y_val, dv


@test
def test_output(output, *args) -> None:
    """Verifica que las matrices de features se crearon correctamente."""
    assert output is not None, 'El output es None'
    X_train, y_train, X_val, y_val, dv = output
    assert X_train.shape[0] > 0, 'X_train esta vacio'
    assert X_train.shape[0] == len(y_train), 'X_train y y_train no coinciden'
    assert X_val.shape[0] == len(y_val), 'X_val y y_val no coinciden'
    assert X_train.shape[1] == X_val.shape[1], 'Diferente num de features'
    print(f"Test OK: train={X_train.shape}, val={X_val.shape}")
