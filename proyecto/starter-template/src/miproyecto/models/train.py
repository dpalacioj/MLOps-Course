"""Entrenamiento con tracking de experimentos.

Tres decisiones estructurales, con su motivo:

**1. El preprocesamiento va DENTRO del artefacto.** El objeto que se serializa es
un ``sklearn.Pipeline`` que incluye el vectorizador. Guardar el preprocesador y
el modelo como dos archivos separados y copiarlos a mano es la receta para que se
desincronicen: el dia que eso pasa, el servicio sirve predicciones sobre features
mal codificadas y NADA falla. Un artefacto, una version, un hash.

**2. Los hiperparametros por defecto viven en un solo lugar** (``PARAMS``). Si
los declaras aqui y ademas los pasas a mano en el flow, se van a desincronizar.

**3. El holdout no se toca durante la seleccion.** Los hiperparametros se eligen
con ``PARTICION_VALID``. ``PARTICION_TEST`` se evalua, como maximo, una vez por
candidato y solo para el gate. Usarlo para tunear convierte el gate en una
medicion de cuanto te sobreajustaste al juez.

Sobre el tracking: se registran params, metricas, ``signature`` e
``input_example``. La signature no es decoracion: es lo unico que detecta
train/serving skew antes de produccion (un ``float`` donde el modelo espera
``int`` deja de ser un misterio y pasa a ser un error explicito).

TODO(estudiante) 14: cambia el estimador y la metrica por los de tu problema.
Un baseline honesto primero (``DummyRegressor`` / ``DummyClassifier``): si tu
modelo no le gana claramente, el problema no esta donde crees.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.pipeline import Pipeline

from miproyecto.config import (
    ALIAS_CANDIDATO,
    EXPERIMENTOS,
    MLFLOW_TRACKING_URI,
    MODELO_REGISTRADO,
    SEMILLA,
)
from miproyecto.features import contract as fc

logger = logging.getLogger(__name__)

#: Unica fuente de verdad de los hiperparametros por defecto.
PARAMS: Final[dict[str, Any]] = {
    "max_iter": 200,
    "max_depth": 6,
    "learning_rate": 0.1,
    "l2_regularization": 1.0,
    "early_stopping": True,
    # n_iter_no_change tiene que ser MENOR que max_iter o el early stopping no
    # puede dispararse nunca. Es un bug silencioso clasico: la constante existe,
    # se ve profesional y no hace nada. Lo vigila un test.
    "n_iter_no_change": 20,
    "random_state": SEMILLA,
}


@dataclass
class Resultado:
    """Salida de un entrenamiento: metricas y como recuperar el artefacto."""

    metricas: dict[str, float]
    params: dict[str, Any]
    run_id: str | None = None
    version_modelo: str | None = None
    subgrupos: dict[str, float] = field(default_factory=dict)


def construir_pipeline(**params: Any) -> Pipeline:
    """Devuelve el pipeline completo: vectorizador + estimador.

    ``sparse=False`` en el vectorizador porque ``HistGradientBoosting`` no acepta
    matrices sparse. Si cambias a un modelo lineal o a XGBoost, ponlo en True:
    con muchas categorias, la matriz densa puede no caber en memoria.
    """
    efectivos = {**PARAMS, **params}
    return Pipeline(
        [
            ("vectorizador", DictVectorizer(sparse=False)),
            ("modelo", HistGradientBoostingRegressor(**efectivos)),
        ]
    )


def construir_baseline() -> Pipeline:
    """Baseline honesto: predice la mediana. Es el numero que hay que batir.

    Si tu modelo no le gana a esto por un margen que importa al negocio, el
    problema no es de hiperparametros.
    """
    return Pipeline(
        [
            ("vectorizador", DictVectorizer(sparse=False)),
            ("modelo", DummyRegressor(strategy="median")),
        ]
    )


def metricas_regresion(y_real: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Metricas globales.

    Se usa ``root_mean_squared_error``. El truco de pasarle ``squared=False`` a
    ``mean_squared_error`` ya no funciona: ese parametro se elimino de
    scikit-learn, y sigue apareciendo en la mayoria de los tutoriales.
    """
    return {
        "rmse": float(root_mean_squared_error(y_real, y_pred)),
        "mae": float(mean_absolute_error(y_real, y_pred)),
        "r2": float(r2_score(y_real, y_pred)),
    }


