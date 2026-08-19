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

echo "[3/5] Installing Poetry if missing..."
if ! command -v poetry >/dev/null 2>&1; then
  curl -sSL https://install.python-poetry.org | python3 -
  exec "$SHELL"
fi

echo "[4/5] Creating env and installing dependencies (if pyproject exists)..."
if [ -f "pyproject.toml" ]; then
  poetry env use python
  poetry install --no-root
else
  echo "No pyproject.toml found. You can run 'poetry init' to start a project."
fi

echo "[5/5] Verify"
poetry --version
poetry run python -V

echo "Done. Use 'poetry shell' or prefix commands with 'poetry run'."


