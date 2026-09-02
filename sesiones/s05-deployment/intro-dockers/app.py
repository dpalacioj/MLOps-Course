"""App minima de FastAPI para el primer contacto con contenedores (S05, bloque A).

Que problema resuelve
---------------------
Nada de MLOps todavia. Esta app existe para separar dos preguntas que en clase se
mezclan siempre:

1. "Como corre mi codigo en un contenedor?" -> mecanica de Docker.
2. "Como sirvo un modelo?" -> el resto de la sesion.

Si se aprenden juntas, cuando algo falla no se sabe si el problema es el modelo,
el registry o el `docker run`. Aqui la app no tiene modelo: si el contenedor
responde, Docker esta bien.

Una sola app, no dos
--------------------
La forma habitual de resolver esto es tener `app.py` y `app_docker.py`: dos
archivos identicos al 95% que difieren en el color del fondo y en el `host` del
`uvicorn.run`. Es el anti-patron central del curso aplicado a un ejemplo de
juguete: dos copias del mismo codigo que se desincronizan en el primer cambio.

Aqui se hace como en un servicio real: **un solo artefacto, y el entorno entra
como configuracion**. `ENTORNO` es una variable que el `Dockerfile`
fija en `docker` y que en local no esta puesta. Es el mismo principio que aplica
`src/taxi/api/main.py` con `TAXI_MODELO_URI`.
"""

from __future__ import annotations

import os
import random
import socket
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

#: Donde cree estar corriendo el proceso. Lo fija el Dockerfile; en local no
#: existe y aplica el default. Es un dato de PRESENTACION: no cambia ninguna
#: decision del codigo, solo lo que se muestra en la pagina.
ENTORNO: str = os.getenv("ENTORNO", "local")

#: Puerto de escucha. Configurable porque el mapeo de puertos es una decision de
#: despliegue, no del codigo.
PUERTO: int = int(os.getenv("PUERTO", "5000"))

#: Interfaz de escucha. En local, 127.0.0.1: el servicio no se expone a la red
#: del salon. Dentro del contenedor hace falta 0.0.0.0 para que el `-p` funcione,
#: y ese valor lo pone el CMD del Dockerfile, no este archivo.
HOST: str = os.getenv("HOST", "127.0.0.1")

GATITOS: tuple[str, ...] = (
    "https://cataas.com/cat",
    "https://cataas.com/cat/cute",
    "https://cataas.com/cat/says/Hola",
    "https://cataas.com/cat/says/Docker",
    "https://cataas.com/cat/says/MLOps",
)

app = FastAPI(title="Gatitos App", version="2.0.0")
plantillas = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request) -> Any:
    """Pagina con un gatito aleatorio y el entorno donde corre el proceso.

    El `hostname` se muestra a proposito: en local es el nombre del equipo y en
    el contenedor es el id corto del contenedor. Es la forma mas rapida de
    demostrar que hay aislamiento sin explicar namespaces.
    """
    return plantillas.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "gatito_url": random.choice(GATITOS),
            "entorno": ENTORNO,
            "es_docker": ENTORNO == "docker",
            "hostname": socket.gethostname(),
        },
    )


@app.get("/health")
def salud() -> dict[str, str]:
    """Liveness check.

    Existe desde el primer ejemplo del curso porque es lo que consulta el
    `HEALTHCHECK` de la imagen y, mas adelante, el orquestador. Una app sin
    `/health` obliga a adivinar si esta viva.
    """
    return {"status": "ok", "entorno": ENTORNO, "hostname": socket.gethostname()}


if __name__ == "__main__":
    # Solo para correr en local con `uv run app.py`. En el contenedor arranca
    # uvicorn como CMD de la imagen.
    import uvicorn

    print(f"Gatitos App en http://{HOST}:{PUERTO}  (entorno={ENTORNO})")
    uvicorn.run(app, host=HOST, port=PUERTO)
