#!/usr/bin/env python
"""Paso 1 de 3: entrenar SIN tracking. Este script existe para doler.

Que hace
--------
Entrena un RandomForest sobre el caso guia y imprime el RMSE. Nada mas. Es
exactamente lo que hace la mayoria de los proyectos de ML antes de tener
tracking, y funciona: el numero sale y es correcto.

Como se usa en clase
--------------------
Correrlo CINCO veces con hiperparametros distintos y, al terminar, intentar
responder estas preguntas mirando solo la terminal:

    python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 5
    python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 10
    python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 20
    python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 20 --n-estimators 300
    python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 30

1. Cual de las cinco corridas fue la mejor, y por cuanto?
2. Con que particiones de datos se entreno la tercera?
3. Con que version del codigo? Habia cambios sin commitear?
4. Donde esta el modelo de la mejor corrida? Se puede cargar hoy?
5. Se puede repetir la corrida numero 2 exactamente, dentro de tres meses?

La respuesta honesta a las cinco es "no, salvo que alguien lo haya apuntado a
mano". Ese es el problema que resuelve el experiment tracking, y por eso se
mira antes de abrir MLflow.

Nota sobre el codigo
--------------------
Los datos y el pipeline se importan de `taxi` en lugar de redefinirse aqui. Dos
rutas de preprocesamiento para el mismo problema (una con pickles y
`DictVectorizer`, otra con parquet y `ColumnTransformer`) acaban dando resultados
distintos segun por donde entres. La regla es la de S01: la logica vive en el
paquete, el material de clase la ejecuta.
"""

from __future__ import annotations

import click
from sklearn.metrics import root_mean_squared_error

from taxi.features import contract as fc
from taxi.models import train


@click.command()
@click.option("--max-depth", default=10, show_default=True, help="Profundidad maxima del bosque.")
@click.option("--n-estimators", default=100, show_default=True, help="Numero de arboles.")
def main(max_depth: int, n_estimators: int) -> None:
    """Entrena un RandomForest y solo imprime el RMSE de validacion."""
    df_train = train.cargar_train()
    df_valid = train.cargar_valid()

    pipeline = train.pipeline_random_forest(max_depth=max_depth, n_estimators=n_estimators)
    train.ajustar(pipeline, df_train, df_valid)

    y_valid = df_valid[fc.TARGET_REGRESION].to_numpy(dtype=float)
    y_pred = pipeline.predict(df_valid)
    # root_mean_squared_error, no mean_squared_error(squared=False): ese
    # parametro fue ELIMINADO de scikit-learn (verificado contra 1.9.0).
    rmse = float(root_mean_squared_error(y_valid, y_pred))

    print(f"max_depth={max_depth} n_estimators={n_estimators} -> RMSE={rmse:.4f}")
    print("Y esto es todo lo que queda de la corrida cuando cierres la terminal.")


if __name__ == "__main__":
    main()
