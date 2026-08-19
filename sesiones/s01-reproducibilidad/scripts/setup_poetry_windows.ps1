Param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

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


