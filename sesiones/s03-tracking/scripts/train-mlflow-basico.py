#!/usr/bin/env python
"""Paso 2 de 3: tracking basico. Params y metricas, y NADA mas.

Que cambia respecto a `train-sin-mlflow.py`
-------------------------------------------
Tres lineas: `set_tracking_uri`, `set_experiment` y un `start_run` que envuelve
el entrenamiento. Con eso, las cinco corridas del paso 1 pasan de ser cinco
`print` perdidos a cinco filas comparables en una tabla.

Que sigue faltando, a proposito
-------------------------------
Este script **no loguea el modelo ni el vectorizador**. Es el estado en el que
estaba este modulo antes del rediseno: ensenaba tracking de metricas sin
trazabilidad de artefactos. El sintoma aparece un mes despues:

    "El run 3f2a tiene el mejor RMSE. Pasame ese modelo."
    "No lo tengo. Solo quedo la metrica."

Un run que registra la metrica de un modelo que ya no existe documenta un
resultado que no se puede volver a usar. `train-mlflow-completo.py` cierra ese
hueco y muestra lo que hace falta para que el artefacto sea utilizable:
`signature`, `input_example` y la decision de serializacion.

Uso
---
    # terminal 1
    make mlflow                    # server en 127.0.0.1:5001

    # terminal 2
    python sesiones/s03-tracking/scripts/train-mlflow-basico.py --max-depth 5
    python sesiones/s03-tracking/scripts/train-mlflow-basico.py --max-depth 10
    python sesiones/s03-tracking/scripts/train-mlflow-basico.py --max-depth 20

Y despues, en la UI: ordenar por `rmse` y responder en cinco segundos la
pregunta que en el paso 1 no tenia respuesta.
"""

from __future__ import annotations

import click
import mlflow
from sklearn.metrics import root_mean_squared_error

from taxi import config
from taxi.features import contract as fc
from taxi.models import train

#: Puerto 5001 en TODO el curso: el puerto por defecto de `mlflow server` lo
#: ocupa AirPlay Receiver en macOS. El repo anterior mezclaba los dos puertos
#: entre scripts y notebooks, y el estudiante acababa con el server en uno y el
#: cliente en el otro. El valor vive en `taxi.config`, no repetido en cada archivo.
TRACKING_URI = config.MLFLOW_TRACKING_URI


@click.command()
@click.option("--max-depth", default=10, show_default=True, help="Profundidad maxima del bosque.")
@click.option("--n-estimators", default=100, show_default=True, help="Numero de arboles.")
def main(max_depth: int, n_estimators: int) -> None:
    """Entrena un RandomForest y loguea params y metricas (sin artefactos)."""
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(config.EXPERIMENTOS["baseline"])

    df_train = train.cargar_train()
    df_valid = train.cargar_valid()

    with mlflow.start_run(run_name=f"rf-depth{max_depth}-trees{n_estimators}"):
        # Tags: metadata para FILTRAR runs despues. Sin ellos, dos runs con el
        # mismo RMSE y datos distintos son indistinguibles.
        mlflow.set_tags(
            {
                "tipo": "baseline",
                "model_family": "random_forest",
                "particiones_train": ",".join(p.etiqueta for p in config.PARTICIONES_TRAIN),
                "particion_valid": config.PARTICION_VALID.etiqueta,
            }
        )
        mlflow.log_params(
            {
                "max_depth": max_depth,
                "n_estimators": n_estimators,
                "semilla": config.SEMILLA,
                "filas_train": len(df_train),
                "filas_valid": len(df_valid),
            }
        )

        pipeline = train.pipeline_random_forest(max_depth=max_depth, n_estimators=n_estimators)
        train.ajustar(pipeline, df_train, df_valid)

        y_valid = df_valid[fc.TARGET_REGRESION].to_numpy(dtype=float)
        y_pred = pipeline.predict(df_valid)
        rmse = float(root_mean_squared_error(y_valid, y_pred))
        mlflow.log_metric("rmse", rmse)

        print(f"RMSE={rmse:.4f} | run_id={mlflow.active_run().info.run_id}")
        print("Modelo logueado: NO. Ese es el punto del paso 3.")


if __name__ == "__main__":
    # Una sola llamada. La version anterior invocaba `run_train()` dos veces
    # seguidas por un copy-paste, asi que cada ejecucion creaba dos runs
    # identicos y duplicaba el tiempo de clase sin que nadie supiera por que.
    main()
