"""Paso 1 de la progresion: un flow minimo.

Una funcion normal de Python que consulta una API publica del clima. La unica
diferencia con codigo normal es el decorador `@flow`. Con eso, Prefect ya le pone
nombre a la corrida, mide su duracion, captura los logs y reporta su estado
final.
"""

import httpx
from prefect import flow


@flow
def fetch_weather(lat: float = 38.9, lon: float = -77.0) -> float:
    """Devuelve la temperatura pronosticada en unas coordenadas."""
    base_url = "https://api.open-meteo.com/v1/forecast/"
    # `timeout` explicito: sin el, una peticion colgada bloquea el flow
    # indefinidamente y ningun retry se dispara.
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
    fetch_weather()
