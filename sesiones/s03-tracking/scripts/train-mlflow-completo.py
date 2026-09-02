#!/usr/bin/env python
"""Paso 3 de 3: tracking completo. HPO con runs anidados y el modelo como artifact.

Que agrega respecto a `train-mlflow-basico.py`
----------------------------------------------
1. **Estructura de runs**: un parent run para el study de Optuna y un child run
   por trial (`nested=True`). Sin eso, 20 trials son 20 runs sueltos sin
   relacion entre si y la UI deja de ser legible.
2. **El modelo como artifact**, con `signature` e `input_example`. Es la
   correccion mas importante de este script: la version anterior loguea
   metricas de un modelo que no guarda en ningun lado.
3. **La decision de serializacion, explicita.** Ver la nota de abajo.

Un artefacto, no dos
--------------------
Se loguea el `Pipeline` completo, que ya contiene el `DictVectorizer`. El repo
anterior guardaba `preprocessor.b` y `model.ubj` como archivos separados y los
copiaba a mano entre modulos: cuando los dos se desincronizaban, el modelo
servia predicciones sobre features mal codificadas y **nada fallaba**. Un
artefacto, una version, un hash.

serialization_format: skops vs cloudpickle
------------------------------------------
En mlflow 3 el default de `mlflow.sklearn.log_model` es `serialization_format='skops'`
(antes era cloudpickle). Verificado contra mlflow 3.15.1:

- skops reconstruye solo tipos de una allowlist en lugar de ejecutar el codigo
  que venga en el archivo. Eso cierra un vector de ejecucion remota de codigo:
  un artefacto de modelo es un archivo que baja de un bucket y se carga en un
  proceso de produccion.
- El precio es que todo tipo que no sea de sklearn hay que declararlo en
  `skops_trusted_types`. Sin la declaracion, `log_model` falla con
  "The saved sklearn model references untrusted types".
- Este script entrena un `XGBRegressor` dentro del Pipeline, asi que hay que
  declarar TRES tipos: `ADiccionarios`, `xgboost.core.Booster` y
  `xgboost.sklearn.XGBRegressor`. `src/taxi/models/train.py` los declara igual;
  `src/taxi/flows/training.py` (S04) eligio `serialization_format="cloudpickle"`
  para el mismo caso. Las dos opciones son defendibles y el trade-off esta en el
  README de la sesion.

Uso
---
    # terminal 1
    make mlflow

    # terminal 2
    python sesiones/s03-tracking/scripts/train-mlflow-completo.py --trials 20

El taller pide >=20 runs en el experimento de HPO. La version del paquete,
`taxi train --hpo --trials 20`, hace lo mismo con pruner de Optuna, metricas por
subgrupo y registro del candidato; este script es la version legible en una
pantalla.
"""

from __future__ import annotations

from typing import Any

import click
import mlflow
import optuna
from mlflow.models import infer_signature
from sklearn.metrics import root_mean_squared_error

from taxi import config
from taxi.features import contract as fc
from taxi.models import train

#: Tipos que skops debe aceptar al deserializar ESTE pipeline. Declararlos a
#: mano se siente tedioso hasta que se piensa que la alternativa es "cargar un
#: .pkl que bajo de un bucket y confiar". Verificado contra mlflow 3.15.1: si
#: falta cualquiera de los tres, `log_model` falla con "untrusted types".
TIPOS_CONFIABLES = [
    "taxi.models.train.ADiccionarios",
    "xgboost.core.Booster",
    "xgboost.sklearn.XGBRegressor",
]

#: Rondas de boosting fijas, sin early stopping, para que un trial tarde
#: segundos en clase. La decision tiene un motivo medible: con ~30 000 features
#: one-hot (el par PU_DO), evaluar el conjunto de validacion en CADA ronda
#: cuesta mas que el propio boosting, y el early stopping obliga a hacerlo. El
#: paquete (`taxi train --hpo`) si lo usa, con `RONDAS_BOOST = 500` y
#: `RONDAS_EARLY_STOPPING = 50`, y tarda bastante mas. **Mide las dos cosas en
#: tu maquina antes de elegir**: el numero depende de tus nucleos y de tu
#: cardinalidad, no de lo que diga este comentario.
#:
#: Si activas early stopping, la paciencia tiene que ser MUCHO menor que las
#: rondas. Declarar paciencia 50 y entrenar 30 rondas deja el mecanismo inerte:
#: no puede dispararse nunca, el codigo se ve correcto y nada avisa.
RONDAS_EN_CLASE = 150


