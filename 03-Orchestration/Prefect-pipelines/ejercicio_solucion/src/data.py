"""
Carga y preparacion de datos.
Usamos el dataset Iris que viene incluido en scikit-learn.
"""

import pandas as pd
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split
from prefect import task, get_run_logger

from .config import TEST_SIZE, RANDOM_STATE


@task(name="cargar_datos", description="Carga el dataset Iris desde sklearn")
def cargar_datos() -> pd.DataFrame:
    """Carga el dataset Iris y lo convierte a DataFrame."""
    logger = get_run_logger()

    iris = load_iris()
    df = pd.DataFrame(iris.data, columns=iris.feature_names)
    df["target"] = iris.target

    logger.info(f"Dataset cargado: {len(df)} registros, {df.shape[1] - 1} features")
    logger.info(f"Clases: {list(iris.target_names)}")
    return df


@task(name="dividir_datos", description="Divide en conjuntos de entrenamiento y prueba")
def dividir_datos(df: pd.DataFrame):
    """Separa features (X) del target (y) y divide en train/test."""
    logger = get_run_logger()

    X = df.drop("target", axis=1)
    y = df["target"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )

    logger.info(f"Train: {len(X_train)} registros | Test: {len(X_test)} registros")
    return X_train, X_test, y_train, y_test
