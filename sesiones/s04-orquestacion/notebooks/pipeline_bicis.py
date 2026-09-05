"""Pipeline de entrenamiento e inferencia sobre el dataset de bicis, con Prefect.

Generado por `02-pipeline-ml-con-prefect.ipynb`: el notebook construye estas tasks
celda por celda y al final escribe este archivo. Para cambiarlo se edita el notebook
(o `_generar_notebooks.py`) y se vuelve a ejecutar.

Uso, desde esta carpeta:
    uv run python pipeline_bicis.py
"""

import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pandera.pandas as pa
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact
from prefect.cache_policies import INPUTS, TASK_SOURCE
from prefect.runtime import flow_run
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

# La raiz del repositorio se busca hacia arriba hasta encontrar pyproject.toml. Sin
# rutas absolutas: el notebook corre desde su carpeta y este archivo desde cualquier
# sitio (incluido /app dentro de un contenedor).
_inicio = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
RAIZ = _inicio
while not (RAIZ / "pyproject.toml").exists() and RAIZ.parent != RAIZ:
    RAIZ = RAIZ.parent

URL_HF = "https://huggingface.co/datasets/t22000t/bike-sharing-tabular/resolve/main/hour.csv"
URL_UCI = "https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip"
CACHE_CSV = RAIZ / "data" / "external" / "bicis-por-hora.csv"
PREDICCIONES = RAIZ / "data" / "processed" / "predicciones-bicis.parquet"

COLUMNAS = {
    "instant": "indice",
    "dteday": "fecha",
    "season": "estacion",
    "yr": "anio",
    "mnth": "mes",
    "hr": "hora",
    "holiday": "festivo",
    "weekday": "dia_semana",
    "workingday": "dia_laboral",
    "weathersit": "clima",
    "temp": "temperatura",
    "atemp": "sensacion_termica",
    "hum": "humedad",
    "windspeed": "viento",
    "casual": "casuales",
    "registered": "registrados",
    "cnt": "total",
}

TARGET = "total"
# `casuales` y `registrados` NO estan: suman exactamente `total`. Incluirlas seria
# predecir el target con el target (fuga de informacion), y el contrato lo verifica.
FEATURES = [
    "estacion",
    "anio",
    "mes",
    "hora",
    "festivo",
    "dia_semana",
    "dia_laboral",
    "clima",
    "temperatura",
    "sensacion_termica",
    "humedad",
    "viento",
]


@task(retries=3, retry_delay_seconds=[2, 5, 10], retry_jitter_factor=0.2)
def descargar(destino: Path = CACHE_CSV) -> pd.DataFrame:
    """Baja el CSV una vez y lo guarda en disco. Los reintentos cubren la red."""
    logger = get_run_logger()
    if destino.exists():
        logger.info("cache en disco: %s", destino.relative_to(RAIZ))
        return pd.read_csv(destino)
    try:
        crudo = pd.read_csv(URL_HF)
        logger.info("descargado de Hugging Face")
    except Exception as exc:  # cualquier fallo de red cae al respaldo
        logger.warning("Hugging Face no respondio (%s); usando UCI", type(exc).__name__)
        respuesta = httpx.get(URL_UCI, timeout=60, follow_redirects=True)
        respuesta.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(respuesta.content)) as zf:
            crudo = pd.read_csv(zf.open("hour.csv"))
    df = crudo.rename(columns=COLUMNAS)
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False)
    return df


CONTRATO = pa.DataFrameSchema(
    {
        "fecha": pa.Column(str),
        "anio": pa.Column(int, pa.Check.isin([0, 1])),
        "mes": pa.Column(int, pa.Check.in_range(1, 12)),
        "hora": pa.Column(int, pa.Check.in_range(0, 23)),
        "clima": pa.Column(int, pa.Check.in_range(1, 4)),
        "temperatura": pa.Column(float, pa.Check.in_range(0, 1)),
        "humedad": pa.Column(float, pa.Check.in_range(0, 1)),
        "viento": pa.Column(float, pa.Check.ge(0)),
        "casuales": pa.Column(int, pa.Check.ge(0)),
        "registrados": pa.Column(int, pa.Check.ge(0)),
        "total": pa.Column(int, pa.Check.ge(0)),
    },
    checks=[
        # La regla que justifica excluir dos columnas de FEATURES, verificada y no supuesta.
        pa.Check(lambda d: d["casuales"] + d["registrados"] == d["total"], name="total_es_la_suma"),
    ],
    strict=False,  # las columnas que no se nombran pasan sin revisarse
)


