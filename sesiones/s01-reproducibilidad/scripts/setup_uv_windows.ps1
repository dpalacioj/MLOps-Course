# =============================================================================
# Setup guiado del entorno del curso con uv — Windows / PowerShell
# =============================================================================
#
#   ANTES DE EJECUTAR ESTE ARCHIVO, LEE ESTO.
#
#   Windows viene con la ExecutionPolicy en 'Restricted' por defecto, y eso
#   bloquea TODO script .ps1, incluido este y el propio Activate.ps1. Si lo
#   ejecutas tal cual, obtienes:
#
#       ... no se puede cargar el archivo ... porque la ejecucion de scripts
#       esta deshabilitada en este sistema.
#           + FullyQualifiedErrorId : UnauthorizedAccess
#
#   Solucion, UNA sola vez por usuario (no requiere administrador):
#
#       Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#
#   Alternativa sin cambiar la politica, para una sola ejecucion:
#
#       powershell -ExecutionPolicy Bypass -File .\setup_uv_windows.ps1
#
#   Detalle y variantes: sesiones/s01-reproducibilidad/troubleshooting-so.md, §2.
#
# -----------------------------------------------------------------------------
#   Uso, desde la RAIZ del repositorio del curso:
#
#       .\sesiones\s01-reproducibilidad\scripts\setup_uv_windows.ps1
#
#   Este script es el plan B del setup manual. Si algo falla y llevas mas de
#   10 minutos, usa el devcontainer (.devcontainer/) y sigue la clase.
# =============================================================================

Param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "[0/7] Comprobando la ExecutionPolicy..."
$politica = Get-ExecutionPolicy -Scope CurrentUser
if ($politica -eq 'Restricted' -or $politica -eq 'Undefined') {
  $efectiva = Get-ExecutionPolicy
  if ($efectiva -eq 'Restricted') {
    Write-Host "  La ExecutionPolicy efectiva es 'Restricted'." -ForegroundColor Yellow
    Write-Host "  Ejecuta esto y vuelve a lanzar el script:" -ForegroundColor Yellow
    Write-Host "    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned" -ForegroundColor Yellow
    Write-Host "  (Si tu equipo lo gestiona la universidad, puede haber una politica de" -ForegroundColor Yellow
    Write-Host "   grupo que lo impida. En ese caso usa el devcontainer.)" -ForegroundColor Yellow
    exit 1
  }
}
Write-Host "  OK ($politica en CurrentUser)."

Write-Host "[1/7] Comprobando Git..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  winget install --id Git.Git -e --source winget
  Write-Host "  Git instalado. CIERRA y vuelve a abrir PowerShell para que el PATH se actualice." -ForegroundColor Yellow
  exit 1
}

Write-Host "[2/7] Comprobando Git LFS..."
if (-not (Get-Command git-lfs -ErrorAction SilentlyContinue)) {
  # LFS va aqui y no al final a proposito: los diagramas del curso son binarios
  # en LFS, y clonar sin LFS deja punteros de texto de 130 bytes en su lugar.
  winget install --id GitHub.GitLFS -e --source winget
}
git lfs install

Write-Host "[3/7] Comprobando uv..."
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  Write-Host "  uv instalado. CIERRA y vuelve a abrir PowerShell, y relanza el script." -ForegroundColor Yellow
  exit 1
}
uv --version

Write-Host "[4/7] Instalando Python 3.11 con uv..."
# Con uv, no con pyenv-win: pyenv-win exige descargar un .ps1 de GitHub,
# ejecutarlo contra la ExecutionPolicy, editar el PATH y reiniciar la terminal.
# Son cuatro puntos de fallo antes de tener un interprete.
uv python install 3.11

Write-Host "[5/7] Trayendo los binarios de Git LFS..."
if (Test-Path -Path .git) {
  git lfs pull
} else {
  Write-Host "  No estas en un repositorio git. Clona tu fork primero." -ForegroundColor Yellow
}

Write-Host "[6/7] Sincronizando dependencias desde el lockfile..."
if (Test-Path -Path pyproject.toml) {
  uv sync --group dev
  uv run pre-commit install --install-hooks
  uv run pre-commit install --hook-type commit-msg
} else {
  Write-Host "  No hay pyproject.toml aqui. Ejecuta el script desde la raiz del repositorio." -ForegroundColor Yellow
  exit 1
}

Write-Host "[7/7] Smoke test del entorno..."
uv run python scripts/smoke_test.py

Write-Host ""
Write-Host "Listo." -ForegroundColor Green
Write-Host "No necesitas activar nada: usa 'uv run <comando>'."
Write-Host "Si aun asi quieres activar el entorno, el comando es (ojo al punto inicial):"
Write-Host "    .\.venv\Scripts\Activate.ps1"
