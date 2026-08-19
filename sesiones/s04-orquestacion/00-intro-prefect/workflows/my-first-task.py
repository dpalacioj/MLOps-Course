"""Paso: de un flow monolitico a un flow con tasks.

La misma logica de `weather1-bare.py`, ahora partida en dos `@task`. Lo que se
gana: cada paso tiene estado propio, asi que cuando algo falla se sabe *cual*
paso fallo; y Prefect deriva el orden de ejecucion de las dependencias de datos
entre tasks, sin que haya que declararlo.
"""

import httpx
import pandas as pd
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_table_artifact


@task(retries=2, retry_delay_seconds=[5, 15])
def obtener_temperatura(lat: float, lon: float) -> float:
    """Consulta la API del clima. Los retries van en la task que habla con la red."""
    logger = get_run_logger()
    respuesta = httpx.get(
        "https://api.open-meteo.com/v1/forecast/",
        params={"latitude": lat, "longitude": lon, "hourly": "temperature_2m"},
        timeout=30,
    )
    respuesta.raise_for_status()
    temperatura = float(respuesta.json()["hourly"]["temperature_2m"][0])
    logger.info("Temperatura pronosticada: %.1f C", temperatura)
    return temperatura


@task
def guardar_temperatura(temperatura: float, destino: str = "weather.csv") -> str:
    """Persiste el dato y publica un artifact con lo que quedo guardado."""
    logger = get_run_logger()
    df = pd.DataFrame({"temperatura_celsius": [temperatura]})
    df.to_csv(destino, index=False)

    create_table_artifact(
        key="datos-de-clima",
        table=df.to_dict("records"),
        description="Temperatura registrada por esta corrida.",
    )
    logger.info("Guardado en %s", destino)
    return destino


@flow(log_prints=True)
def pipeline_clima(lat: float = 6.2476, lon: float = -75.5658) -> str:
    """Flow de dos pasos: obtener y guardar."""
    temperatura = obtener_temperatura(lat, lon)
    # `guardar_temperatura` depende del resultado de la task anterior: de ahi
    # sale el grafo, no de una declaracion explicita de dependencias.
    return guardar_temperatura(temperatura)


if __name__ == "__main__":
    print(pipeline_clima())