def metricas_por_subgrupo(
    df: pd.DataFrame,
    y_real: np.ndarray,
    y_pred: np.ndarray,
    *,
    columna: str = fc.COL_SUBGRUPO,
    minimo_por_grupo: int = 30,
) -> dict[str, float]:
    """RMSE por subgrupo, para detectar mejoras que esconden degradaciones.

    Un modelo puede bajar el RMSE global un 3% y a la vez empeorar un 40% en un
    segmento entero. La metrica global no lo muestra; esta si. El gate de
    promocion la usa como criterio de rechazo.

    Los grupos con menos de ``minimo_por_grupo`` filas se omiten: su metrica es
    ruido y contaminaria la decision.
    """
    salida: dict[str, float] = {}
    for valor, indices in df.groupby(columna, observed=True).groups.items():
        posiciones = df.index.get_indexer(indices)
        if len(posiciones) < minimo_por_grupo:
            continue
        clave = str(valor)
        salida[f"rmse_{clave}"] = float(
            root_mean_squared_error(y_real[posiciones], y_pred[posiciones])
        )
        salida[f"n_{clave}"] = float(len(posiciones))
    return salida


def entrenar(
    df_train: pd.DataFrame,
    df_valid: pd.DataFrame,
    *,
    params: dict[str, Any] | None = None,
    registrar: bool = True,
    experimento: str = EXPERIMENTOS["baseline"],
) -> Resultado:
    """Entrena, evalua y (opcionalmente) registra el candidato en MLflow.

    ``registrar=False`` existe para los tests: el entrenamiento tiene que ser
    ejecutable sin un servidor de tracking levantado. Si tu funcion de
    entrenamiento no se puede testear sin infraestructura, el problema es la
    funcion, no la infraestructura.

    Nota importante: esta funcion registra el candidato con el alias
    ``candidate`` y **no lo promueve**. Promover porque el entrenamiento termino
    sin excepciones es como se degradan los sistemas de ML en produccion. La
    decision es del gate (``models/promote.py``), y el gate vive en CI.
    """
    params = params or {}
    pipeline = construir_pipeline(**params)

    x_train = fc.a_diccionarios(df_train)
    y_train = df_train[fc.TARGET].to_numpy()
    x_valid = fc.a_diccionarios(df_valid)
    y_valid = df_valid[fc.TARGET].to_numpy()

    pipeline.fit(x_train, y_train)
    pred = pipeline.predict(x_valid)

    metricas = metricas_regresion(y_valid, pred)
    subgrupos = metricas_por_subgrupo(df_valid.reset_index(drop=True), y_valid, pred)
    logger.info("metricas de validacion: %s", metricas)

    resultado = Resultado(
        metricas=metricas,
        params={**PARAMS, **params},
        subgrupos=subgrupos,
    )
    if registrar:
        _registrar_en_mlflow(pipeline, resultado, df_valid, experimento)
    return resultado


def _registrar_en_mlflow(
    pipeline: Pipeline,
    resultado: Resultado,
    df_ejemplo: pd.DataFrame,
    experimento: str,
) -> None:
    """Registra run, params, metricas y modelo con signature e input_example.

    El import de mlflow es local a proposito: asi importar este modulo (y correr
    los tests) no depende de que mlflow este instalado ni de que el servidor
    responda.
    """
    import mlflow
    from mlflow.models import infer_signature

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experimento)

    ejemplo = fc.a_diccionarios(df_ejemplo.head(5))
    with mlflow.start_run() as run:
        mlflow.log_params(resultado.params)
        mlflow.log_metrics(resultado.metricas)
        mlflow.log_metrics(resultado.subgrupos)
        mlflow.set_tag("features", ",".join(fc.FEATURES))

        info = mlflow.sklearn.log_model(
            sk_model=pipeline,
            name="modelo",
            signature=infer_signature(ejemplo, pipeline.predict(ejemplo)),
            input_example=ejemplo,
            registered_model_name=MODELO_REGISTRADO,
        )
        resultado.run_id = run.info.run_id

    cliente = mlflow.MlflowClient()
    version = info.registered_model_version
    if version is not None:
        # El alias `candidate` marca "esto es lo ultimo entrenado", no "esto
        # sirve". Mover `champion` es responsabilidad del gate.
        cliente.set_registered_model_alias(MODELO_REGISTRADO, ALIAS_CANDIDATO, str(version))
        resultado.version_modelo = str(version)
    logger.info("run %s, version %s", resultado.run_id, resultado.version_modelo)
