# syntax=docker/dockerfile:1
# ^ Directiva del parser. Tiene que ser la PRIMERA linea: si aparece despues de
# un comentario, Docker la trata como comentario y la ignora en silencio.
#
# =============================================================================
# Imagen de la app de gatitos — la version MINIMA correcta
# =============================================================================
# Este Dockerfile es deliberadamente simple: una sola etapa. Su trabajo es
# ensenar cinco cosas y nada mas.
#
#   1. base slim y con version fija (no `python:latest`)
#   2. capas ordenadas: dependencias antes que codigo
#   3. dependencias desde un LOCKFILE, nunca pines a mano
#   4. usuario sin privilegios
#   5. HEALTHCHECK que de verdad funciona en esta imagen
#
# Lo que NO hace, y se agrega en el Dockerfile de la raiz del repositorio:
# multi-stage, ARGs de version, cache mounts de BuildKit y una etapa aparte para
# el servidor de MLflow. Comparar los dos archivos es el ejercicio.
#
# Diferencias con la version anterior de este mismo archivo:
#   - `pip install -r requirements.txt` -> `uv sync --locked` (ver pyproject.toml)
#   - corria como root -> usuario `gatos`
#   - sin healthcheck -> HEALTHCHECK con el interprete de la imagen
#   - `COPY app_docker.py app.py` (dos copias del codigo) -> un solo `app.py`
#     mas la variable de entorno ENTORNO
# =============================================================================

FROM python:3.11-slim-bookworm

# El binario de uv se copia de su imagen oficial en lugar de instalarlo con pip:
# asi la imagen final no arrastra pip ni el cache de la descarga. La version esta
# fija porque la herramienta que lee el lock es parte del entorno reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv

# Fuera del arbol del proyecto: el venv no depende de /app.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
# El interprete es el de la imagen base; sin esto uv podria bajar otro Python.
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PYTHON=/usr/local/bin/python3
ENV UV_LINK_MODE=copy
# Los logs salen a stdout en el momento. Sin esto, `docker logs` de un contenedor
# que acaba de fallar sale vacio.
ENV PYTHONUNBUFFERED=1
# El venv al frente del PATH: `uvicorn` es el del entorno resuelto por el lock.
ENV PATH="/opt/venv/bin:$PATH"

# Marca el entorno. Es lo unico que distingue esta ejecucion de la local: el
# codigo es identico.
ENV ENTORNO=docker

WORKDIR /app

# --- Capa 1: solo el manifiesto y el lock ----------------------------------
# Se copian ANTES del codigo. Las dependencias cambian pocas veces y el codigo
# cambia en cada edicion: con este orden, tocar `app.py` reutiliza la capa de
# dependencias en lugar de reinstalarlas.
#
# `--locked` falla si `uv.lock` no esta sincronizado con `pyproject.toml`, en
# lugar de re-resolver en silencio. Es lo que hace el build reproducible.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# --- Capa 2: el codigo -----------------------------------------------------
# Invertir el orden de estas dos capas es el error de cache mas comun: cada
# cambio de una linea de Python reinstalaria FastAPI.
COPY app.py ./
COPY templates ./templates

# Usuario sin privilegios. Si alguien logra ejecucion de codigo en el proceso,
# con root dentro del contenedor tiene mucho mas margen.
RUN groupadd --system --gid 1001 gatos \
    && useradd --system --uid 1001 --gid gatos --no-create-home gatos \
    && chown -R gatos:gatos /app
USER gatos

EXPOSE 5000

# HEALTHCHECK con Python, no con curl.
#
# `curl` NO existe en `python:*-slim`. Un `HEALTHCHECK CMD curl -f ...` sobre esta
# base falla siempre, el contenedor queda permanentemente `unhealthy` y cualquier
# `depends_on: service_healthy` se cuelga esperando. El interprete que ya esta en
# la imagen resuelve lo mismo sin agregar dependencias.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=4).status == 200 else 1)"]

# 0.0.0.0 es correcto AQUI y solo aqui: dentro del contenedor hay que escuchar en
# todas las interfaces para que el `-p` funcione. El aislamiento lo da Docker, no
# el bind. En un proceso local, 0.0.0.0 expone el servicio a toda la red.
#
# Forma exec (lista, sin shell): el proceso queda como PID 1 y recibe SIGTERM
# directo, asi que uvicorn puede cerrar conexiones antes de morir.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]
