"""
Test de la logica core de los bloques Mage (sin depender de mage-ai).

Verifica que toda la logica de negocio funciona correctamente:
- Carga de datos NYC Taxi
- Validacion de calidad
- Creacion de features con DictVectorizer
- Optimizacion con Optuna y entrenamiento con XGBoost + MLflow

Uso:
    uv run python 03-Orchestration/Mage-pipelines/test_blocks.py
"""

import sys
import os

# Agregar el directorio del proyecto al path
PROJECT_DIR = os.path.join(os.path.dirname(__file__), 'nyc_taxi_project')
sys.path.insert(0, PROJECT_DIR)

import pandas as pd
from sklearn.feature_extraction import DictVectorizer
from utils.constants import (
    DEFAULT_YEAR, DEFAULT_MONTH,
    CATEGORICAL_FEATURES, TARGET_COLUMN,
    MIN_DURATION, MAX_DURATION, MIN_RECORDS, NULL_THRESHOLD,
    OPTUNA_TRIALS, NUM_BOOST_ROUNDS, EARLY_STOPPING_ROUNDS,
    MLFLOW_EXPERIMENT_NAME, MLFLOW_DEFAULT_URI,
)


def test_load_data():
    """Test: Carga de datos (logica de load_taxi_data.py)."""
    print("=" * 60)
    print("TEST 1: Carga de datos NYC Taxi")
    print("=" * 60)

    year, month = DEFAULT_YEAR, DEFAULT_MONTH
    url = (
        f'https://d37ci6vzurychx.cloudfront.net/trip-data/'
        f'green_tripdata_{year}-{month:02d}.parquet'
    )
    print(f"  Descargando desde: {url}")
    df = pd.read_parquet(url)

    df['duration'] = (
        df.lpep_dropoff_datetime - df.lpep_pickup_datetime
    ).dt.total_seconds() / 60
    df = df[(df.duration >= MIN_DURATION) & (df.duration <= MAX_DURATION)]
    df[CATEGORICAL_FEATURES] = df[CATEGORICAL_FEATURES].astype(str)

    assert len(df) > 0, "DataFrame vacio"
    assert 'duration' in df.columns, "Falta columna duration"
    for col in CATEGORICAL_FEATURES:
        assert col in df.columns, f"Falta columna {col}"

    print(f"  OK: {len(df):,} registros cargados")
    print(f"  Duracion promedio: {df['duration'].mean():.2f} min")
    return df


def test_validate_data(df):
    """Test: Validacion de calidad (logica de validate_data.py)."""
    print("\n" + "=" * 60)
    print("TEST 2: Validacion de datos")
    print("=" * 60)

    null_pct = df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100

    if len(df) < MIN_RECORDS:
        print(f"  WARN: Volumen bajo: {len(df)}")
    else:
        print(f"  OK: Volumen suficiente: {len(df):,}")

    if null_pct > NULL_THRESHOLD:
        print(f"  WARN: Nulos altos: {null_pct:.2f}%")
    else:
        print(f"  OK: Nulos aceptables: {null_pct:.2f}%")

    return df


def test_create_features(df):
    """Test: Ingenieria de features (logica de create_features.py)."""
    print("\n" + "=" * 60)
    print("TEST 3: Creacion de features")
    print("=" * 60)

    # Cargar datos de validacion
    year, month = DEFAULT_YEAR, DEFAULT_MONTH
    next_year = year if month < 12 else year + 1
    next_month = month + 1 if month < 12 else 1

    val_url = (
        f'https://d37ci6vzurychx.cloudfront.net/trip-data/'
        f'green_tripdata_{next_year}-{next_month:02d}.parquet'
    )
    print(f"  Cargando validacion: {next_year}-{next_month:02d}")
    df_val = pd.read_parquet(val_url)
    df_val['duration'] = (
        df_val.lpep_dropoff_datetime - df_val.lpep_pickup_datetime
    ).dt.total_seconds() / 60
    df_val = df_val[(df_val.duration >= 1) & (df_val.duration <= 60)]
    df_val[CATEGORICAL_FEATURES] = df_val[CATEGORICAL_FEATURES].astype(str)

    # DictVectorizer
    train_dicts = df[CATEGORICAL_FEATURES].to_dict(orient='records')
    val_dicts = df_val[CATEGORICAL_FEATURES].to_dict(orient='records')

    dv = DictVectorizer()
    X_train = dv.fit_transform(train_dicts)
    X_val = dv.transform(val_dicts)

    y_train = df[TARGET_COLUMN].values
    y_val = df_val[TARGET_COLUMN].values

    assert X_train.shape[0] == len(y_train)
    assert X_val.shape[0] == len(y_val)
    assert X_train.shape[1] == X_val.shape[1]

    print(f"  OK: X_train={X_train.shape}, X_val={X_val.shape}")
    print(f"  Features: {X_train.shape[1]}")
    return X_train, y_train, X_val, y_val, dv


