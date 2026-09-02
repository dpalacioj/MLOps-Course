#!/usr/bin/env bash
# =============================================================================
# Setup guiado del entorno del curso con uv — macOS / Linux
# =============================================================================
#
#   Uso, desde la RAIZ del repositorio:
#       chmod +x sesiones/s01-reproducibilidad/scripts/setup_uv_mac.sh
#       ./sesiones/s01-reproducibilidad/scripts/setup_uv_mac.sh
#
#   ESTO NO FUNCIONA EN WINDOWS. `chmod` es un comando POSIX que no existe en
#   PowerShell ni en Cmd, y el bit de ejecucion no es un concepto de NTFS:
#   Windows decide que es ejecutable por la extension (.exe, .bat, .ps1), no por
#   un permiso. En Windows usa setup_uv_windows.ps1, o bien Git Bash / WSL 2 de
#   forma explicita. Ver troubleshooting-so.md, §4.
# =============================================================================
set -euo pipefail

echo "[1/5] Checking Git..."
if ! command -v git >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew install git
  else
    xcode-select --install || true
  fi
fi

echo "[2/5] Checking Python (3.11+ recommended)..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "Installing Python via Homebrew..."
  brew install python@3.11
fi

echo "[3/5] Installing uv if missing..."
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  exec "$SHELL"
fi

echo "[4/5] Creating virtual environment (.venv)..."
uv venv

echo "[5/5] Activating and syncing dependencies (if pyproject exists)..."
source .venv/bin/activate
if [ -f "pyproject.toml" ]; then
  uv sync || true
else
  echo "No pyproject.toml found. You can run 'uv init' to start a project."
fi

echo "Done. Activate later with: source .venv/bin/activate"
