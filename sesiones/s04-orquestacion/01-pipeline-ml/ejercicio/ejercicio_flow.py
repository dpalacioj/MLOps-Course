"""EJERCICIO — Flow de clasificacion orquestado con Prefect 3.

Completa las funciones marcadas con TODO. No borres los docstrings: describen el
contrato que cada task debe cumplir.

Ejecutar:

    uv run python sesiones/s04-orquestacion/01-pipeline-ml/ejercicio/ejercicio_flow.py

Criterios de aceptacion: ver README.md de esta carpeta.
La solucion de referencia esta en `../../_soluciones/solucion_ejercicio_flow.py`
(mirala despues de intentarlo, no antes: el valor esta en el intento).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from prefect import flow, get_run_logger, task

# Estos imports son los que necesitas para resolver los TODO. Ruff no se queja
# de los que todavia no usas gracias al noqa; quitalo cuando termines.
from taxi.config import (  # noqa: F401
    ALIAS_CANDIDATO,
    EXPERIMENTOS,
    MLFLOW_TRACKING_URI,
    MODELO_CLASIFICACION,
    PARTICION_VALID,
    PARTICIONES_TRAIN,
)
from taxi.features import contract as fc  # noqa: F401
from taxi.flows.training import preparar  # noqa: F401  -- reutilizar, no duplicar

UMBRALES: tuple[float, ...] = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7)


# =============================================================================
# TODO 1 — Task de datos con reintentos y backoff
# =============================================================================
@task(name="cargar_datos")  # TODO 1a: agrega retries=3 y un backoff creciente
def cargar_datos(particiones: tuple[Any, ...]) -> pd.DataFrame:
    """Prepara las particiones indicadas y devuelve el dataframe procesado.

    Requisitos:
    - reutiliza la task `preparar` de `taxi.flows.training` (no reimplementes la
      preparacion de datos);
    - loguea cuantas filas quedaron y cual es la proporcion de la clase positiva,
      porque el desbalance es lo que determina que metrica tiene sentido.

    TODO 1b: implementa el cuerpo.
    """
    logger = get_run_logger()  # noqa: F841  -- usalo en tu implementacion
    raise NotImplementedError("TODO 1b")


# =============================================================================
# TODO 2 — Task de entrenamiento
# =============================================================================
@task(name="entrenar_clasificador")
def entrenar_clasificador(
    df_train: pd.DataFrame,
    experimento: str = EXPERIMENTOS["pipeline"],
) -> dict[str, Any]:
    """Entrena un clasificador y lo loguea en MLflow.

    Requisitos:
    - configura MLflow **dentro** de la task, nunca a nivel de modulo;
    - el estimador debe aceptar un DataFrame con `fc.FEATURES` como entrada;
    - loguea el modelo con `name="model"` (no `artifact_path=`), con `signature`
      e `input_example`;
    - devuelve un dict con al menos `run_id`, `model_uri` y `estimador`.

    TODO 2: implementa el cuerpo.
    """
    raise NotImplementedError("TODO 2")


# =============================================================================
# TODO 3 — Evaluacion por umbral
# =============================================================================
@task(name="evaluar_por_umbral")
def evaluar_por_umbral(
    modelo: dict[str, Any],
    df_valid: pd.DataFrame,
    umbrales: tuple[float, ...] = UMBRALES,
) -> list[dict[str, float]]:
    """Evalua el clasificador en validacion para cada umbral.

    Requisitos:
    - una fila por umbral, con `precision`, `recall`, `f1` y cuantos positivos
      predice;
    - `roc_auc` y `average_precision` se calculan una sola vez (no dependen del
      umbral: por eso se reportan aparte);
    - **no** uses accuracy como metrica principal, y deja escrito en un comentario
      por que.

    TODO 3: implementa el cuerpo.
    """
    raise NotImplementedError("TODO 3")


# =============================================================================
# TODO 4 — Artifact con la tabla de umbrales
# =============================================================================
@task(name="publicar_tabla_de_umbrales")
def publicar_tabla_de_umbrales(filas: list[dict[str, float]]) -> None:
    """Publica la tabla de metricas por umbral como artifact de Prefect.

    La clave del artifact debe ser exactamente `metricas-por-umbral` (el criterio
    de aceptacion 4 la busca por ese nombre).

    TODO 4: implementa el cuerpo.
    """
    raise NotImplementedError("TODO 4")


# =============================================================================
# TODO 5 — Registro del candidato, SIN promover
# =============================================================================
@task(name="registrar_candidato_clasificacion")
def registrar_candidato_clasificacion(
    modelo: dict[str, Any],
    metricas: list[dict[str, float]],
    nombre_modelo: str = MODELO_CLASIFICACION,
) -> str:
    """Registra la version y le pone el alias `candidate`. No promueve.

    Requisitos:
    - alias `ALIAS_CANDIDATO`, nunca `champion`;
    - tags con la evidencia: mejor f1 y el umbral con el que se obtuvo;
    - prohibida la API de stages de MLflow y las URIs `models:/<nombre>/<stage>`.

    TODO 5: implementa el cuerpo y devuelve la version como string.
    """
    raise NotImplementedError("TODO 5")


# =============================================================================
# TODO 6 — El flow
# =============================================================================
@flow(name="clasificacion-viaje-largo", log_prints=True)
def clasificacion_flow(registrar: bool = True) -> dict[str, Any]:
    """Pipeline de clasificacion: datos -> entrenar -> evaluar -> registrar.

    Requisitos:
    - entrena con `PARTICIONES_TRAIN` y evalua en `PARTICION_VALID`;
    - devuelve un dict con `run_id`, `model_version` y las metricas;
    - el valor de retorno determina el estado final del flow.

    TODO 6: implementa el cuerpo conectando las tasks anteriores.
    """
    raise NotImplementedError("TODO 6")


if __name__ == "__main__":
    print(clasificacion_flow())
