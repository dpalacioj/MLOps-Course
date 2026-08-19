#!/usr/bin/env bash
# =============================================================================
# post-create del devcontainer del curso
# =============================================================================
# Se ejecuta UNA vez, cuando el contenedor se crea (onCreateCommand). Su unico
# objetivo es que `make smoke` funcione dentro sin que el estudiante haga nada.
#
# Por que existe este archivo y no una lista de comandos en devcontainer.json:
# porque los comandos necesitan condicionales (git-lfs puede no tener objetos que
# traer, `data/` puede no existir) y un JSON no es sitio para logica.
#
# Se ejecuta con `set -e` PERO cada paso opcional esta protegido con `|| true`:
# un devcontainer que no arranca porque falla un paso opcional no sirve de plan B.
# =============================================================================
set -euo pipefail

echo ""
echo "=============================================================="
echo "  Preparando el entorno del curso de MLOps"
echo "=============================================================="
echo ""

# -----------------------------------------------------------------------------
# 1. uv
# -----------------------------------------------------------------------------
# La imagen base de devcontainers/python no trae uv. Se instala con el
# instalador oficial, que no necesita Python previo.
if ! command -v uv >/dev/null 2>&1; then
  echo "[1/6] Instalando uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # El instalador escribe en ~/.local/bin. Se agrega al PATH de las shells
  # futuras y al de este script.
  export PATH="$HOME/.local/bin:$PATH"
  echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.bashrc"
  if [ -f "$HOME/.zshrc" ]; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.zshrc"
  fi
else
  echo "[1/6] uv ya esta instalado."
fi
uv --version

# -----------------------------------------------------------------------------
# 2. Git LFS
# -----------------------------------------------------------------------------
# Los 12 diagramas de la sesion 4 son .png en LFS. Sin esto se ven como
# archivos de texto de tres lineas, que es uno de los fallos que este curso
# corrige. La feature de devcontainers ya instalo el binario; aqui se activa
# en el repositorio y se traen los objetos.
echo "[2/6] Git LFS..."
if command -v git-lfs >/dev/null 2>&1; then
  git lfs install --local || true
  git lfs pull || echo "  AVISO: 'git lfs pull' no pudo traer objetos (repo sin remoto?)."
else
  echo "  AVISO: git-lfs no esta disponible. Los diagramas .png no se veran."
fi

# -----------------------------------------------------------------------------
# 3. Dependencias, desde el lockfile
# -----------------------------------------------------------------------------
# --locked es deliberado: si el uv.lock estuviera desfasado respecto al
# pyproject.toml, queremos saberlo aqui y no tres sesiones despues.
echo "[3/6] Sincronizando dependencias desde uv.lock..."
uv sync --group dev --locked

# -----------------------------------------------------------------------------
# 4. Hooks de git
# -----------------------------------------------------------------------------
echo "[4/6] Instalando hooks..."
git config --local core.hooksPath .githooks || true
uv run pre-commit install --install-hooks || true
uv run pre-commit install --hook-type commit-msg || true

# -----------------------------------------------------------------------------
# 5. Directorios de trabajo
# -----------------------------------------------------------------------------
# Estan gitignorados, asi que no existen en un clon limpio. Varios modulos
# escriben ahi y fallarian con FileNotFoundError.
echo "[5/6] Creando directorios de trabajo..."
mkdir -p data/raw data/processed reports mlruns

# -----------------------------------------------------------------------------
# 6. Kernel de Jupyter
# -----------------------------------------------------------------------------
# Sin esto, los notebooks del curso abren con un kernel que no ve las
# dependencias del proyecto, que es el error mas frecuente con notebooks.
echo "[6/6] Registrando el kernel de Jupyter..."
uv run python -m ipykernel install --user \
  --name mlops-curso \
  --display-name "Python 3.11 (curso MLOps)" >/dev/null 2>&1 ||
  echo "  AVISO: no se pudo registrar el kernel; selecciona el interprete a mano."

echo ""
echo "=============================================================="
echo "  Listo. Siguiente paso:"
echo ""
echo "      make smoke"
echo ""
echo "  Los datos NO se descargan aqui (son ~200 MB y tardan)."
echo "  Cuando los necesites:  make data"
echo ""
echo "  Material de hoy: sesiones/s01-reproducibilidad/README.md"
echo "=============================================================="
echo ""
