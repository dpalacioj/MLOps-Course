"""Paso 5 de la progresion: `deploy()` contra un work pool.

Diferencia con `serve()`: `serve()` deja este proceso vivo y ejecutando;
`deploy()` registra un deployment **persistente** en el servidor y la ejecucion
la hace un **worker** que toma trabajo de un work pool. Cuando este script
termina, el deployment sigue existiendo.

Bug corregido respecto a la version anterior de este archivo: llamaba a
`.deploy()` **sin `work_pool_name`** (linea 19), y en Prefect 3 ese argumento es
obligatorio. Sin work pool no hay quien ejecute el flow.

Antes de correrlo:

    prefect work-pool create curso-mlops --type process
    prefect worker start --pool curso-mlops      # en otra terminal
"""

import httpx
from prefect import flow
from prefect.schedules import Cron


@flow
def fetch_weather(lat: float = 38.9, lon: float = -77.0) -> float:
    """Consulta la temperatura pronosticada en unas coordenadas."""
    base_url = "https://api.open-meteo.com/v1/forecast/"
    temps = httpx.get(
        base_url,
        params={"latitude": lat, "longitude": lon, "hourly": "temperature_2m"},
        timeout=30,
    )
    temps.raise_for_status()
    forecasted_temp = float(temps.json()["hourly"]["temperature_2m"][0])
    print(f"Temperatura pronosticada: {forecasted_temp} C")
    return forecasted_temp


if __name__ == "__main__":
    fetch_weather.deploy(
        name="clima-medellin",
        # Obligatorio en Prefect 3. Los agents (`prefect agent start`) fueron
        # eliminados: el modelo es workers + work pools.
        work_pool_name="curso-mlops",
        # Un work pool de tipo `process` ejecuta en el entorno del worker, asi
        # que no hay imagen que construir ni publicar.
        image=None,
        build=False,
        push=False,
        # `schedules=[...]` en plural. El `schedule=` singular con un dict es la
        # forma de Prefect 2.
        schedules=[Cron("*/10 * * * *", timezone="America/Bogota")],
        parameters={"lat": 6.2476, "lon": -75.5658},  # Medellin
        tags=["s04", "demo"],
    )
