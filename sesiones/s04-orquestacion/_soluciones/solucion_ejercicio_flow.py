"""SOLUCION de referencia del ejercicio de clasificacion (Sesion 4).

Mirala despues de intentarlo. El enunciado esta en
`../01-pipeline-ml/ejercicio/`.

Decisiones que conviene discutir en clase:

1. **Se reutiliza `taxi.flows.training.preparar`.** Preparar los datos es
   identico en regresion y clasificacion. Duplicarlo seria repetir el error del
   repo anterior, donde el mismo problema tenia tres implementaciones con
   features distintas.
2. **La metrica principal no es accuracy.** Con el umbral de 30 minutos la clase
   positiva es minoritaria: predecir siempre "no es largo" da una accuracy alta y
   un modelo inutil. Se reportan `f1` por umbral, y `roc_auc` /
   `average_precision`, que no dependen del umbral. Con clases desbalanceadas,
   `average_precision` (area bajo precision-recall) es mas informativa que
   `roc_auc`.
3. **El umbral no es un hiperparametro, es una decision de negocio.** Depende del
   costo relativo de un falso positivo frente a un falso negativo, y ese costo lo
   pone quien opera el sistema. El pipeline no elige: **informa**, con la tabla de
   umbrales como artifact.
4. **El flow registra y no promueve.** Igual que el de regresion.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact

from taxi.config import (
    ALIAS_CANDIDATO,
    EXPERIMENTOS,
    MLFLOW_TRACKING_URI,
    MODELO_CLASIFICACION,
    PARTICION_VALID,
    PARTICIONES_TRAIN,
)
from taxi.features import contract as fc
from taxi.flows.training import preparar

UMBRALES: tuple[float, ...] = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7)


def filas_por_umbral(
    y_real: np.ndarray,
    probabilidades: np.ndarray,
    umbrales: tuple[float, ...] = UMBRALES,
) -> list[dict[str, float]]:
    """Metricas para cada umbral de decision. Funcion pura: se testea directo."""
    from sklearn.metrics import precision_score, recall_score

    filas: list[dict[str, float]] = []
    for umbral in umbrales:
        prediccion = (probabilidades >= umbral).astype(int)
        precision = float(precision_score(y_real, prediccion, zero_division=0))
        recall = float(recall_score(y_real, prediccion, zero_division=0))
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        filas.append(
            {
                "umbral": float(umbral),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "positivos_predichos": int(prediccion.sum()),
            }
        )
    return filas


def _configurar_mlflow(experimento: str) -> None:
    """Configura MLflow dentro de la task, nunca al importar el modulo."""
    import mlflow

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experimento)


# =============================================================================
# 1 — Datos
# =============================================================================
@task(name="cargar_datos", retries=3, retry_delay_seconds=[10, 30, 60])
def cargar_datos(particiones: tuple[Any, ...]) -> pd.DataFrame:
    """Prepara las particiones y reporta el desbalance de clases."""
    logger = get_run_logger()
    df = preparar(particiones)
    positivos = float(df[fc.TARGET_CLASIFICACION].mean())
    logger.info(
        "Filas: %d. Clase positiva (viaje largo): %.1f%%. "
        "Con este desbalance, accuracy no es una metrica util.",
        len(df),
        100 * positivos,
    )
    return df


# =============================================================================
# 2 — Entrenamiento
# =============================================================================
@task(name="entrenar_clasificador")
def entrenar_clasificador(
    df_train: pd.DataFrame,
    experimento: str = EXPERIMENTOS["pipeline"],
) -> dict[str, Any]:
    """Entrena una regresion logistica y la loguea en MLflow."""
    import mlflow
    from mlflow.models import infer_signature
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    from taxi.models.train import ADiccionarios

    logger = get_run_logger()
    _configurar_mlflow(experimento)

    estimador = Pipeline(
        [
            # Mismo preprocesamiento que los modelos de regresion del curso: una
            # sola definicion de features para todo el proyecto.
            ("diccionarios", ADiccionarios(list(fc.FEATURES))),
            ("vectorizador", DictVectorizer(sparse=True)),
            # class_weight="balanced" compensa el desbalance sin remuestrear.
            ("modelo", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )

    x_train = df_train[fc.FEATURES]
    y_train = df_train[fc.TARGET_CLASIFICACION].to_numpy(dtype=int)

    with mlflow.start_run(run_name="s04-clasificacion-orquestada") as run:
        estimador.fit(x_train, y_train)
        mlflow.set_tags({"orquestador": "prefect", "problema": "clasificacion"})
        mlflow.log_params({"modelo": "LogisticRegression", "class_weight": "balanced"})

        ejemplo = x_train.head(5)
        firma = infer_signature(ejemplo, estimador.predict(ejemplo))
        info = mlflow.sklearn.log_model(
            estimador,
            name="model",
            signature=firma,
            input_example=ejemplo,
            serialization_format="cloudpickle",
        )
        run_id = run.info.run_id

    logger.info("Clasificador entrenado en el run %s", run_id)
    return {"run_id": run_id, "model_uri": info.model_uri, "estimador": estimador}


# =============================================================================
# 3 — Evaluacion por umbral
# =============================================================================
@task(name="evaluar_por_umbral")
def evaluar_por_umbral(
    modelo: dict[str, Any],
    df_valid: pd.DataFrame,
    umbrales: tuple[float, ...] = UMBRALES,
    experimento: str = EXPERIMENTOS["pipeline"],
) -> list[dict[str, float]]:
    """Evalua en validacion para cada umbral y loguea las metricas globales."""
    import mlflow
    from sklearn.metrics import average_precision_score, roc_auc_score

    logger = get_run_logger()
    _configurar_mlflow(experimento)

    y_valid = df_valid[fc.TARGET_CLASIFICACION].to_numpy(dtype=int)
    probabilidades = modelo["estimador"].predict_proba(df_valid[fc.FEATURES])[:, 1]

    filas = filas_por_umbral(y_valid, probabilidades, umbrales)
    # roc_auc y average_precision no dependen del umbral: describen el ranking de
    # probabilidades, no una decision concreta.
    globales = {
        "roc_auc": float(roc_auc_score(y_valid, probabilidades)),
        "average_precision": float(average_precision_score(y_valid, probabilidades)),
    }

    with mlflow.start_run(run_id=modelo["run_id"]):
        mlflow.log_metrics(globales)
        for fila in filas:
            mlflow.log_metric("f1_por_umbral", fila["f1"], step=int(fila["umbral"] * 100))

    mejor = max(filas, key=lambda f: f["f1"])
    logger.info(
        "roc_auc=%.4f average_precision=%.4f. Mejor f1=%.4f con umbral %.2f.",
        globales["roc_auc"],
        globales["average_precision"],
        mejor["f1"],
        mejor["umbral"],
    )
    for clave, valor in globales.items():
        filas.append({"umbral": -1.0, clave: round(valor, 4)})
    return filas


# =============================================================================
# 4 — Artifacts
# =============================================================================
@task(name="publicar_tabla_de_umbrales")
def publicar_tabla_de_umbrales(filas: list[dict[str, float]]) -> None:
    """Publica la tabla de umbrales y un resumen con la decision pendiente."""
    por_umbral = [f for f in filas if f.get("umbral", -1.0) >= 0]
    create_table_artifact(
        key="metricas-por-umbral",
        table=por_umbral,
        description="Precision, recall y f1 para cada umbral de decision.",
    )

    mejor = max(por_umbral, key=lambda f: f["f1"])
    create_markdown_artifact(
        key="decision-de-umbral",
        markdown=f"""# Umbral de decision

