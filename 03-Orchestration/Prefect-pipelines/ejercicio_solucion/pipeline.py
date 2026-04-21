"""
Pipeline principal de clasificacion Iris con Prefect + MLflow.
Orquesta todos los pasos: carga, division, features, entrenamiento.
"""

import mlflow
from prefect import flow, get_run_logger

from src.config import MLFLOW_EXPERIMENT_NAME, MLFLOW_TRACKING_URI
from src.data import cargar_datos, dividir_datos
from src.features import escalar_features
from src.models import entrenar_modelo


@flow(name="Iris Classification Pipeline", log_prints=True)
def clasificacion_flow():
    """Flow principal que conecta todos los pasos del pipeline."""
    logger = get_run_logger()

    # Configurar MLflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    # Paso 1: Cargar datos
    df = cargar_datos()

    # Paso 2: Dividir en train/test
    X_train, X_test, y_train, y_test = dividir_datos(df)

    # Paso 3: Escalar features
    X_train_scaled, X_test_scaled, scaler = escalar_features(X_train, X_test)

    # Paso 4: Entrenar modelo y registrar en MLflow
    run_id, accuracy = entrenar_modelo(
        X_train_scaled, y_train, X_test_scaled, y_test, scaler
    )

    logger.info(f"Pipeline completado! Accuracy: {accuracy:.4f}")
    logger.info(f"MLflow Run ID: {run_id}")

    return run_id


if __name__ == "__main__":
    clasificacion_flow()
