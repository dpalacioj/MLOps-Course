# Taller S05 — Servir tu modelo: API contenedorizada y batch trazable

**Duración:** 55 min en clase. **Se entrega en clase.**
**Sobre:** tu propio repositorio de proyecto (no el del curso).
**Entregable:** un PR con el servicio, la imagen, los tests y el ADR.

---

## Contexto

Tu modelo ya está en el registry con un alias (S03) y tu entrenamiento ya corre
orquestado (S04). Hoy dejas de ser el único que puede usarlo.

El objetivo **no** es "hacer una API": es que otro sistema pueda consumir tu modelo
y que, ante una predicción concreta, puedas decir qué artefacto la produjo.

Puedes usar la API del curso como plantilla, pero **el modelo tiene que ser el
tuyo**, cargado desde tu registry por alias.

---

## 1. Decide la forma de servicio y déjalo escrito

Antes de escribir código, un párrafo en el PR: **batch, online o streaming**, y por
qué, usando los cinco criterios de la
[matriz de decisión](README.md#2-batch-online-o-streaming-la-decisión-antes-de-la-herramienta):
latencia tolerada, volumen, frescura de features, costo, complejidad operativa.

Si tu consumidor puede esperar al próximo corte, **elegir batch es la respuesta
correcta** y no una salida fácil. Lo que no se acepta es "hice una API porque es lo
que vimos hoy".

Entregas las **dos** formas de todos modos (sección 2 y sección 4), porque el criterio se aprende
comparando. Lo que el párrafo decide es cuál es la principal de tu proyecto.

## 2. El servicio online

- FastAPI con **Pydantic v2**: `model_config = ConfigDict(...)`, `@field_validator`.
  Nada de `class Config` ni `@validator`.
- **Request y response separados.** La respuesta incluye, como mínimo, la predicción
  más `model_name` y `model_version`.
- `extra="forbid"` en los requests, y **rangos que coincidan con tu contrato de
  datos de S02**. Si tu modelo nunca vio un valor, la API no debe aceptarlo.
- Ciclo de vida con **`lifespan`**, y el modelo se carga ahí, no en el primer
  request.
- El modelo se resuelve **del registry por alias** (`models:/<tu-modelo>@champion`).
  Si en tu repo hay un paso que copia el modelo a una carpeta, este es el momento de
  borrarlo y de decir en el commit por qué.
- Endpoints mínimos: `/predict`, `/predict/batch`, `/health` (con la versión del
  modelo), `/metrics`.
- **Ningún error devuelve el texto de la excepción.** Mensaje estable al cliente,
  `id_correlacion`, traza al log.

## 3. La imagen

- Base slim con versión fija.
- Dependencias con **`uv sync --locked`** desde tu lockfile. **Cero** `pip install
  paquete==version` en el `Dockerfile`.
- `.dockerignore` que excluya al menos: entornos virtuales, datos, artefactos,
  `.git` y secretos.
- Usuario **no-root**.
- `HEALTHCHECK` que funcione **en tu imagen** (si la base no trae `curl`, usa el
  intérprete).
- `docker-compose.yml` **sin** la clave `version:`.

## 4. El batch, con trazabilidad

Un job que predice sobre un lote y persiste **una fila por predicción** con, como
mínimo: `batch_id`, `prediction_timestamp`, `model_name`, `model_version`,
`model_alias` y las features de entrada.

Prohibido: `iterrows()` en el bucle de predicción (predice sobre el DataFrame
completo) y escribir un literal como `'stage': 'Production'` en la fila.

## 5. Tests de la API (≥4)

Tienen que correr **sin registry y sin red**: sustituye el modelo por un doble de
prueba. Mira [`tests/api/conftest.py`](../../tests/api/conftest.py) para la costura.

Los cuatro que se piden como mínimo:

1. una predicción válida devuelve 200 **con `model_version`**;
2. una entrada inválida devuelve 422;
3. sin modelo cargado, `/predict` devuelve 503 y `/health` devuelve 200;
4. un fallo de inferencia devuelve 500 **sin filtrar el mensaje de la excepción**.

## 6. ADR: `docs/adr/00X-forma-de-servicio.md`

Una página:

1. **Contexto** — quién consume tu modelo, con qué latencia y volumen.
2. **Decisión** — batch, online o streaming, con los cinco criterios.
3. **Alternativas descartadas** — al menos dos, con el motivo.
4. **Consecuencias** — qué te costaría equivocarte en los dos sentidos: qué pasa si
   montas un servicio online que nadie necesitaba (disponibilidad que hay que
   sostener, p95 que vigilar, costo fijo) y qué pasa si te quedas en batch cuando el
   consumidor necesitaba tiempo real.

---

## Criterios de aceptación

Se verifican **ejecutando**, no leyendo. Si un criterio no se puede comprobar con un
comando, no cuenta.

| # | Criterio | Cómo se verifica |
|---|---|---|
| 1 | `docker compose up` levanta la API y `/health` responde con la versión del modelo | `curl -s localhost:PUERTO/health \| jq .model_version` devuelve un valor, no `null` |
| 2 | La imagen **no corre como root** | `docker run --rm --entrypoint sh TU_IMAGEN -c 'id -u'` imprime algo distinto de `0` |
| 3 | El `HEALTHCHECK` funciona | `docker ps` muestra `(healthy)`, no `(unhealthy)` ni `(health: starting)` indefinidamente |
| 4 | **≥4 tests de API pasan**, sin registry ni red | `uv run pytest tests/ -k api` en verde, con el servicio de MLflow **apagado** |
| 5 | Una consulta SQL muestra predicciones con su versión de modelo | `SELECT model_version, COUNT(*) FROM <tu_tabla> GROUP BY 1;` devuelve ≥1 fila |
| 6 | Ningún error de la API filtra internals | el test 4 de sección 5 lo demuestra: el cuerpo del 500 no contiene el texto de la excepción |
| 7 | Cero pines a mano en el `Dockerfile` | `grep -nE "pip install .*==" Dockerfile` no devuelve nada |
| 8 | El CI del repo del curso sigue verde | el PR de tu proyecto no aplica aquí, pero tu propio CI debe estar en verde |

El criterio 2 **ya está automatizado en este repositorio**: mira el job `imagen` de
[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), que construye la imagen
y falla si el UID es 0. Cópialo a tu proyecto: un criterio verificado por una persona
se deja de verificar en la tercera semana.

---

## Verificación rápida antes de entregar

```bash
# 1. La imagen y el usuario
docker compose up -d --build
docker compose ps                       # STATUS debe decir (healthy)
docker compose exec api id -u           # != 0

# 2. El contrato
curl -s localhost:8000/health | jq
curl -sX POST localhost:8000/predict -H 'Content-Type: application/json' \
  -d '{...tu payload...}' | jq '.model_version'

# 3. Los 422 esperados (manda basura a propósito)
curl -sX POST localhost:8000/predict -H 'Content-Type: application/json' \
  -d '{"campo_que_no_existe": 1}' -o /dev/null -w '%{http_code}\n'   # 422

# 4. Tests sin infraestructura
docker compose stop mlflow 2>/dev/null || true
uv run pytest -k api -q

# 5. Trazabilidad del batch
sqlite3 -header -column <tu.db> "SELECT model_version, COUNT(*) FROM <tabla> GROUP BY 1;"

# 6. Nada de pines a mano
grep -nE "pip install .*==" Dockerfile || echo "sin pines a mano  OK"
```

Con Postman: importa [`postman/`](postman/) y usa *Run collection* — cada request
lleva sus tests, así que el resultado es una verificación del contrato completo.

---

## Errores frecuentes (en el orden en que aparecen)

| Síntoma | Causa casi siempre |
|---|---|
| `422` en todos los requests del lote | la clave del lote cambió a `viajes`; estás mandando `trips` |
| `/health` devuelve `model_loaded: false` con una URI válida | el registry no está arriba, o `MLFLOW_TRACKING_URI` apunta al puerto equivocado (el curso usa **5001**) |
| El contenedor queda `unhealthy` para siempre | el `HEALTHCHECK` usa `curl` y la base es `python:*-slim`, que no lo trae |
| `docker logs` sale vacío tras un fallo | falta `ENV PYTHONUNBUFFERED=1` |
| El build tarda lo mismo tras cambiar una línea de código | el `COPY` del código está **antes** de la instalación de dependencias |
| `InconsistentVersionWarning` al cargar el modelo | hay dos resoluciones de dependencias: el lockfile y unos pines a mano |
| Los tests fallan solo en CI | dependen del registry o de la red; hay que inyectar el doble de prueba |

---

## Rúbrica

| Peso | Aspecto |
|---|---|
| 25% | El servicio: contrato con Pydantic v2, carga por alias, endpoints operativos |
| 20% | La imagen: lockfile, no-root, healthcheck real, `.dockerignore` |
| 20% | Trazabilidad: `model_version` en la respuesta **y** en la fila del batch |
| 15% | Tests: ≥4, sin infraestructura, incluido el que verifica que no se filtran internals |
| 10% | El ADR: los cinco criterios y las consecuencias en los dos sentidos |
| 10% | Manejo de errores: nada de `str(e)` al cliente, `id_correlacion` en los logs |

Descuentos: usar `app.run(debug=True)`, `@app.on_event`, `pickle.load` de un
artefacto sin linaje, copiar el modelo a la imagen, o `imagen:latest` como
referencia de despliegue.
