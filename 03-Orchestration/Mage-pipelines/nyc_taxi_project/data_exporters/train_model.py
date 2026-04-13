"""
Data Exporter: Optimizacion de hiperparametros y entrenamiento del modelo.

Este bloque es el equivalente a optimize_hyperparameters() + train_model()
del pipeline Prefect. En Mage, un @data_exporter es el paso final del pipeline
(exportar/guardar resultados).

Usa Optuna para optimizar XGBoost y MLflow para registrar experimentos.
"""

import pickle
from pathlib import Path
from typing import Tuple

import xgboost as xgb
import optuna
import mlflow
from sklearn.metrics import root_mean_squared_error

if 'data_exporter' not in globals():
    from mage_ai.data_preparation.decorators import data_exporter
if 'test' not in globals():
    from mage_ai.data_preparation.decorators import test

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.constants import (
    OPTUNA_TRIALS, NUM_BOOST_ROUNDS, EARLY_STOPPING_ROUNDS,
    MLFLOW_EXPERIMENT_NAME, MLFLOW_DEFAULT_URI
)


def _setup_mlflow():
    """Configura MLflow con SQLite local."""
    mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", MLFLOW_DEFAULT_URI)
    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
    print(f"MLflow configurado: {mlflow_uri}")
    print(f"Experimento: {MLFLOW_EXPERIMENT_NAME}")


@data_exporter
def train_and_export_model(data: Tuple, *args, **kwargs) -> dict:
    """
    Optimiza hiperparametros con Optuna y entrena modelo final con XGBoost.

    Recibe la tupla (X_train, y_train, X_val, y_val, dv) del bloque anterior.
    1. Ejecuta N trials de Optuna, cada uno logueado como nested run en MLflow
    2. Entrena modelo final con los mejores hiperparametros
    3. Guarda modelo y preprocesador

    Args:
        data: Tupla con matrices de features, targets y DictVectorizer.

    Returns:
        Diccionario con resultados del entrenamiento.
    """
    X_train, y_train, X_val, y_val, dv = data

    _setup_mlflow()

    # ----- Paso 1: Optimizacion con Optuna -----
    n_trials = kwargs.get('n_trials', OPTUNA_TRIALS)
    print(f"\nIniciando optimizacion con {n_trials} trials de Optuna...")

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
                params, dtrain,
                num_boost_round=100,
                evals=[(dval, 'validation')],
                early_stopping_rounds=10,
                verbose_eval=False
            )

            preds = model.predict(dval)
            rmse = root_mean_squared_error(y_val, preds)

            mlflow.log_metric("rmse", rmse)
            mlflow.set_tag("trial_type", "optuna_optimization")

        return rmse

    study = optuna.create_study(
        direction='minimize',
        study_name='xgboost-optimization-mage'
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    best_params = study.best_params
    best_params['objective'] = 'reg:squarederror'
    best_params['seed'] = 42

    print(f"\nMejor RMSE en optimizacion: {study.best_value:.4f}")
    print(f"Mejor trial: #{study.best_trial.number}")

    # ----- Paso 2: Entrenar modelo final -----
    print(f"\nEntrenando modelo final con parametros optimizados...")

    with mlflow.start_run() as run:
        mlflow.log_params(best_params)

        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)

        booster = xgb.train(
            params=best_params,
            dtrain=dtrain,
            num_boost_round=NUM_BOOST_ROUNDS,
            evals=[(dval, 'validation')],
            early_stopping_rounds=EARLY_STOPPING_ROUNDS
        )

        y_pred = booster.predict(dval)
        rmse = root_mean_squared_error(y_val, y_pred)
        mlflow.log_metric("rmse", rmse)

        # Guardar preprocesador
        models_dir = Path('models')
        models_dir.mkdir(exist_ok=True)

        preprocessor_path = models_dir / "preprocessor.b"
        with open(preprocessor_path, "wb") as f:
            pickle.dump(dv, f)

        mlflow.log_artifact(str(preprocessor_path), artifact_path="preprocessor")
        mlflow.xgboost.log_model(booster, "models_mlflow")

        mlflow.set_tag("pipeline", "mage")
        mlflow.set_tag("best_optuna_rmse", f"{study.best_value:.4f}")

        run_id = run.info.run_id

    # ----- Resumen -----
    results = {
        'run_id': run_id,
        'rmse': rmse,
        'best_optuna_rmse': study.best_value,
        'n_trials': n_trials,
        'best_params': best_params,
        'train_samples': X_train.shape[0],
        'val_samples': X_val.shape[0],
        'n_features': X_train.shape[1],
    }

    print(f"\n{'='*50}")
    print(f"PIPELINE COMPLETADO")
    print(f"{'='*50}")
    print(f"RMSE final:          {rmse:.4f}")
    print(f"MLflow Run ID:       {run_id}")
    print(f"Muestras train:      {X_train.shape[0]:,}")
    print(f"Muestras validacion: {X_val.shape[0]:,}")
    print(f"Numero de features:  {X_train.shape[1]:,}")
    print(f"{'='*50}")

    return results


@test
def test_output(output, *args) -> None:
    """Verifica que el modelo se entreno correctamente."""
    assert output is not None, 'El output es None'
    assert 'run_id' in output, 'Falta run_id en los resultados'
    assert 'rmse' in output, 'Falta rmse en los resultados'
    assert output['rmse'] > 0, 'RMSE debe ser positivo'
    print(f"Test OK: RMSE={output['rmse']:.4f}, run_id={output['run_id']}")
