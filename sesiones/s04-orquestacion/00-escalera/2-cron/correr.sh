#!/usr/bin/env bash
# =============================================================================
# Peldano 2 de la escalera — el envoltorio que cron necesita de verdad.
# =============================================================================
# Este archivo existe por una razon que sorprende a casi todo el mundo la primera
# vez: `cron` NO ejecuta el comando en el mismo entorno que tu terminal. No lee
# tu ~/.bashrc ni tu ~/.zshrc, arranca con un PATH minimo, y el directorio de
# trabajo es tu HOME, no el del proyecto.
#
# Poner `uv run python 1-script.py` directo en el crontab falla con
# "uv: command not found" o con un error de proyecto no encontrado. Las tres
# lineas que lo arreglan son las tres primeras del bloque de abajo, y son el
# contenido del peldano: el script no cambio, cambio todo lo que hay alrededor
# para poder ejecutarlo sin nadie delante.
#
# Uso manual (para probarlo antes de meterlo al crontab):
#
#     ./correr.sh
#     tail -20 "$HOME/escalera-cron.log"
# =============================================================================

# `set -euo pipefail`: cortar en el primer error, tratar variables no definidas
# como error, y no dejar que un fallo a mitad de un pipe pase inadvertido. En un
# script que corre a las 3 a.m. sin nadie mirando, esto no es opcional.
set -euo pipefail

# 1. Resolver rutas a partir de la ubicacion de ESTE archivo, no del directorio
#    de trabajo. Asi funciona igual desde el crontab, desde tu terminal o desde
#    cualquier otra carpeta.
CARPETA_ESCALERA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAIZ_REPO="$(cd "$CARPETA_ESCALERA/../../.." && pwd)"

# 2. Asegurar el PATH. `uv` suele quedar en uno de estos tres sitios; cron no
#    conoce ninguno. Si `uv` esta en otro lugar, agregalo aqui: la salida de
#    `command -v uv` en tu terminal te dice donde.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# 3. Ejecutar desde la raiz del repositorio, que es donde `uv run` encuentra el
#    pyproject.toml y el entorno virtual del curso.
cd "$RAIZ_REPO"

# El log. Cron manda stdout y stderr al correo local del usuario, que en una
# maquina de desarrollo nadie lee y en muchas ni existe. Sin esta redireccion,
# la corrida de las 3 a.m. es invisible: no hay forma de saber si paso.
LOG="${ESCALERA_LOG:-$HOME/escalera-cron.log}"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
  if uv run python "$CARPETA_ESCALERA/1-script.py"; then
    echo "estado: OK"
  else
    codigo=$?
    echo "estado: FALLO (codigo $codigo)"
    # Aqui es donde, en un sistema de verdad, tendrias que escribir a mano lo
    # que el orquestador ya trae: reintentar, avisar a alguien, y no volver a
    # avisar cien veces por el mismo fallo. Ver la tabla del README.
    exit "$codigo"
  fi
} >>"$LOG" 2>&1
