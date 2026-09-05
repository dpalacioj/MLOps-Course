# syntax=docker/dockerfile:1
# Imagen del pipeline de bicis, en una sola etapa. Cinco decisiones:
#   1. imagen base "slim" y con version fija (nunca `python:latest`)
#   2. dependencias antes que codigo, para aprovechar la cache de capas
#   3. instalacion desde el LOCKFILE, no desde versiones escritas a mano
#   4. usuario sin privilegios, con un HOME escribible
#   5. un proceso que termina solo: es un job, no un servidor (por eso no hay HEALTHCHECK)

FROM python:3.11-slim-bookworm

# El binario de uv se copia de su imagen oficial, con version fija, en vez de
# instalarlo con pip: la imagen no arrastra pip ni caches de descarga.
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv

# El entorno virtual fuera del arbol del proyecto y con el interprete de la imagen.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PYTHON=/usr/local/bin/python3
ENV UV_LINK_MODE=copy
# Los logs salen a stdout en el momento: sin esto, `docker logs` de un contenedor
# que acaba de fallar sale vacio.
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Capa 1: solo manifiesto y lock. Cambian poco; el codigo cambia en cada edicion.
# `--locked` falla si uv.lock no esta al dia con pyproject.toml, en vez de
# re-resolver en silencio.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# Capa 2: el codigo.
COPY pipeline_bicis.py ./

# Usuario sin privilegios. `--create-home` importa: Prefect guarda su configuracion,
# la base de datos del servidor efimero y los resultados cacheados en ~/.prefect, y
# un usuario sin HOME escribible no puede crear ese directorio.
RUN groupadd --system --gid 1001 bicis \
    && useradd --system --uid 1001 --gid bicis --create-home bicis \
    && chown -R bicis:bicis /app
USER bicis

# Forma exec (lista, sin shell): el proceso es PID 1 y recibe las senales directo.
CMD ["python", "pipeline_bicis.py"]
