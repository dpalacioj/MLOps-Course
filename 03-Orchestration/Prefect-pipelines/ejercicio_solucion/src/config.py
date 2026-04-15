"""
Configuracion del pipeline de clasificacion.
Aqui centralizamos todas las constantes y parametros.
"""

# --- MLflow ---
MLFLOW_EXPERIMENT_NAME = "iris-clasificacion-prefect"
MLFLOW_TRACKING_URI = "sqlite:///mlflow.db"

# --- Datos ---
TEST_SIZE = 0.2
RANDOM_STATE = 42

# --- Modelo (RandomForest) ---
N_ESTIMATORS = 100
MAX_DEPTH = 5
