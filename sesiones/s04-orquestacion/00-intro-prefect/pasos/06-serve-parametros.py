"""Paso 6 de la progresion: `serve()` con parametros.

El mismo flow, con valores por defecto que se pueden cambiar desde la UI sin
tocar el codigo. Es la forma de reentrenar con otros datos, o de correr el mismo
pipeline para otra ciudad, sin duplicar archivos.
"""

import httpx
from prefect import flow


@flow(log_prints=True)
def fetch_weather(lat: float = 38.9, lon: float = -77.0) -> float:
    """Devuelve la temperatura pronosticada en unas coordenadas."""
    base_url = "https://api.open-meteo.com/v1/forecast/"
    temps = httpx.get(
        base_url,
        # `temperature_2m`: temperatura a 2 m del suelo, la convencion
        # meteorologica estandar.
        params={"latitude": lat, "longitude": lon, "hourly": "temperature_2m"},
        timeout=30,
    )
    temps.raise_for_status()
    forecasted_temp = float(temps.json()["hourly"]["temperature_2m"][0])
    print(f"Temperatura pronosticada: {forecasted_temp} C")
    return forecasted_temp


if __name__ == "__main__":
    # Medellin. Los parametros del deployment tienen que ser serializables a
    # JSON: por eso los flows del curso reciben strings y numeros, no objetos.
    fetch_weather.serve(
        name="clima-con-parametros",
        parameters={"lat": 6.2476, "lon": -75.5658},
    )