def rmse_de(pipeline: Any, df: Any) -> float:
    """RMSE de un pipeline ajustado sobre un dataframe procesado."""
    y_true = df[fc.TARGET_REGRESION].to_numpy(dtype=float)
    return float(root_mean_squared_error(y_true, pipeline.predict(df)))


@click.command()
@click.option("--trials", default=20, show_default=True, help="Combinaciones a probar.")
def main(trials: int) -> None:
    """Busca hiperparametros con Optuna y registra el mejor modelo como artifact."""
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(config.EXPERIMENTOS["hpo"])

    df_train = train.cargar_train()
    df_valid = train.cargar_valid()

    def objetivo(trial: optuna.Trial) -> float:
        params = {
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "min_child_weight": trial.suggest_float("min_child_weight", 0.5, 20.0, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        }
        # El resto de los hiperparametros (objetivo, semilla, tree_method) sale
        # de `train.PARAMS_XGBOOST`: una sola fuente de verdad.
        pipeline = train.pipeline_xgboost(
            n_estimators=RONDAS_EN_CLASE,
            early_stopping_rounds=None,
            **params,
        )
        # nested=True: el trial cuelga del parent run del study.
        with mlflow.start_run(run_name=f"trial-{trial.number:03d}", nested=True):
            mlflow.set_tag("tipo", "hpo-trial")
            mlflow.log_params(params)
            train.ajustar(pipeline, df_train, df_valid)
            rmse = rmse_de(pipeline, df_valid)
            mlflow.log_metric("rmse", rmse)
        return rmse

    # Sampler con semilla explicita: dos corridas del mismo study exploran las
    # mismas combinaciones. Sin semilla, "mi mejor RMSE fue 4.31" no es una
    # afirmacion reproducible.
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=config.SEMILLA),
    )

    with mlflow.start_run(run_name=f"hpo-xgboost-{trials}-trials"):
        mlflow.set_tags({"tipo": "hpo-parent", "sampler": "TPESampler"})
        mlflow.log_params({"trials": trials, "semilla": config.SEMILLA})
        study.optimize(objetivo, n_trials=trials)

        mlflow.log_metric("mejor_rmse", float(study.best_value))
        mlflow.log_dict(dict(study.best_params), "hpo/best_params.json")

        # --- El mejor modelo, reentrenado y logueado como artifact ---
        with mlflow.start_run(run_name="mejor-modelo", nested=True):
            mlflow.set_tag("tipo", "candidato")
            mlflow.log_params(study.best_params)
            pipeline = train.pipeline_xgboost(
                n_estimators=RONDAS_EN_CLASE,
                early_stopping_rounds=None,
                **study.best_params,
            )
            train.ajustar(pipeline, df_train, df_valid)
            mlflow.log_metric("rmse", rmse_de(pipeline, df_valid))
            mlflow.log_metric("rondas", float(RONDAS_EN_CLASE))

            # El input_example declara el tipo MAS ANCHO de cada columna, no el
            # mas compacto con el que se entreno. Si se pasa el dataframe tal
            # cual, `hora_pickup` viaja como int16, la firma queda como int32 y
            # MLflow RECHAZA en produccion cualquier peticion con int64 —que es
            # lo que manda cualquier cliente normal. La explicacion completa
            # esta en el docstring de `train._ejemplo_de_entrada`: el guion bajo
            # dice que es un detalle interno del paquete, pero el problema que
            # resuelve es contenido de esta clase.
            ejemplo = train._ejemplo_de_entrada(df_valid)
            firma = infer_signature(ejemplo, pipeline.predict(ejemplo))

            info = mlflow.sklearn.log_model(
                sk_model=pipeline,
                # `name=`, no `artifact_path=`: el segundo esta deprecado en
                # los flavors de mlflow 3.
                name="modelo",
                signature=firma,
                input_example=ejemplo,
                skops_trusted_types=TIPOS_CONFIABLES,
            )
            print(f"Modelo logueado en {info.model_uri}")

    print(f"Mejor RMSE={study.best_value:.4f} con {study.best_params}")
    print(f"Revisa {config.MLFLOW_TRACKING_URI} -> experimento {config.EXPERIMENTOS['hpo']}")
    print("El parent run tiene los trials como child runs. Ordena por rmse y compara.")


if __name__ == "__main__":
    # Una sola llamada: la version anterior corria `run_optimization()` dos
    # veces por un copy-paste y duplicaba en silencio todos los runs.
    main()
