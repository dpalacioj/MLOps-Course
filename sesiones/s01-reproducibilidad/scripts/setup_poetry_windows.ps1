# =============================================================================
# Setup guiado con Poetry — Windows / PowerShell
# =============================================================================
#
#   ANTES DE EJECUTAR ESTE ARCHIVO: la ExecutionPolicy por defecto de Windows es
#   'Restricted' y bloquea TODO script .ps1. Ejecuta una sola vez, sin necesidad
#   de administrador:
#
#       Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#
#   O bien, para una sola ejecucion y sin cambiar nada:
#
#       powershell -ExecutionPolicy Bypass -File .\setup_poetry_windows.ps1
#
#   Detalle: sesiones/s01-reproducibilidad/troubleshooting-so.md, §2.
#
#   Nota: el curso usa uv. Poetry 2.x sigue vivo y mantenido, y es una
#   alternativa perfectamente valida; este script existe para quien ya lo tiene
#   en su flujo. No uses las dos herramientas en el mismo proyecto: dos
#   lockfiles describiendo el mismo entorno es peor que ninguno.
# =============================================================================

Param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "[0/5] Comprobando la ExecutionPolicy..."
if ((Get-ExecutionPolicy) -eq 'Restricted') {
  Write-Host "  ExecutionPolicy 'Restricted'. Ejecuta y reintenta:" -ForegroundColor Yellow
  Write-Host "    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned" -ForegroundColor Yellow
  exit 1
}

Write-Host "[1/5] Checking Git..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  winget install --id Git.Git -e --source winget
}

Write-Host "[2/5] Checking Python (3.11+ recommended)..."
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  winget install --id Python.Python.3.11 -e --source winget
}

Write-Host "[3/5] Installing Poetry if missing..."
if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
  (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
}

Write-Host "[4/5] Creating env and installing dependencies (if pyproject exists)..."
if (Test-Path -Path pyproject.toml) {
  poetry env use python
  poetry install --no-root --no-interaction --no-ansi
} else {
  Write-Host "No pyproject.toml found. You can run 'poetry init' to start a project." -ForegroundColor Yellow
}

Write-Host "[5/5] Verify"
poetry --version
poetry run python -V

Write-Host "Done. Use 'poetry shell' or prefix commands with 'poetry run'."


