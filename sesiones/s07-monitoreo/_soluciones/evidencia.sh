#!/usr/bin/env bash
# Genera la evidencia que el taller S07 pide pegar en la descripción del PR.
#
# Por qué un script y no una lista de comandos en el enunciado: la evidencia tiene que
# ser reproducible por quien revisa. Si el revisor no puede regenerarla con un comando,
# lo que está revisando es una captura de pantalla.
#
# Uso (desde la raíz del repositorio):
#   bash sesiones/s07-monitoreo/_soluciones/evidencia.sh
#
# No falla el script cuando el check falla: aquí un exit code 1 es el resultado
# esperado del criterio 2, así que se captura y se reporta en lugar de propagarse.
set -uo pipefail

PY="${PY:-uv run python}"
SEP="========================================================================"

titulo() { printf '\n%s\n%s\n%s\n' "$SEP" "$1" "$SEP"; }

titulo "0. Versiones (la evidencia caduca sin ellas)"
$PY - <<'EOF'
import importlib.metadata as md

for paquete in ("evidently", "scipy", "mlflow", "prometheus-client", "pandas", "scikit-learn"):
    try:
        print(f"{paquete:20s} {md.version(paquete)}")
    except md.PackageNotFoundError:
        print(f"{paquete:20s} NO INSTALADO")
EOF

titulo "1. Criterio 2 — el check FALLA con drift (exit code esperado: 1)"
# Se fuerza con un umbral bajo para que el criterio sea determinista en clase.
# En el proyecto real, el drift lo trae el periodo, no la bandera.
$PY -m taxi.monitoring.check_drift --actual 2023-07 --umbral 0.10 --sin-mlflow
echo "EXIT CODE: $?"

titulo "2. Criterio 3 — el check PASA sin drift (exit code esperado: 0)"
# Control negativo: la referencia contra sí misma. Si esto falla, el detector está roto
# y el criterio anterior no demuestra nada.
$PY -m taxi.monitoring.check_drift \
  --referencia 2023-01,2023-02,2023-03 \
  --actual 2023-01,2023-02,2023-03 \
  --sin-mlflow
echo "EXIT CODE: $?"

titulo "3. Criterio 5 — calibración: ruido bajo el nulo vs umbral vs señal"
$PY - <<'EOF'
import pandas as pd

from taxi import config
from taxi.features import contract as fc
from taxi.models import train
from taxi.monitoring import estadistico as est

NUM = [*fc.FEATURES_NUMERICAS, fc.TARGET_REGRESION]
CAT = list(fc.FEATURES_CATEGORICAS)

referencia = train.cargar_split(list(config.PARTICIONES_TRAIN))
ruido = est.linea_base_nula(referencia, columnas_numericas=NUM, columnas_categoricas=CAT)


def senal(particion: config.Particion) -> dict:
    actual = train.cargar_particion(particion)
    resultado = est.detectar_drift(
        referencia, actual, columnas_numericas=NUM, columnas_categoricas=CAT
    )
    return {c.columna: c.tamano_efecto for c in resultado.columnas}


tabla = pd.DataFrame(
    {
        "ruido (nulo)": pd.Series(ruido),
        "umbral": pd.Series(
            {c: est.umbral_de(c, est.TIPO_NUMERICA if c in NUM else est.TIPO_CATEGORICA) for c in ruido}
        ),
        "senal vs 2023-07": pd.Series(senal(config.Particion(2023, 7))),
        "senal vs 2024-01": pd.Series(senal(config.Particion(2024, 1))),
    }
).round(4)
tabla["umbral > ruido"] = tabla["umbral"] > tabla["ruido (nulo)"]
print(tabla.to_string())
if not tabla["umbral > ruido"].all():
    print("\nATENCION: hay umbrales por debajo del ruido -> falsos positivos garantizados")
EOF

titulo "4. Criterio 4 — el JSON trae estadístico, p-valor, efecto y umbral por columna"
$PY - <<'EOF'
import json
from pathlib import Path

from taxi.config import REPORTS_DIR

archivos = sorted(REPORTS_DIR.glob("drift_*.json"))
if not archivos:
    print("no hay JSON todavia; corre el check primero")
else:
    contenido = json.loads(archivos[-1].read_text(encoding="utf-8"))
    print("archivo:", archivos[-1].name)
    print("claves de nivel superior:", sorted(contenido))
    print(json.dumps(contenido["detalle"][0], indent=2, ensure_ascii=False))
EOF

titulo "5. Criterio 6 — /metrics expone al menos 3 métricas propias"
if curl -sf --max-time 5 localhost:8000/metrics >/dev/null 2>&1; then
  curl -s localhost:8000/metrics | grep -E '^taxi_[a-z_]+ ' -c | xargs echo "familias taxi_* expuestas:"
  curl -s localhost:8000/metrics | grep '^taxi_' | grep -v '_bucket' | head -12
else
  echo "La API no responde en localhost:8000. Levantala con:  docker compose up -d"
  echo "Exposicion en proceso, sin servidor (equivalente para la evidencia):"
  $PY - <<'EOF'
from prometheus_client import REGISTRY, generate_latest

from taxi.api import metricas

metricas.fijar_modelo("nyc-taxi-duration", "1", "models:/nyc-taxi-duration@champion")
metricas.observar_latencia(version="1", segundos=0.004)
metricas.registrar_prediccion(version="1", viaje_largo=False)
familias = {
    linea.split("{")[0].split(" ")[0]
    for linea in generate_latest(REGISTRY).decode().splitlines()
    if linea.startswith("taxi_")
}
print("familias taxi_*:", len(familias))
for nombre in sorted(familias):
    print(" ", nombre)
EOF
fi

titulo "6. Criterio 7 — el dashboard está versionado en el repositorio"
$PY - <<'EOF'
import json

from taxi.config import PROJECT_ROOT

ruta = PROJECT_ROOT / "observabilidad" / "grafana" / "dashboards" / "api-modelo.json"
dashboard = json.loads(ruta.read_text(encoding="utf-8"))
print(ruta.relative_to(PROJECT_ROOT))
print("titulo:", dashboard["title"], "| paneles:", len(dashboard["panels"]))
for panel in dashboard["panels"]:
    print(f"  [{panel['type']}] {panel['title']}")
EOF

titulo "Listo"
echo "Pega los bloques 1, 2, 3 y 5 en la descripcion del PR."