@task
def validar(df: pd.DataFrame) -> pd.DataFrame:
    """Detiene la ejecucion si los datos no cumplen el contrato. Reporta todos los errores."""
    validado = CONTRATO.validate(df, lazy=True)
    get_run_logger().info("contrato OK: %d filas, %d columnas", *validado.shape)
    return validado


@task
def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    """Se queda con FEATURES + TARGET + fecha. Lo demas no entra al modelo."""
    return df[["fecha", *FEATURES, TARGET]].copy()


@task
def dividir_temporal(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """2011 entrena, 2012 valida. Nunca un split aleatorio: es una serie en el tiempo."""
    entrena = df[df["anio"] == 0]
    valida = df[df["anio"] == 1]
    get_run_logger().info(
        "entrena %d filas (2011) | valida %d filas (2012)", len(entrena), len(valida)
    )
    return entrena, valida


@task(cache_policy=INPUTS + TASK_SOURCE, cache_expiration=timedelta(days=1))
def entrenar(entrena: pd.DataFrame, n_iteraciones: int, tasa_aprendizaje: float):
    """Entrena el regresor. Cacheado: mismos datos + mismos hiperparametros = mismo modelo.

    Es seguro cachear porque `random_state` esta fijo y el DataFrame de entrada es parte
    de la clave: si los datos cambian, se reentrena solo. Sin `random_state`, cachear
    seria servir un modelo que nadie evaluo.
    """
    modelo = HistGradientBoostingRegressor(
        max_iter=n_iteraciones, learning_rate=tasa_aprendizaje, random_state=42
    )
    modelo.fit(entrena[FEATURES], entrena[TARGET])
    return modelo


@task
def evaluar(modelo, entrena: pd.DataFrame, valida: pd.DataFrame) -> dict:
    """RMSE y MAE del modelo contra el baseline de predecir la media de 2011."""
    y = valida[TARGET]
    baseline = np.full(len(valida), entrena[TARGET].mean())
    pred = modelo.predict(valida[FEATURES])
    metricas = {
        "rmse_baseline": round(float(root_mean_squared_error(y, baseline)), 1),
        "rmse_modelo": round(float(root_mean_squared_error(y, pred)), 1),
        "mae_modelo": round(float(mean_absolute_error(y, pred)), 1),
    }
    filas = "\n".join(f"| {k} | {v} |" for k, v in metricas.items())
    create_markdown_artifact(
        key="bicis-metricas",
        markdown=f"# Metricas en 2012\n\n| metrica | valor |\n|---|---|\n{filas}\n",
        description="Validacion temporal: entrena 2011, evalua 2012.",
    )
    get_run_logger().info("metricas: %s", metricas)
    return metricas


@task
def predecir_lote(modelo, valida: pd.DataFrame, mes: int, destino: Path = PREDICCIONES) -> Path:
    """Predice un mes completo y guarda cada fila con el id de la ejecucion que la produjo."""
    lote = valida[valida["mes"] == mes].copy()
    lote["prediccion"] = modelo.predict(lote[FEATURES]).round(0)
    # Trazabilidad por fila: de que ejecucion salio cada prediccion y cuando.
    lote["flow_run_id"] = flow_run.id
    lote["flow_run_name"] = flow_run.name
    lote["generado_en"] = datetime.now(UTC).isoformat(timespec="seconds")
    destino.parent.mkdir(parents=True, exist_ok=True)
    lote.to_parquet(destino, index=False)
    get_run_logger().info("%d predicciones en %s", len(lote), destino.relative_to(RAIZ))
    return destino


@flow(log_prints=True)
def pipeline_bicis(
    n_iteraciones: int = 300, tasa_aprendizaje: float = 0.1, mes_a_predecir: int = 12
) -> dict:
    """Descarga -> valida -> features -> split temporal -> entrena -> evalua -> predice."""
    crudo = descargar()
    limpio = validar(crudo)
    tabla = construir_features(limpio)
    entrena, valida = dividir_temporal(tabla)
    modelo = entrenar(entrena, n_iteraciones, tasa_aprendizaje)
    metricas = evaluar(modelo, entrena, valida)
    predecir_lote(modelo, valida, mes_a_predecir)
    return metricas


if __name__ == "__main__":
    print(pipeline_bicis())
