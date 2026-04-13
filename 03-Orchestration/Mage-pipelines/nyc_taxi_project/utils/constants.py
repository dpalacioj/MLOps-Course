"""
Constantes de configuracion del pipeline NYC Taxi.
Identicas a las del pipeline Prefect para comparacion directa.
"""

# Datos
DEFAULT_YEAR = 2025
DEFAULT_MONTH = 1
MIN_RECORDS = 1000
NULL_THRESHOLD = 10.0

# Modelo
OPTUNA_TRIALS = 20
NUM_BOOST_ROUNDS = 30
EARLY_STOPPING_ROUNDS = 50

# MLflow
MLFLOW_EXPERIMENT_NAME = "nyc-taxi-experiment-mage"
MLFLOW_DEFAULT_URI = "sqlite:///mlflow.db"

# Features
CATEGORICAL_FEATURES = ['PULocationID', 'DOLocationID']
TARGET_COLUMN = 'duration'

# Calidad de datos
MIN_DURATION = 1
MAX_DURATION = 60
