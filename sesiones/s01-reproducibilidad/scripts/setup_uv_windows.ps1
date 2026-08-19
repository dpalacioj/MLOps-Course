Param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "[1/6] Checking Git..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  winget install --id Git.Git -e --source winget
}

Write-Host "[2/6] Checking Python (3.11+ recommended)..."
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  winget install --id Python.Python.3.11 -e --source winget
}

Write-Host "[3/6] Installing uv if missing..."
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  irm https://astral.sh/uv/install.ps1 | iex
}

Write-Host "[4/6] Creating virtual environment (.venv)..."
uv venv

Write-Host "[5/6] Activating venv..."
. .\.venv\Scripts\Activate.ps1

Write-Host "[6/6] Syncing dependencies if pyproject exists..."
if (Test-Path -Path pyproject.toml) {
  uv sync
} else {
  Write-Host "No pyproject.toml found. You can run 'uv init' to start a project." -ForegroundColor Yellow
}

Write-Host "Done. Activate later with: .\\.venv\\Scripts\\Activate.ps1"