El mejor f1 se obtiene con umbral **{mejor["umbral"]:.2f}**
(precision {mejor["precision"]:.3f}, recall {mejor["recall"]:.3f}).

Eso **no** significa que ese sea el umbral correcto. El umbral depende del costo
relativo de los dos errores:

- **Falso positivo**: se avisa "viaje largo" y no lo es. Molesta al usuario.
- **Falso negativo**: no se avisa y el viaje si es largo. Rompe la promesa.

Si el falso negativo cuesta mas, hay que bajar el umbral y aceptar menos
precision. Esa decision la toma quien opera el sistema, no el pipeline: el
pipeline informa.
""",
        description="Por que el umbral es una decision de negocio.",
    )


# =============================================================================
# 5 — Registro del candidato
# =============================================================================
@task(name="registrar_candidato_clasificacion")
def registrar_candidato_clasificacion(
    modelo: dict[str, Any],
    metricas: list[dict[str, float]],
    nombre_modelo: str = MODELO_CLASIFICACION,
    experimento: str = EXPERIMENTOS["pipeline"],
) -> str:
    """Registra la version con alias `candidate`. No promueve."""
    import mlflow
    from mlflow import MlflowClient

    logger = get_run_logger()
    _configurar_mlflow(experimento)

    version_registrada = mlflow.register_model(modelo["model_uri"], nombre_modelo)
    version = str(version_registrada.version)
    cliente = MlflowClient()

    por_umbral = [f for f in metricas if f.get("umbral", -1.0) >= 0]
    mejor = max(por_umbral, key=lambda f: f["f1"])
    for clave, valor in {
        "f1_valid": f"{mejor['f1']:.4f}",
        "umbral_mejor_f1": f"{mejor['umbral']:.2f}",
        "registrado_por": "solucion_ejercicio_flow",
    }.items():
        cliente.set_model_version_tag(nombre_modelo, version, clave, valor)

    cliente.set_registered_model_alias(nombre_modelo, ALIAS_CANDIDATO, version)
    logger.info(
        "Registrado %s v%s con alias @%s. Sin promover: la promocion es el gate de S06.",
        nombre_modelo,
        version,
        ALIAS_CANDIDATO,
    )
    return version


# =============================================================================
# 6 — Flow
# =============================================================================
@flow(name="clasificacion-viaje-largo", log_prints=True)
def clasificacion_flow(registrar: bool = True) -> dict[str, Any]:
    """Pipeline de clasificacion: datos -> entrenar -> evaluar -> registrar."""
    df_train = cargar_datos(PARTICIONES_TRAIN)
    df_valid = cargar_datos((PARTICION_VALID,))

    modelo = entrenar_clasificador(df_train)
    metricas = evaluar_por_umbral(modelo, df_valid)
    publicar_tabla_de_umbrales(metricas)

    version = registrar_candidato_clasificacion(modelo, metricas) if registrar else None

    return {
        "run_id": modelo["run_id"],
        "model_version": version,
        "promovido": False,
        "metricas": metricas,
    }


if __name__ == "__main__":
    print(clasificacion_flow())
