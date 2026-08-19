
import os
import pickle
import click
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error

def load_pickle(filename: str):
    with open(filename, "rb") as f_in:
        return pickle.load(f_in)

@click.command()
@click.option(
    "--data_path",
    default="./data/processed",
    help="Location where the processed NYC taxi trip data was saved"
)
def run_train(data_path: str):
    X_train, y_train = load_pickle(os.path.join(data_path, "X_train.pkl")), load_pickle(os.path.join(data_path, "y_train.pkl"))
    X_val, y_val = load_pickle(os.path.join(data_path, "X_val.pkl")), load_pickle(os.path.join(data_path, "y_val.pkl"))

    rf = RandomForestRegressor(max_depth=10, random_state=0)
    rf.fit(X_train, y_train)
    y_pred = rf.predict(X_val)

    rmse = np.sqrt(mean_squared_error(y_val, y_pred))
    print(f"RMSE: {rmse}")

if __name__ == '__main__':
    run_train()
