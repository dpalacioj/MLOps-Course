#!/usr/bin/env bash
# Genera la evidencia que el taller S05 pide pegar en la descripción del PR.
#
# Por qué un script y no una lista de comandos en el enunciado: la evidencia tiene que
# ser reproducible por quien revisa. Si el revisor no puede regenerarla con un comando,
# lo que está revisando es una captura de pantalla.
#
# Uso (desde la raíz del repositorio):
#   bash sesiones/s05-deployment/_soluciones/verificar.sh
#
# Variables:
#   IMAGEN   imagen a inspeccionar          (default: mlops-curso/api:local)
#   BASE     URL de la API ya levantada     (default: http://127.0.0.1:8000)
#   DB       base SQLite del batch          (default: data/predicciones.db)
#
# No usa `set -e`: varios criterios esperan un exit code distinto de 0 (un 422, un
# grep sin resultados) y abortar en el primero dejaría la evidencia a medias.
set -uo pipefail

IMAGEN="${IMAGEN:-mlops-curso/api:local}"
BASE="${BASE:-http://127.0.0.1:8000}"
DB="${DB:-data/predicciones.db}"

SEP="========================================================================"
titulo() { printf '\n%s\n%s\n%s\n' "$SEP" "$1" "$SEP"; }
ok()     { printf '  OK    %s\n' "$1"; }
fallo()  { printf '  FALLA %s\n' "$1"; }

titulo "0. Versiones (la evidencia caduca sin ellas)"
uv run python - <<'EOF'
import importlib.metadata as md

for paquete in ("fastapi", "pydantic", "uvicorn", "mlflow", "scikit-learn", "xgboost"):
    try:
        print(f"{paquete:16s} {md.version(paquete)}")
    except md.PackageNotFoundError:
        print(f"{paquete:16s} NO INSTALADO")
EOF
docker --version || fallo "docker no está disponible"

titulo "1. Criterio 7 — cero pines a mano en el Dockerfile de la API"
# La etapa mlflow-server sí instala drivers de infraestructura con floor pins (>=);
# lo que se busca aquí son pines exactos (==) de librerías que deserializan el modelo.
if grep -nE 'pip install .*(mlflow|scikit-learn|xgboost|numpy|pandas)==' Dockerfile; then
  fallo "hay pines exactos de librerías de ML en el Dockerfile"
else
  ok "sin pines exactos de librerías de ML"
fi

titulo "2. Criterio 2 — la imagen no corre como root"
if docker image inspect "$IMAGEN" >/dev/null 2>&1; then
  uid="$(docker run --rm --entrypoint sh "$IMAGEN" -c 'id -u' 2>/dev/null || echo "?")"
  echo "  UID dentro del contenedor: $uid"
  [ "$uid" != "0" ] && [ "$uid" != "?" ] && ok "no es root" || fallo "corre como root"
else
  echo "  La imagen '$IMAGEN' no existe todavía. Constrúyela:"
  echo "      docker build -t $IMAGEN ."
fi

titulo "3. Criterio 3 — estado del healthcheck"
docker ps --filter "ancestor=$IMAGEN" --format '  {{.Names}}\t{{.Status}}' || true
echo "  (se espera '(healthy)'; '(unhealthy)' permanente suele ser el HEALTHCHECK con curl)"

titulo "4. Criterio 1 — /health responde con la versión del modelo"
salud="$(curl -fsS "$BASE/health" 2>/dev/null || true)"
if [ -n "$salud" ]; then
  echo "$salud" | (jq . 2>/dev/null || cat)
  version="$(printf '%s' "$salud" | uv run python -c 'import json,sys; print(json.load(sys.stdin).get("model_version"))' 2>/dev/null || echo None)"
  [ "$version" != "None" ] && ok "model_version = $version" \
    || fallo "model_version es null: el servicio arrancó degradado"
else
  fallo "no hubo respuesta en $BASE/health (¿está levantado el servicio?)"
fi

titulo "5. Criterio 6 — los 422 esperados (el contrato rechaza basura)"
for payload in \
  '{"PULocationID": 9999, "DOLocationID": 238, "trip_distance": 2.4}' \
  '{"PULocationId": 43, "DOLocationID": 238, "trip_distance": 2.4}' \
  '{"PULocationID": 43, "DOLocationID": 238, "trip_distance": 2.4, "pickup_datetime": "2023-05-15T08:30:00Z"}'
do
  codigo="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/predict" \
    -H 'Content-Type: application/json' -d "$payload" 2>/dev/null || echo 000)"
  [ "$codigo" = "422" ] && ok "422  $payload" || fallo "$codigo (se esperaba 422)  $payload"
done

titulo "6. Criterio 4 — tests de API sin registry y sin red"
# TAXI_MODELO_URI=ninguno es un cinturón de seguridad: si algún test construyera el
# cargador global por descuido, arrancaría degradado en lugar de colgarse en un timeout.
TAXI_MODELO_URI=ninguno uv run pytest tests/api -q
echo "EXIT CODE: $?"

titulo "7. Criterio 5 — trazabilidad del batch en SQL"
if [ -f "$DB" ]; then
  sqlite3 -header -column "$DB" \
    "SELECT model_version, model_alias, COUNT(*) AS n,
            ROUND(AVG(prediccion_minutos), 2) AS media_min
       FROM predicciones GROUP BY 1, 2 ORDER BY 1;"
else
  echo "  No existe $DB todavía. Genéralo con:  make batch"
fi

titulo "Fin"
echo "Pega esta salida completa en la descripción del PR, incluidas las FALLA."
echo "Un criterio que falla y está explicado vale más que uno que se omite."
