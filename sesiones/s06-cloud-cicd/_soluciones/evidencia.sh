#!/usr/bin/env bash
# Genera la evidencia que el taller S06 pide pegar en la descripción del PR.
#
# Por qué un script y no una lista de comandos en el enunciado: la evidencia tiene que
# ser reproducible por quien revisa. Si el revisor no puede regenerarla con un comando,
# lo que está revisando es una captura de pantalla.
#
# Uso (desde la raíz del repositorio, con MLflow arriba y un @champion existente):
#   bash sesiones/s06-cloud-cicd/_soluciones/evidencia.sh
#
# `set -e` NO se usa: aquí un exit code 1 es el RESULTADO ESPERADO del criterio 1, y
# abortar en el primer "fallo" dejaría la evidencia a medias.
set -uo pipefail

PY="${PY:-uv run}"
MODELO="${MODELO:-nyc-taxi-duration}"
SEP="========================================================================"

titulo() { printf '\n%s\n%s\n%s\n' "$SEP" "$1" "$SEP"; }

champion() {
  $PY python - <<'EOF' 2>/dev/null || echo "  (no se pudo consultar el registry)"
from taxi.models import registry

mv = registry.version_por_alias("nyc-taxi-duration", "champion")
print(f"  @champion -> version {mv.version if mv else 'ninguna'}")
EOF
}

titulo "0. Versiones y estado inicial"
$PY python - <<'EOF'
import importlib.metadata as md

for paquete in ("mlflow", "scikit-learn", "xgboost", "pandera"):
    try:
        print(f"{paquete:16s} {md.version(paquete)}")
    except md.PackageNotFoundError:
        print(f"{paquete:16s} NO INSTALADO")
EOF
champion

titulo "1. Criterio 2 — el gate ACEPTA un candidato mejor (exit esperado: 0)"
# Se entrena con HPO y pocos trials para que quepa en el tiempo de clase. El candidato
# queda registrado como @candidate con validation_status=pending.
$PY taxi train --hpo --trials 10
$PY taxi promote
echo "EXIT CODE: $?"
champion

titulo "2. Criterio 1 — el gate RECHAZA un candidato peor (exit esperado: 1)"
# El baseline de la media es, por construcción, peor que cualquier modelo que haya
# llegado a @champion. Es el rechazo más limpio de demostrar, y el rechazo es REAL:
# no se toca ningún umbral para forzarlo.
$PY taxi train --modelo media --registrar
$PY taxi promote
echo "EXIT CODE: $?"

titulo "3. El champion NO se movió tras el rechazo"
# Esta es la mitad del criterio 1 que se olvida: no basta con el exit 1, hay que
# demostrar que el modelo que estaba sirviendo sigue ahí.
champion

titulo "4. Criterio 4 — no pudo medir (exit esperado: 2)"
echo "Apagando MLflow..."
docker compose stop mlflow >/dev/null 2>&1 || echo "  (no había un MLflow en Compose)"
$PY taxi promote
echo "EXIT CODE: $?"
echo "Volviendo a levantar MLflow..."
docker compose start mlflow >/dev/null 2>&1 || true

titulo "5. Criterio 5 — tests de la política, sin infraestructura"
$PY pytest tests/unit/test_gate.py -q
echo "EXIT CODE: $?"

titulo "6. Criterio 7 — el CD no usa 'latest' como referencia de despliegue"
if grep -n "latest" .github/workflows/cd.yml; then
  echo "  REVISAR: ¿alguna de esas líneas es una referencia de despliegue?"
else
  echo "  OK: sin 'latest' en cd.yml"
fi

titulo "7. Los cinco criterios del gate, con --dry-run (para pegar la tabla)"
# --dry-run evalúa e informa sin escribir el tag ni mover el alias: es la forma segura
# de generar la tabla de criterios para el PR.
$PY taxi promote --dry-run
echo "EXIT CODE: $?"

titulo "Fin"
cat <<'TEXTO'
Pega esta salida completa en la descripción del PR, y además los DOS enlaces a las
corridas de GitHub Actions:

  - Gate ACEPTA (exit 0): <enlace>
  - Gate RECHAZA (exit 1): <enlace>

El enlace del rechazo es el que demuestra que el gate existe. Un gate que solo se ha
visto aprobar es indistinguible de un `echo "todo bien"`.
TEXTO
