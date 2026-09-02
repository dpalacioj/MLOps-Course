# syntax=docker/dockerfile:1
# ^ Directiva del parser. Tiene que ser la PRIMERA linea del archivo: si aparece
# despues de un comentario o de una instruccion, Docker la trata como un
# comentario cualquiera y la ignora en silencio, sin avisar de nada. Es la razon
# por la que se lee este bloque de cabecera DESPUES de la directiva y no antes.
#
# =============================================================================
# Imagen de la API de inferencia — build multi-stage con uv
# =============================================================================
# El Dockerfile anterior de esta API garantizaba el fallo mas dificil de
# diagnosticar del curso. Copiaba `pyproject.toml` a la imagen y acto seguido lo
# ignoraba, instalando a mano:
#
#     RUN pip install --no-cache-dir mlflow==2.17.2 xgboost==2.1.2 scikit-learn==1.5.2
#
# El artefacto que servia esa imagen se habia generado con mlflow 3.x,
# xgboost 3.2 y scikit-learn 1.6.1. Resultado: `InconsistentVersionWarning` en
# cada arranque, `pickle` deserializando estimadores de otra version y
# predicciones que podian diferir de las validadas por el gate de promocion. Un
# modelo aprobado en CI y una imagen que sirve otra cosa.
#
# La regla que corrige esto: **las versiones se resuelven UNA vez, en `uv.lock`,
# y todos los entornos —local, CI, entrenamiento, serving— instalan de ahi.**
# Ningun pin escrito a mano en este archivo.
#
# Orden de las etapas: `runtime` va AL FINAL a proposito. `docker build` sin
# `--target` construye la ultima etapa, y el job `imagen` del CI depende de eso.
# Mover `runtime` hacia arriba haria que el CI verificara la imagen equivocada.
# =============================================================================

ARG PYTHON_VERSION=3.11
# uv pinneado: la herramienta que resuelve el lock es parte del entorno
# reproducible. Un `uv` distinto puede rechazar el lock (`--locked`) o resolver
# diferente; que la version flote seria el mismo error que este archivo corrige.
ARG UV_VERSION=0.8.17
ARG MLFLOW_VERSION=3.15.1


# =============================================================================
# Etapa 0 — el binario de uv, pinneado
# =============================================================================
# Se declara como etapa con nombre para que `COPY --from` pueda usar el ARG. La
# imagen es distroless y solo contiene el binario estatico.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv-bin


# =============================================================================
# Etapa 1 — builder: resuelve e instala dependencias desde uv.lock
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

# Patron oficial de uv: se copia el binario en lugar de instalarlo con pip.
# Evita meter pip/curl en el builder solo para bajar la herramienta.
COPY --from=uv-bin /uv /bin/uv

# Precompila a .pyc dentro de la imagen: el arranque del contenedor no paga la
# compilacion del bytecode en el primer request.
ENV UV_COMPILE_BYTECODE=1
# copy en lugar de hardlink: el cache de uv y el venv estan en filesystems
# distintos dentro del build y el hardlink fallaria con un aviso en cada paquete.
ENV UV_LINK_MODE=copy
# El interprete es el de la imagen base. Sin estas dos, uv podria descargar otro
# Python y la imagen acabaria con dos.
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PYTHON=/usr/local/bin/python3
# Fuera del arbol del proyecto: asi el venv no depende de /app y se copia solo a
# la etapa de runtime.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# --- Capa 1: solo el manifiesto y el lock ---------------------------------
# Se copian ANTES del codigo fuente. Las dependencias cambian pocas veces y el
# codigo cambia en cada commit: con este orden, editar `main.py` reutiliza la
# capa de dependencias en lugar de reinstalar 300 MB de paquetes.
COPY pyproject.toml uv.lock ./

# --no-install-project: instala SOLO las dependencias. El proyecto se instala en
# la capa siguiente, cuando ya esta el codigo.
# --locked: falla si el lock no esta sincronizado con pyproject.toml, en lugar de
#   re-resolver en silencio. Es lo que convierte el build en reproducible.
# --no-dev: ruff, mypy y pytest no tienen nada que hacer en la imagen de runtime;
#   son superficie de ataque y peso muerto.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --no-editable

# --- Capa 2: el proyecto ---------------------------------------------------
# README.md hace falta porque `pyproject.toml` lo declara como `readme` y
# hatchling lo lee al construir el wheel.
COPY README.md ./
COPY src ./src

# --no-editable: el paquete se copia dentro del venv como un wheel instalado, en
# lugar de dejar un .pth apuntando a /app/src. Asi la imagen de runtime no
# necesita el codigo fuente en disco: menos superficie y una sola copia del
# paquete.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# =============================================================================
# Etapa 2 — servidor de MLflow para el stack local
# =============================================================================
# NO es la imagen de la API. La usa `docker-compose.yml` con
# `target: mlflow-server`.
#
# Aqui SI hay dos pines escritos a mano, y la diferencia con el anti-patron de
# arriba es exactamente el punto pedagogico:
#
# - Alli se pinneaban a mano las librerias que **deserializan el modelo**. Esas
#   tienen que coincidir con las del entrenamiento o el artefacto se corrompe en
#   silencio.
# - Aqui se instalan el driver de Postgres y el cliente S3 de un servicio de
#   **infraestructura**, que no toca el pickle del modelo. La imagen oficial de
#   MLflow no los incluye, y ninguno de los dos esta en `uv.lock` porque el
#   proyecto no los necesita.
#
# La solucion mas limpia a largo plazo es declararlos en un extra de
# `pyproject.toml` y dejar que uv los resuelva. Se documenta la deuda en lugar de
# esconderla.
FROM ghcr.io/mlflow/mlflow:v${MLFLOW_VERSION} AS mlflow-server

