"""Paso 2 de la progresion: `serve()`.

El proceso queda vivo haciendo polling de corridas programadas, y el deployment
aparece en la UI. Ctrl+C lo detiene y el deployment desaparece: `serve()` no
persiste infraestructura.

Antes de correrlo, en otra terminal:

    prefect server start
    prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api

Sin ese `config set`, cada `.serve()` levanta un servidor temporal propio y nada
aparece en el dashboard. Es el error mas comun de la sesion.
"""

import httpx
from prefect import flow


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
    fetch_weather.serve(name="clima-manual")
