"""Paso 3 de la progresion: `serve()` con schedule.

`cron="* * * * *"` (cada minuto) sirve para *ver* el mecanismo en clase. En
produccion la frecuencia se deriva de cuando llegan datos nuevos, no de las ganas
de ver runs en la pantalla: ver `taxi/flows/deploy.py` y la discusion del
anti-patron de reentrenar cada dos minutos.

    * * * * *
    | | | | |
    | | | | +-- dia de la semana (0-6, 0 = domingo)
    | | | +---- mes (1-12)
    | | +------ dia del mes (1-31)
    | +-------- hora (0-23)
    +---------- minuto (0-59)

| Expresion | Significado |
|---|---|
| `* * * * *` | cada minuto (solo para pruebas) |
| `0 2 * * *` | todos los dias a las 02:00 |
| `0 9 * * 1-5` | lunes a viernes a las 09:00 |
| `0 3 5 * *` | el dia 5 de cada mes a las 03:00 |
"""

import httpx
from prefect import flow
from prefect.schedules import Cron


@flow
def fetch_weather(lat: float = 38.9, lon: float = -77.0) -> float:
    """Devuelve la temperatura pronosticada en unas coordenadas."""
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
    # `schedules=[...]` (plural) permite declarar la zona horaria. Sin zona, el
    # cron se interpreta en UTC. El atajo `cron="* * * * *"` tambien es valido.
    fetch_weather.serve(
        name="clima-programado",
        schedules=[Cron("* * * * *", timezone="America/Bogota")],
    )
