# syntax=docker/dockerfile:1
# ^ Directiva del parser. Tiene que ser la PRIMERA linea: si aparece despues de
# un comentario o de una instruccion, Docker la trata como comentario y la ignora
# en silencio.
#
# =============================================================================
# Imagen de la API de inferencia — multi-stage con uv
# =============================================================================
# La regla central de este archivo: **las versiones se resuelven UNA vez, en
# uv.lock, y todos los entornos (local, CI, entrenamiento, serving) instalan de
# ahi.** Ningun pin escrito a mano aqui.
#
# Por que importa tanto: si la imagen instala `pip install scikit-learn==1.5` a
# mano y el artefacto se entreno con 1.6, la deserializacion puede "funcionar"
# emitiendo un InconsistentVersionWarning y servir predicciones distintas de las
# que el gate aprobo. Un modelo validado en CI y una imagen que sirve otra cosa.
# =============================================================================

ARG PYTHON_VERSION=3.11
# uv pinneado: la herramienta que resuelve el lock es parte del entorno
# reproducible. Un uv distinto puede rechazar el lock o resolver diferente.
ARG UV_VERSION=0.8.17

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv-bin


# =============================================================================
# Etapa 1 — builder: instala dependencias desde uv.lock
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

COPY --from=uv-bin /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PYTHON=/usr/local/bin/python3
# Fuera del arbol del proyecto: asi el venv no depende de /app y se copia solo a
# la etapa de runtime.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# --- Capa 1: solo el manifiesto y el lock -----------------------------------
# Se copian ANTES del codigo. Las dependencias cambian pocas veces y el codigo
# cambia en cada commit: con este orden, editar main.py reutiliza la capa de
# dependencias en lugar de reinstalar cientos de MB.
COPY pyproject.toml uv.lock ./

# --no-install-project: instala SOLO las dependencias.
# --locked: falla si el lock no esta sincronizado con pyproject.toml.
# --no-dev: ruff, mypy y pytest no tienen nada que hacer en runtime; son
#   superficie de ataque y peso muerto.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --no-editable

# --- Capa 2: el proyecto ----------------------------------------------------
# README.md hace falta porque pyproject.toml lo declara como `readme` y hatchling
# lo lee al construir el wheel.
COPY README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# =============================================================================
# Etapa 2 — runtime: lo minimo para servir
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# TODO(estudiante) 23: completa estas etiquetas. Sirven para saber, mirando un
# registry, que es cada imagen y de que commit salio.
LABEL org.opencontainers.image.title="miproyecto-api" \
      org.opencontainers.image.description="TODO: descripcion del servicio." \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1
# Sin buffer: los logs salen a stdout en el momento. Sin esto, `docker logs` de un
# contenedor que acaba de fallar aparece vacio y el diagnostico es adivinanza.
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"
# Default seguro: la imagen arranca sin modelo. /health responde 200 con
# modelo_cargado=false y /predict devuelve 503. Es lo que permite verificar la
# imagen en CI sin levantar el registry.
ENV MIPROYECTO_MODELO_URI=ninguno

# Usuario no-root creado ANTES de copiar, para asignar la propiedad en el COPY y
# no pagar una capa extra con `chown -R`.
#
# Por que: si un atacante logra ejecucion de codigo en el proceso, con root
# dentro del contenedor tiene muchisimo mas margen. El CI lo verifica con un paso
# que falla si el UID es 0.
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --create-home --shell /usr/sbin/nologin app \
    && install -d -o app -g app /app

WORKDIR /app

# Se copia UNICAMENTE el venv: el codigo ya esta instalado dentro
# (--no-editable), asi que la imagen final no lleva src/, ni uv, ni caches.
COPY --from=builder --chown=app:app /opt/venv /opt/venv

USER app

EXPOSE 8000

# HEALTHCHECK con Python, NO con curl.
#
# `python:*-slim` no trae curl. Un healthcheck con curl falla siempre, el
# contenedor queda permanentemente `unhealthy` y cualquier
# `depends_on: service_healthy` se cuelga para siempre. El interprete ya esta en
# la imagen y resuelve lo mismo sin agregar 10 MB.
#
# Regla general: el healthcheck solo puede usar binarios que la imagen trae de
# verdad. Verificable en un comando:
#   docker run --rm --entrypoint sh <imagen> -c 'command -v curl wget python'
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# 0.0.0.0 es correcto AQUI y solo aqui: dentro del contenedor hay que escuchar en
# todas las interfaces para que el port mapping funcione, y el aislamiento lo da
# Docker. En un proceso local, 0.0.0.0 expone el servicio a toda la red del
# equipo (por eso `make serve` usa 127.0.0.1).
#
# Forma exec (lista, sin shell): el proceso queda como PID 1 y recibe SIGTERM
# directamente, asi que uvicorn puede cerrar conexiones antes de morir. Con la
# forma shell, `sh` se traga la senal y Docker mata el contenedor a los 10s.
CMD ["uvicorn", "miproyecto.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
