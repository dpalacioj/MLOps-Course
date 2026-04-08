"""
Preprocesamiento de datos - NYC Green Taxi Trip Data (2023)

Este script descarga, limpia y transforma los datos de viajes en taxi
para ser usados en los notebooks de experiment tracking con MLflow.

Fuente de datos: NYC Taxi & Limousine Commission (TLC)
https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page

Uso:
    python preprocess_data.py

Salida (en data/processed/):
    - X_train.pkl  : matriz dispersa de features (enero 2023)
    - y_train.pkl  : target de entrenamiento (duracion en minutos)
    - X_val.pkl    : matriz dispersa de features (febrero 2023)
    - y_val.pkl    : target de validacion (duracion en minutos)
    - dv.pkl       : DictVectorizer ajustado (necesario para transformar nuevos datos)
"""

import os
import pickle
import urllib.request

import pandas as pd
from sklearn.feature_extraction import DictVectorizer

# --- Configuracion del dataset ---
BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
TRAIN_DATASET = "green_tripdata_2023-01.parquet"  # Enero -> entrenamiento
VAL_DATASET = "green_tripdata_2023-02.parquet"    # Febrero -> validacion

# Features que usaremos para el modelo
CATEGORICAL_FEATURES = ['PULocationID', 'DOLocationID']  # Zona de recogida y destino
NUMERICAL_FEATURES = ['trip_distance']                    # Distancia del viaje
TARGET = 'duration'                                       # Variable objetivo: duracion en minutos

# Filtros de calidad: descartamos viajes muy cortos o muy largos
MIN_DURATION_MINUTES = 1
MAX_DURATION_MINUTES = 60


def download_data(url, filename):
    """Descarga un archivo desde una URL si no existe localmente."""
    if os.path.exists(filename):
        print(f"  Ya existe {filename}, se omite la descarga")
        return
    print(f"  Descargando {url}...")
    try:
        urllib.request.urlretrieve(url, filename)
        print(f"  Descargado -> {filename}")
    except Exception as e:
        print(f"  Error descargando {filename}: {e}")
        raise


def compute_duration(df):
    """Calcula la duracion del viaje en minutos a partir de las columnas de fecha."""
    df['duration'] = df.lpep_dropoff_datetime - df.lpep_pickup_datetime
    df['duration'] = df['duration'].apply(lambda td: td.total_seconds() / 60)
    return df


def filter_outliers(df):
    """Filtra viajes con duraciones fuera del rango esperado (1-60 min)."""
    before = len(df)
    df = df[(df.duration >= MIN_DURATION_MINUTES) & (df.duration <= MAX_DURATION_MINUTES)]
    removed = before - len(df)
    print(f"  Filtrados {removed} viajes fuera de rango ({MIN_DURATION_MINUTES}-{MAX_DURATION_MINUTES} min)")
    return df


def preprocess_data(data_path, output_path):
    """
    Pipeline completo de preprocesamiento:
    1. Descarga los datos crudos de la TLC
    2. Calcula la duracion y filtra outliers
    3. Vectoriza features categoricas y numericas
    4. Guarda los artefactos en pickle
    """
    os.makedirs(data_path, exist_ok=True)
    os.makedirs(output_path, exist_ok=True)

    # --- 1. Descarga ---
    print("Paso 1: Descarga de datos")
    train_file = os.path.join(data_path, "jan.parquet")
    val_file = os.path.join(data_path, "feb.parquet")
    download_data(f"{BASE_URL}/{TRAIN_DATASET}", train_file)
    download_data(f"{BASE_URL}/{VAL_DATASET}", val_file)

    # --- 2. Carga y limpieza ---
    print("Paso 2: Limpieza de datos")
    df_train = pd.read_parquet(train_file)
    df_val = pd.read_parquet(val_file)

    print(f"  Train (enero):  {len(df_train)} registros")
    print(f"  Val (febrero):  {len(df_val)} registros")

    df_train = compute_duration(df_train)
    df_val = compute_duration(df_val)

    print("  Filtrando train:")
    df_train = filter_outliers(df_train)
    print("  Filtrando val:")
    df_val = filter_outliers(df_val)

    # --- 3. Vectorizacion de features ---
    print("Paso 3: Vectorizacion de features")
    df_train[CATEGORICAL_FEATURES] = df_train[CATEGORICAL_FEATURES].astype(str)
    df_val[CATEGORICAL_FEATURES] = df_val[CATEGORICAL_FEATURES].astype(str)

    all_features = CATEGORICAL_FEATURES + NUMERICAL_FEATURES
    train_dicts = df_train[all_features].to_dict(orient='records')
    val_dicts = df_val[all_features].to_dict(orient='records')

    # DictVectorizer convierte categoricas a one-hot y mantiene numericas
    dv = DictVectorizer()
    X_train = dv.fit_transform(train_dicts)
    X_val = dv.transform(val_dicts)

    y_train = df_train[TARGET].values
    y_val = df_val[TARGET].values

    print(f"  X_train: {X_train.shape} | X_val: {X_val.shape}")

    # --- 4. Guardado de artefactos ---
    print("Paso 4: Guardando artefactos")
    artifacts = {
        "X_train.pkl": X_train,
        "y_train.pkl": y_train,
        "X_val.pkl": X_val,
        "y_val.pkl": y_val,
        "dv.pkl": dv,
    }
    for name, obj in artifacts.items():
        filepath = os.path.join(output_path, name)
        with open(filepath, "wb") as f:
            pickle.dump(obj, f)

    print(f"  Artefactos guardados en {output_path}/")
    print("Listo!")


if __name__ == '__main__':
    data_path = "data"
    output_path = "data/processed"
    preprocess_data(data_path, output_path)