def test_train_model(X_train, y_train, X_val, y_val, dv):
    """Test: Optimizacion + entrenamiento (logica de train_model.py)."""
    print("\n" + "=" * 60)
    print("TEST 4: Optuna + XGBoost + MLflow")
    print("=" * 60)

    import xgboost as xgb
    import optuna
    import mlflow
    from sklearn.metrics import root_mean_squared_error

    # Setup MLflow
    mlflow.set_tracking_uri(MLFLOW_DEFAULT_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
    print(f"  MLflow: {MLFLOW_DEFAULT_URI}")

    # Optuna con pocos trials para test rapido
    n_trials = 3  # Reducido para test
    print(f"  Optuna: {n_trials} trials (reducido para test)")

    def objective(trial):
        params = {
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'min_child_weight': trial.suggest_float('min_child_weight', 1, 10),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 0.0, 1.0),
            'reg_lambda': trial.suggest_float('reg_lambda', 0.0, 1.0),
            'objective': 'reg:squarederror',
            'seed': 42
        }
        with mlflow.start_run(nested=True, run_name=f"trial_{trial.number}"):
            mlflow.log_params(params)
            dtrain = xgb.DMatrix(X_train, label=y_train)
            dval = xgb.DMatrix(X_val, label=y_val)
            model = xgb.train(
                params, dtrain, num_boost_round=50,
                evals=[(dval, 'validation')],
                early_stopping_rounds=10, verbose_eval=False
            )
            preds = model.predict(dval)
            rmse = root_mean_squared_error(y_val, preds)
            mlflow.log_metric("rmse", rmse)
        return rmse

    study = optuna.create_study(direction='minimize')
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_params = study.best_params
    best_params['objective'] = 'reg:squarederror'
    best_params['seed'] = 42

    print(f"  Mejor RMSE Optuna: {study.best_value:.4f}")

    # Entrenar modelo final
    with mlflow.start_run() as run:
        mlflow.log_params(best_params)
        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)
        booster = xgb.train(
            best_params, dtrain, num_boost_round=NUM_BOOST_ROUNDS,
            evals=[(dval, 'validation')],
            early_stopping_rounds=EARLY_STOPPING_ROUNDS
        )
        preds = booster.predict(dval)
        rmse = root_mean_squared_error(y_val, preds)
        mlflow.log_metric("rmse", rmse)
        mlflow.set_tag("pipeline", "mage-test")
        run_id = run.info.run_id

    assert rmse > 0, "RMSE debe ser positivo"
    assert run_id is not None, "run_id no debe ser None"

    print(f"  OK: RMSE final = {rmse:.4f}")
    print(f"  MLflow run_id: {run_id}")
    return run_id, rmse


def main():
    print("\n" + "#" * 60)
    print("# TEST DE BLOQUES MAGE (logica core sin mage-ai)")
    print("#" * 60 + "\n")

    # Test secuencial (simula el pipeline)
    df = test_load_data()
    df = test_validate_data(df)
    X_train, y_train, X_val, y_val, dv = test_create_features(df)
    run_id, rmse = test_train_model(X_train, y_train, X_val, y_val, dv)

    print("\n" + "#" * 60)
    print("# TODOS LOS TESTS PASARON")
    print(f"# RMSE: {rmse:.4f} | MLflow run: {run_id}")
    print("#" * 60)


if __name__ == "__main__":
    main()
