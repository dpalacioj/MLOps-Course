"""
Entrenamiento del modelo y registro en MLflow.
"""

import pickle
from pathlib import Path

import mlflow
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from prefect import task, get_run_logger

from .config import N_ESTIMATORS, MAX_DEPTH, RANDOM_STATE


@task(name="entrenar_modelo", description="Entrena RandomForest y registra en MLflow")
def entrenar_modelo(X_train, y_train, X_test, y_test, scaler):
    """Entrena un RandomForest, evalua y registra todo en MLflow."""
    logger = get_run_logger()

    with mlflow.start_run() as run:
        # 1. Registrar parametros
        mlflow.log_param("n_estimators", N_ESTIMATORS)
        mlflow.log_param("max_depth", MAX_DEPTH)
        mlflow.log_param("random_state", RANDOM_STATE)
        mlflow.log_param("modelo", "RandomForestClassifier")

        # 2. Entrenar modelo
        modelo = RandomForestClassifier(
            n_estimators=N_ESTIMATORS,
            max_depth=MAX_DEPTH,
            random_state=RANDOM_STATE,
        )
        modelo.fit(X_train, y_train)

        # 3. Evaluar
        y_pred = modelo.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)

        # 4. Registrar metricas
        mlflow.log_metric("accuracy", accuracy)

        # 5. Registrar modelo
        mlflow.sklearn.log_model(modelo, "modelo_random_forest")

        # 6. Guardar scaler como artefacto
        models_dir = Path("models")
        models_dir.mkdir(exist_ok=True)
        scaler_path = models_dir / "scaler.pkl"
        with open(scaler_path, "wb") as f:
            pickle.dump(scaler, f)
        mlflow.log_artifact(str(scaler_path))

        logger.info(f"Accuracy: {accuracy:.4f}")
        logger.info(f"MLflow Run ID: {run.info.run_id}")

        return run.info.run_id, accuracy