# Sin pin de version exacta a proposito: son drivers, no runtime de modelos.
# Un floor pin evita el otro extremo (`latest` silencioso) sin fijar una version
# que quede sin parches de seguridad.
RUN pip install --no-cache-dir "psycopg2-binary>=2.9.9" "boto3>=1.34"

# La imagen oficial de MLflow corre como root. Se crea un usuario sin
# privilegios, igual que en la etapa de runtime: **ninguna imagen construida en
# este repositorio corre como root**.
#
# Matiz honesto: eso no vuelve todo el stack rootless. Postgres baja a su propio
# usuario internamente, pero los contenedores de MinIO si corren como root porque
# su imagen oficial esta hecha asi. Cambiarlo requiere ajustar los permisos del
# volumen y no aporta a lo que el curso ensena; lo que si esta bajo nuestro
# control son estas dos imagenes.
RUN groupadd --system --gid 1001 mlflow \
    && useradd --system --uid 1001 --gid mlflow --create-home mlflow
USER mlflow

EXPOSE 5001

# El comando concreto (backend store, artifacts destination, allowed hosts) vive
# en docker-compose.yml: es configuracion de despliegue, no de la imagen.


# =============================================================================
# Etapa 3 — runtime: lo minimo para servir. ULTIMA ETAPA (ver cabecera).
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="nyc-taxi-duration-api" \
      org.opencontainers.image.description="API de inferencia de duracion de viajes de green taxi (curso MLOps)." \
      org.opencontainers.image.source="https://github.com/" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1
# Sin buffer: los logs salen a stdout en el momento, no cuando se llena el
# buffer. Sin esto, `docker logs` de un contenedor que acaba de fallar aparece
# vacio y el diagnostico se vuelve adivinanza.
ENV PYTHONUNBUFFERED=1
# El venv del builder se antepone al PATH: `python` y `uvicorn` son los del
# entorno resuelto por el lock, no los del sistema.
ENV PATH="/opt/venv/bin:$PATH"
# Default seguro: la imagen arranca sin modelo si nadie configura la URI.
# `/health` responde 200 con model_loaded=false y `/predict` devuelve 503. Es lo
# que permite verificar la imagen en CI sin levantar el registry.
ENV TAXI_MODELO_URI=ninguno

# Usuario no-root creado explicitamente ANTES de copiar, para poder asignar la
# propiedad en el COPY y no pagar una capa extra con `chown -R`.
#
# Por que importa: si un atacante logra ejecucion de codigo en el proceso, con
# root dentro del contenedor tiene muchisimo mas margen (montajes, capabilities,
# escapes conocidos). El CI lo verifica: hay un paso que falla si el UID es 0.
RUN groupadd --system --gid 1001 taxi \
    && useradd --system --uid 1001 --gid taxi --create-home --shell /usr/sbin/nologin taxi \
    && install -d -o taxi -g taxi /app

# El WORKDIR pertenece al usuario de la aplicacion. Si quedara de root, cualquier
# libreria que escriba un archivo temporal en el directorio actual (matplotlib,
# el cache de mlflow) fallaria con un PermissionError que no menciona los
# permisos del WORKDIR.
WORKDIR /app

# Se copia UNICAMENTE el venv. El codigo fuente ya esta instalado dentro
# (--no-editable), asi que la imagen final no lleva ni `src/`, ni `uv`, ni el
# cache de compilacion del builder.
COPY --from=builder --chown=taxi:taxi /opt/venv /opt/venv

USER taxi

EXPOSE 8000

# HEALTHCHECK con Python, no con curl.
#
# El compose anterior definia `test: ["CMD","curl","-f",...]` sobre una imagen
# `python:3.11-slim`, que no trae curl. El comando fallaba siempre, el contenedor
# quedaba permanentemente `unhealthy` y cualquier `depends_on: service_healthy`
# se colgaba. Instalar curl solo para esto agregaria una dependencia y ~10 MB;
# el interprete que ya esta en la imagen resuelve lo mismo.
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# 0.0.0.0 es correcto AQUI y solo aqui: dentro del contenedor hay que escuchar en
# todas las interfaces para que el port mapping funcione. El aislamiento lo da
# Docker, no el bind. En un proceso local, en cambio, 0.0.0.0 expone el servicio
# a toda la red del equipo (por eso `main.py` usa 127.0.0.1 por defecto).
#
# Forma exec (lista, sin shell): el proceso queda como PID 1 y recibe SIGTERM
# directamente, asi que uvicorn puede cerrar conexiones antes de morir. Con la
# forma shell, `sh` se traga la senal y Docker mata el contenedor a los 10s.
CMD ["uvicorn", "taxi.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
