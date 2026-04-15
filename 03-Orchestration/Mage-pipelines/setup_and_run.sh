#!/bin/bash
# =============================================================================
# Setup y ejecucion del pipeline Mage - NYC Taxi Duration Prediction
#
# Mage requiere un entorno virtual separado porque sus dependencias
# (SQLAlchemy 1.4, etc.) entran en conflicto con Prefect y MLflow modernos.
# Usamos uv para mantener consistencia con el resto del repositorio.
#
# Uso:
#   chmod +x setup_and_run.sh
#   ./setup_and_run.sh          # Setup + abrir UI
#   ./setup_and_run.sh --run    # Setup + ejecutar pipeline sin UI
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/nyc_taxi_project"

echo "============================================"
echo "  Mage Pipeline - NYC Taxi Duration"
echo "============================================"

# --- Paso 1: Verificar que uv esta disponible ---
if ! command -v uv &> /dev/null; then
    echo "ERROR: uv no esta instalado. Instala con: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# --- Paso 2: Crear entorno virtual con uv ---
echo ""
echo "[1/3] Creando entorno virtual con uv..."
cd "$SCRIPT_DIR"
uv venv --quiet .venv-mage 2>/dev/null || true
echo "      Entorno .venv-mage listo."

# --- Paso 3: Instalar dependencias con uv ---
echo ""
echo "[2/3] Instalando dependencias con uv..."
VIRTUAL_ENV="$SCRIPT_DIR/.venv-mage" uv pip install --quiet -r pyproject.toml
echo "      Dependencias instaladas."

# --- Paso 4: Ejecutar ---
echo ""
echo "[3/3] Iniciando Mage..."

# Activar el entorno
source "$SCRIPT_DIR/.venv-mage/bin/activate"

# Desactivar autenticacion (Mage 0.9.71+ la activa por defecto).
# Mage solo acepta "false"/"False" — el valor "0" NO funciona.
export REQUIRE_USER_AUTHENTICATION=false

if [ "$1" == "--run" ]; then
    echo "      Ejecutando pipeline sin UI..."
    cd "$PROJECT_DIR"
    python -c "
import mage_ai
mage_ai.run(
    'nyc_taxi_training',
    project_path='$PROJECT_DIR'
)
print('Pipeline ejecutado exitosamente!')
"
else
    echo ""
    echo "      Abriendo Mage UI en http://localhost:6789"
    echo "      Pipeline: nyc_taxi_training"
    echo ""
    echo "      NOTA: Mage pedira crear una cuenta la primera vez."
    echo "      Es local (no se envia a ningun servidor)."
    echo "      Usa cualquier email/password, por ejemplo:"
    echo "        Email:    admin@admin.com"
    echo "        Password: admin123"
    echo ""
    echo "      Presiona Ctrl+C para detener"
    echo ""
    cd "$PROJECT_DIR"
    REQUIRE_USER_AUTHENTICATION=false mage start "$PROJECT_DIR"
fi
