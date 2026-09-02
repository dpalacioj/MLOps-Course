"""Variante del paso 1: `@flow()` con parentesis.

No cambia nada funcional respecto a `01-flow.py`; las dos formas son
validas. Este es el archivo al que apunta el `entrypoint` de `prefect.yaml`.
"""

import httpx
from prefect import flow


@flow()
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
    fetch_weather()
