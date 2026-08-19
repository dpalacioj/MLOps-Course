
import os
import pickle

import click
import mlflow
import numpy as np
import optuna
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error

mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("nyc-taxi-experiment-hpo")

def load_pickle(filename: str):
    with open(filename, "rb") as f_in:
        return pickle.load(f_in)

@click.command()
@click.option(
    "--data_path",
    default="./data/processed",
    help="Location where the processed NYC taxi trip data was saved"
)
def run_optimization(data_path: str):
    X_train, y_train = load_pickle(os.path.join(data_path, "X_train.pkl")), load_pickle(os.path.join(data_path, "y_train.pkl"))
    X_val, y_val = load_pickle(os.path.join(data_path, "X_val.pkl")), load_pickle(os.path.join(data_path, "y_val.pkl"))

    def objective(trial):
        with mlflow.start_run():
            params = {
                'n_estimators': trial.suggest_int('n_estimators', 10, 50, 1),
                'max_depth': trial.suggest_int('max_depth', 1, 20, 1),
                'min_samples_split': trial.suggest_int('min_samples_split', 2, 10, 1),
                'min_samples_leaf': trial.suggest_int('min_samples_leaf', 1, 4, 1),
                'random_state': 42,
                'n_jobs': -1
            }
            mlflow.log_params(params)

            rf = RandomForestRegressor(**params)
            rf.fit(X_train, y_train)
            y_pred = rf.predict(X_val)
            rmse = np.sqrt(mean_squared_error(y_val, y_pred))
            mlflow.log_metric("rmse", rmse)

        return rmse

    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    study.optimize(objective, n_trials=10)

if __name__ == '__main__':
    run_optimization()
    run_optimization()
