"""Paso 8 de la progresion: `deploy()` contra un work pool.

Diferencia con `serve()`: `serve()` deja este proceso vivo y ejecutando;
`deploy()` registra un deployment **persistente** en el servidor y la ejecucion
la hace un **worker** que toma trabajo de un work pool. Cuando este script
termina, el deployment sigue existiendo.

Dos argumentos que parecen opcionales y no lo son:

1. `work_pool_name`. En Prefect 3 es obligatorio: sin work pool no hay quien
   ejecute el flow.
2. `flow.from_source(...)`. Sin el, `.deploy()` falla con
   `ValueError: Either an image or remote storage location must be provided`.
   La razon es la misma que hace interesante a este paso: el worker es **otro
   proceso**, arranca mas tarde y necesita saber de donde traer el codigo. Un
   deployment tiene que declarar su origen —una imagen de Docker, un repositorio
   git, o una ruta local— y `.deploy()` a secas no declara ninguno.

Ojo con `source=`: la ruta se calcula en tiempo de ejecucion a partir de
`__file__`, no se escribe a mano. Una ruta absoluta hardcodeada aqui funciona en
el disco de quien la escribio y en ningun otro; es lo que vigila el hook
`scripts/hooks/sin_rutas_absolutas.py`.

Antes de correrlo:

    prefect work-pool create curso-mlops --type process
    prefect worker start --pool curso-mlops      # en otra terminal
"""

from pathlib import Path

import httpx
from prefect import flow
from prefect.schedules import Cron


@flow(log_prints=True)
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
    # `from_source` declara de donde sale el codigo. Con una ruta local, Prefect
    # genera un paso de `pull` llamado `set_working_directory`: el worker se
    # mueve a esta carpeta antes de importar el flow. Se ve en el log del worker.
    # Con un pool de tipo `docker` o `kubernetes`, aqui iria una imagen o un
    # repositorio git en vez de la ruta, y el resto del codigo no cambiaria.
    origen = flow.from_source(
        source=str(Path(__file__).parent),
        entrypoint=f"{Path(__file__).name}:fetch_weather",
    )
    origen.deploy(
        name="clima-medellin",
        # Obligatorio en Prefect 3. Los agents (`prefect agent start`) fueron
        # eliminados: el modelo es workers + work pools.
        work_pool_name="curso-mlops",
        # Un work pool de tipo `process` ejecuta en el entorno del worker, asi
        # que no hay imagen que construir ni publicar.
        build=False,
        push=False,
        # `schedules=[...]` en plural. El `schedule=` singular con un dict es la
        # forma de Prefect 2.
        schedules=[Cron("*/10 * * * *", timezone="America/Bogota")],
        parameters={"lat": 6.2476, "lon": -75.5658},  # Medellin
        tags=["s04", "demo"],
    )
