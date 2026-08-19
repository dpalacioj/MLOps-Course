#!/usr/bin/env bash
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


