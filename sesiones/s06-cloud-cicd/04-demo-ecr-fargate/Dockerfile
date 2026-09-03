# syntax=docker/dockerfile:1
# ^ Directiva del parser. Tiene que ser la PRIMERA linea del archivo.
#
# =============================================================================
# Imagen de la demo de nube (S06): la imagen de la API de S05 mas UNA capa
# =============================================================================
# Que problema resuelve. En la nube de esta demo no hay ningun MLflow al que el
# contenedor pueda pedirle el modelo por alias: montar un registry accesible
# desde la nube (base de datos + bucket + red privada) cuesta mas que toda la
# demo junta. Asi que el modelo VIAJA DENTRO DE LA IMAGEN.
#
# Eso NO contradice la sesion 5. Lo que la sesion 5 rechaza es copiar a mano el
# directorio de un run concreto (`shutil.copytree`, un `run_id` fijo, sin saber
# que version es). Aqui el modelo se exporta del registry POR ALIAS con
# `mlflow artifacts download`, y la version que ese alias resolvia queda
# escrita como etiqueta de la imagen (ver LABEL). El precio del patron esta
# dicho en el README de esta carpeta, seccion "Dos formas de llevar el modelo":
# cambiar de modelo exige reconstruir y redesplegar la imagen.
#
# Como se usa (desde la raiz del repositorio; el README de esta carpeta lo
# recorre paso a paso):
#
#   docker build -t mlops-curso/api:local .
#   MLFLOW_TRACKING_URI=http://127.0.0.1:5001 uv run mlflow artifacts download \
#       --artifact-uri "models:/nyc-taxi-duration@champion" \
#       --dst-path sesiones/s06-cloud-cicd/04-demo-ecr-fargate/modelo-exportado
#   docker build -t mlops-curso/api-con-modelo:local \
#       --build-arg MODELO_VERSION=<version que resolvia @champion> \
#       sesiones/s06-cloud-cicd/04-demo-ecr-fargate
#
# `modelo-exportado/` esta en .gitignore: es un artefacto, se regenera desde el
# registry, y no se versiona nunca.
# =============================================================================

# La base es la imagen que construye el Dockerfile de la raiz. Se pasa como ARG
# para poder apuntar a la que ya esta en ECR sin reconstruirla.
ARG BASE=mlops-curso/api:local
FROM ${BASE}

# Se declara DESPUES del FROM: un ARG declarado antes del FROM solo existe para
# el propio FROM, y aqui hace falta para el LABEL.
ARG MODELO_NOMBRE=nyc-taxi-duration
ARG MODELO_VERSION=desconocida

# La unica capa nueva. --chown porque la imagen base corre como el usuario
# `taxi` (UID 1001) y `/app` le pertenece; sin el chown los archivos quedarian
# de root y mlflow no podria leerlos ni escribir a su lado.
COPY --chown=taxi:taxi modelo-exportado /app/modelo

# Una ruta local en lugar de `models:/...@champion`. La API la acepta y avisa en
# el log de que una ruta no es auditable: `/modelo` va a responder
# version=desconocida. Es el costo del patron hecho visible, no un bug.
ENV TAXI_MODELO_URI=/app/modelo

# Lo que la API no puede saber lo sabe la imagen: que modelo y que version
# lleva dentro. `docker inspect` lo muestra sin arrancar el contenedor.
LABEL mlops-curso.modelo.nombre="${MODELO_NOMBRE}" \
      mlops-curso.modelo.version="${MODELO_VERSION}" \
      mlops-curso.modelo.origen="mlflow artifacts download models:/${MODELO_NOMBRE}@champion"
