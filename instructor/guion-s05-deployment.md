# Guion de clase — Sesión 5: Deployment

Para seguir **al pie de la letra**: cada bloque abre con su **caja de comandos**, numerados,
con la terminal y la salida esperada. Debajo va lo que se dice. Primero se ejecuta la caja,
después se habla.

**Duración total:** 240 min (4 h), con pausa de 15 min.

**Tres terminales desde el minuto 0, siempre las mismas, todas en la raíz del repositorio:**

| Terminal | Para qué | Qué corre ahí |
|---|---|---|
| **T1** | el stack | `make up`, `make logs`, `docker compose ...` |
| **T2** | lo que se construye y despliega | `docker build`, `docker run`, `make batch` |
| **T3** | el cliente | `curl`, `jq`, `sqlite3`, `uv run python -c` |

**Un solo registry en toda la clase: el del stack de Compose (`make up`).** `make mlflow` no
se usa en clase; está en el anexo al final por si Docker falla.

**El único bloque que cambia de directorio es el 3** (`intro-dockers`). El guion dice cuándo
entrar y cuándo volver.

| Tramo | Min | Bloques |
|---|---|---|
| Arranque | 0-15 | 1 |
| El dolor | 15-40 | 2 |
| Bloque A — empaquetar | 40-95 | 3, 4, 5, 6 |
| Pausa | 95-110 | — |
| Bloque B — servir | 110-165 | 7, 8, 9, 10, 11 |
| Taller | 165-220 | 12 |
| Cierre | 220-240 | 13 |

**Pizarra:** [`pizarra-s05-deployment.html`](pizarra-s05-deployment.html).
**Material del estudiante:** [`sesiones/s05-deployment/`](../sesiones/s05-deployment/).

---

## BLOQUE 0 — Antes de clase

```bash
# T1 — el stack arriba y con un @champion en SU registry
make up
docker compose ps                       # seis servicios Up ... (healthy); grafana tarda unos segundos más

# T3 — ¿hay champion en el registry del stack?
uv run python -c "
from taxi.models import registry
mv = registry.version_por_alias('nyc-taxi-duration', 'champion')
print('champion ->', mv.version if mv else 'NO HAY')
"
# Si dice NO HAY (la primera vez siempre):
uv run taxi train --registrar && uv run taxi promote      # ~20 s
docker compose restart api && sleep 10
curl -s http://127.0.0.1:8000/health | jq .model_version   # debe ser != null

# T3 — herramientas de los bloques 9 y 10
command -v jq sqlite3

# T2 — imágenes base en cache, para que el build en vivo no espere la red
docker pull python:3.11-slim-bookworm
docker pull ghcr.io/astral-sh/uv:0.8.17
```

Dejar el stack **arriba** durante toda la clase. Los bloques 3 a 5 no lo usan, pero no
molesta y ahorra el arranque del bloque 6.

---

## BLOQUE 1 — Arranque (0-15 min)

Sin comandos.

1. **Recuento de S04** (5 min): flows, tasks, schedules, y el pipeline que **registra pero
   no promueve**. Pregunta que conecta: *"el modelo está registrado como `@champion`.
   ¿Quién lo puede usar hoy, aparte de nosotros?"*
2. **CI de los talleres entregados** (7 min): abrir dos PR de estudiantes, mirar el
   workflow en verde o en rojo.
3. **Encuadre** (3 min): "Su modelo está en un registry y no le sirve a nadie más. Hoy lo
   convertimos en algo que otro sistema puede consumir, y de lo que se puede decir con
   precisión qué versión respondió."

---

## BLOQUE 2 — El dolor (15-40 min)

```bash
# T3 — las versiones reales del entorno (único comando del bloque)
uv run python -c "import importlib.metadata as m; print({p: m.version(p) for p in ('mlflow','xgboost','scikit-learn')})"
```

**Salida esperada:** `{'mlflow': '3.15.1', 'xgboost': '3.2.0', 'scikit-learn': '1.9.0'}`
(o las que tenga tu lock).

**Archivos que se proyectan:** la cabecera del [`Dockerfile`](../Dockerfile) de la raíz y
[`_contraejemplo-insegure-aws/predict.py`](../sesiones/s06-cloud-cicd/_contraejemplo-insegure-aws/predict.py).
**No se abre FastAPI en este bloque.**

### Acto 1 — La imagen que sirve otra cosa (14 min)

Proyectar estas dos líneas de la cabecera del `Dockerfile` y presentarlas como **el atajo
que cualquiera escribiría**:

```dockerfile
COPY pyproject.toml .
RUN pip install --no-cache-dir mlflow==2.17.2 xgboost==2.1.2 scikit-learn==1.5.2
```

Correr el comando de la caja y preguntar: *"el artefacto se entrenó con estas versiones y
la imagen instala las de arriba. ¿Qué pasa al cargarlo?"*

| Dicen | Contestar |
|---|---|
| "falla" | a veces sí, **y ese es el caso bueno**: es ruidoso |
| "no pasa nada" | a veces también, y ahí está el problema |
| "sale un warning" | `InconsistentVersionWarning`. ¿Quién lee los warnings de un contenedor en producción? |

Remate: **el peor caso no es el error, es que cargue y prediga distinto de lo que el gate
validó.** Tablero:

> Las versiones se resuelven **una** vez, en `uv.lock`. Ningún pin a mano en un `Dockerfile`.

### Acto 2 — `pickle.load` de un binario descargado (11 min)

Proyectar solo estas tres líneas de `predict.py`:

```python
with open("lin_reg.bin", "rb") as f_in:
    (dv, model) = pickle.load(f_in)
```

Pregunta y silencio: *"¿qué código se ejecuta al deserializar ese archivo?"* Respuesta:
cualquiera. `pickle` es un lenguaje con opcodes; deserializar es ejecutar un script que
alguien te mandó. Segunda pregunta: *"¿de dónde salió `lin_reg.bin`?"* No está en el
repositorio: nadie puede decir qué lo produjo. Tercer detalle: está a nivel de módulo, se
ejecuta al importar, no hay forma de fallar limpiamente.

Cierre (2 min): las dos cosas que rompen un despliegue sin avisar son **el entorno** y **la
procedencia del artefacto**. Las dos se resuelven igual: una sola fuente de verdad.
`uv.lock` para el entorno, el Model Registry para el artefacto.

---

## BLOQUE 3 — Local vs contenedor (40-62 min)

**Es el único bloque fuera de la raíz.** Se hace entero en **T2**.

```bash
# T2 — 3.1 local (4 min)
cd sesiones/s05-deployment/intro-dockers
uv run app.py
#   -> abrir http://127.0.0.1:5000 y ANOTAR el hostname en el tablero
#   -> Ctrl+C para seguir
#   (si sale "Address already in use": PUERTO=5050 uv run app.py)

# T2 — 3.3 en Docker (9 min)
pwd                                    # debe terminar en sesiones/s05-deployment/intro-dockers
docker build -t gatitos-app .          # ocho pasos, todos [stage-0 ...]
docker run -d -p 8080:5000 --name gatitos gatitos-app
#   -> abrir http://localhost:8080: misma página, otro color, OTRO hostname

# T2 — las tres verificaciones
docker run --rm --entrypoint sh gatitos-app -c 'id -u'    # 1001, no 0
docker ps                                                 # STATUS: Up ... (healthy)
docker logs gatitos                                       # no vacío
docker run --rm --entrypoint sh gatitos-app -c 'command -v curl || echo sin curl'   # sin curl

# T2 — 3.5 el cache de capas (3 min)
docker build --no-cache -t gatitos-app .   # línea base: mide el tiempo
#   -> editar app.py: agregar una URL a GATITOS
docker build -t gatitos-app .              # [4/8] y [5/8] dicen CACHED; desde [6/8] se rehace
#   -> editar pyproject.toml (basta un comentario)
docker build -t gatitos-app .              # ahora sí reinstala todo

# T2 — limpieza y VOLVER A LA RAÍZ
docker stop gatitos && docker rm gatitos
cd ../../..
pwd                                        # debe terminar en /MLOps-Course
```

**Salidas esperadas:** en local, `Gatitos App en http://127.0.0.1:5000 (entorno=local)` y el
proceso se queda esperando. En Docker, `curl -s http://127.0.0.1:8080/health` devuelve
`{"status":"ok","entorno":"docker","hostname":"<12 caracteres>"}`. `docker ps` dice
`(health: starting)` los primeros 10 s y luego `(healthy)`.

**Qué decir, en orden:**

- **3.2, antes de dockerizar (2 min):** "¿qué problemas tiene `uv run app.py` como forma de
  entregar software?" Python del host, dependencias del host, cero aislamiento, "en mi
  máquina funciona". Frase del bloque A: **el contenedor convierte el entorno completo en
  el artefacto que se despliega.**
- **3.3:** `app.py` es **el mismo archivo**. Solo cambió la variable `ENTORNO`, que fija el
  `Dockerfile`. Es lo mismo que hará la API con `TAXI_MODELO_URI`. El atajo tentador:
  `app.py` y `app_docker.py`, dos copias que se desincronizan.
- **Healthcheck:** el atajo `HEALTHCHECK CMD curl -f ...` sobre `python:slim` falla siempre
  porque **no hay `curl`** (lo acabas de comprobar). El contenedor queda `unhealthy` para
  siempre y cualquier `depends_on: service_healthy` se cuelga.
- **3.5:** cambiar código no reinstala dependencias; cambiar `pyproject.toml` sí. Mide y
  compara, no cites cifras.

**Si vas justo de tiempo:** salta la demo del "error del contexto" (construir desde la raíz
con el Dockerfile equivocado). El README de `intro-dockers` la trae con salidas reales.

---

## BLOQUE 4 — El `Dockerfile` real (62-80 min)

**Archivos abiertos en dos paneles:** [`Dockerfile`](../Dockerfile) de la raíz y el de
`intro-dockers`. También [`.dockerignore`](../.dockerignore) y el job `imagen` de
[`ci.yml`](../.github/workflows/ci.yml).

```bash
# T2 — 4.1 construir la imagen real (desde la raíz)
docker build -t mlops-curso/api:local .        # la primera vez tarda minutos; las capas base ya están
docker images | grep mlops-curso               # ~3.3 GB
docker history mlops-curso/api:local | head -15

# T2 — 4.2 las tres verificaciones, ahora sobre la imagen real
docker run --rm --entrypoint sh mlops-curso/api:local -c 'id -u'   # 1001
docker run -d --name api-local -p 8001:8000 -e TAXI_MODELO_URI=ninguno mlops-curso/api:local
sleep 5 && docker ps --filter name=api-local                        # (healthy) tras el start-period

# T3
curl -s http://127.0.0.1:8001/health | jq

# T2 — limpieza
docker rm -f api-local
```

**Nota:** se publica en el **8001** porque el 8000 lo tiene la API del stack (`make up`).

**Salida esperada del `curl`:**

```json
{"status": "degradado", "model_loaded": false, "model_name": null, "model_version": null, "model_uri": "ninguno", "version_api": "1.0.0"}
```

**Qué decir:**

- **Las siete decisiones** con la tabla del README sección 3.1 proyectada. Tiempo real a
  tres: *multi-stage* (`uv`, cache y dev-deps se quedan en el `builder`: menos peso y menos
  superficie de ataque), **`runtime` va al final** (el CI construye la última etapa), y
  **`.dockerignore`**: un `.env` copiado por `COPY . .` **no se borra con `RUN rm`**, la capa
  anterior sigue ahí.
- **`TAXI_MODELO_URI=ninguno` no es un truco de demo**: es lo que permite que el CI
  verifique la imagen sin registry. `/health` devuelve **200** y no 503 porque es liveness;
  se explica en el bloque 9.
- **4.3, el CI ya verifica esto:** abrir el job `imagen` de `ci.yml`, leer los dos pasos.
  "Un criterio que verifica una persona se deja de verificar en la tercera semana." Señalar
  el `docker logs api` antes del `exit 1`.

---

## BLOQUE 5 — Del tag mutable al digest inmutable (80-88 min)

```bash
# T2 — el tag es un puntero
docker inspect --format='{{.Id}}' mlops-curso/api:local
docker tag mlops-curso/api:local mlops-curso/api:latest
docker inspect --format='{{.Id}}' mlops-curso/api:latest    # el MISMO id

#   -> cambiar cualquier cosa del código (un comentario en src/taxi/api/main.py) y:
docker build -t mlops-curso/api:latest .
docker inspect --format='{{.Id}}' mlops-curso/api:latest    # OTRO id, mismo nombre
```

**Qué decir:** *"si esto pasó entre que probaron staging y que desplegaron producción,
¿cómo se dan cuenta?"* No se dan cuenta: los logs de las dos corridas dicen `latest`.
Proyectar la tabla del README sección 3.4 y cerrar con la analogía:

> `:latest` es a `@sha256:...` lo que `@champion` es a `versión 7`. Una **referencia
> mutable** sobre **contenido inmutable**. Para enrutar usas la referencia; para desplegar
> y auditar usas el contenido.

Es el bloque que prepara la sesión 6.

---

## BLOQUE 6 — El stack local con Compose (88-95 min)

```bash
# T1 — el stack ya está arriba desde antes de clase
docker compose ps        # seis servicios Up ... (healthy)
make logs                # ver el arranque en orden; Ctrl+C para salir del seguimiento

# T3
curl -s http://127.0.0.1:8000/health | jq -c '{model_loaded, model_version}'   # true y una versión
```

**Archivo:** [`docker-compose.yml`](../docker-compose.yml). Siete minutos, tres cosas y
ninguna más:

1. `--artifacts-destination=s3://mlflow/` con `MLFLOW_S3_ENDPOINT_URL` apuntando a
   **MinIO, que habla protocolo S3**. Contra AWS se borra el endpoint y el resto es idéntico.
   Es el puente con la sesión 6, en una frase.
2. **El servicio `api` no define `healthcheck`**: lo define la imagen, porque depende de qué
   binarios tiene. Dos definiciones se desincronizan.
3. **No hay clave `version:`**: Compose v2 la ignora y avisa que está obsoleta.

El stack es infraestructura de apoyo, no el tema. Seguir.

---

## PAUSA (95-110 min)

```bash
# T2 — lanzar y DEJAR CORRIENDO durante la pausa
make batch               # equivale a: uv run python -m taxi.flows.batch
# (si data/ no está preparado: uv run taxi data primero, y por eso se lanza aquí)
```

---

## BLOQUE 7 — El contrato (110-125 min)

**Archivo:** [`src/taxi/api/schemas.py`](../src/taxi/api/schemas.py). La API del stack ya
está arriba en el 8000.

```bash
# T3 — 7.3 probarlo en vivo (3 min)
#   -> abrir http://127.0.0.1:8000/docs en el navegador: la documentación viva de la API

# un request válido
curl -sX POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' \
  -d '{"PULocationID": 43, "DOLocationID": 238, "trip_distance": 2.4, "pickup_datetime": "2023-05-15T08:30:00"}' | jq

# una zona que no existe -> 422 señalando PULocationID
curl -sX POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' \
  -d '{"PULocationID": 9999, "DOLocationID": 238, "trip_distance": 2.4}' | jq

# el que más impresiona: la "i" minúscula -> 422 por extra="forbid"
curl -sX POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' \
  -d '{"PULocationId": 43, "DOLocationID": 238, "trip_distance": 2.4}' | jq
```

**Salidas esperadas:** el primero devuelve `duration_min`, `viaje_largo`, `model_name`,
`model_version` y `latencia_ms`. Los otros dos, `422` con `detalle_validacion`.

**Qué decir:**

- **7.1 (4 min), empezar con el problema, no con Pydantic:** "del otro lado de su API hay
  clientes que no leyeron el contrato de features. ¿Qué pasa si mandan `trip_distance:
  -40`?" No pasa un error: pasa una **predicción absurda con 200**, indistinguible de una
  correcta.
- **7.2 (8 min), las cuatro decisiones de `ViajeRequest`:**

| Decisión | Frase |
|---|---|
| `extra="forbid"` | "`PULocationId` da 422 en lugar de una predicción con el default silencioso. Fallar ruidosamente es más barato que degradar en silencio" |
| rangos 1-265 y 0-100 mi | "los mismos del contrato de datos de S02" |
| `@field_validator` rechaza el offset | "quien manda `08:30:00Z` cree hablar de las 08:30 y el modelo entendería 04:30" |
| response separado, con `model_version` | "esto hace auditable una predicción tres semanas después" |

- Lo que **no** se pide al cliente: `PU_DO`, `hora_pickup`, `dia_semana_pickup`. "Pedir
  features derivadas al cliente es pedirle que replique su pipeline."

---

## BLOQUE 8 — El ciclo de vida y la carga por alias (125-140 min)

**Archivos:** [`main.py`](../src/taxi/api/main.py) (el `lifespan`) y
[`modelo.py`](../src/taxi/api/modelo.py).

```bash
# T3 — 1. qué versión está sirviendo
curl -s http://127.0.0.1:8000/health | jq '{model_version, model_uri}'

# T3 — 2. qué versiones existen, para elegir OTRA que exista
uv run python -c "
from taxi.models import registry
for v in registry.cliente().search_model_versions(\"name='nyc-taxi-duration'\"): print(v.version, v.aliases)
"
# T3 — 3. mover el alias a otra versión existente (cambia el 2 por una que tengas)
uv run python -c "from taxi.models import registry; registry.asignar_alias('nyc-taxi-duration', 'champion', '2')"

# T1 — 4. reiniciar SOLO el proceso. Sin rebuild, sin redeploy.
docker compose restart api && sleep 8

# T3 — 5. cambió la versión, no la imagen
curl -s http://127.0.0.1:8000/health | jq '{model_version, model_uri}'

# T3 — 6. DEJAR EL CHAMPION COMO ESTABA (la versión del paso 1) antes de seguir
uv run python -c "from taxi.models import registry; registry.asignar_alias('nyc-taxi-duration', 'champion', '<version del paso 1>')"
```

**Salida esperada:** entre el paso 1 y el 5 cambia `model_version`; `model_uri` es el mismo
(`models:/nyc-taxi-duration@champion`). **No se reconstruyó nada.**

**Qué decir:**

- **8.1 (4 min), `lifespan` y no `@app.on_event`:** deprecado desde FastAPI 0.93; `lifespan`
  libera recursos al apagar y se comporta igual bajo `TestClient` y bajo `uvicorn`. Dos
  decisiones del arranque: **cargar al arrancar** (el cold start se vería como un timeout
  aleatorio tras cada despliegue) y **no abortar si la carga falla** (un contenedor que
  muere al arrancar entra en bucle y nadie puede leer `/health`).
- **8.2 (8 min), la decisión central:** leer en el docstring de `modelo.py` las cuatro
  consecuencias del atajo `copy_model.py`, y luego la línea que lo reemplaza:
  `mlflow.pyfunc.load_model("models:/nyc-taxi-duration@champion")`. Correr la caja. La
  pregunta de cierre: *"¿cuánto habría tardado esto con el `copy_model.py`?"* Copiar,
  reconstruir, redesplegar, y sin poder decir después qué versión era.
- **8.3 (3 min):** `_resolver_identidad` pregunta al registry **qué versión resolvía el alias
  en el momento de la carga** y la guarda. "Si no, en sus logs queda `champion` y en seis
  meses eso no dice nada."

---

## BLOQUE 9 — Endpoints operativos y errores (140-152 min)

**Archivos:** [`main.py`](../src/taxi/api/main.py), [`metricas.py`](../src/taxi/api/metricas.py),
[`tests/api/`](../tests/api/).

```bash
# T3 — 9.1 cuatro endpoints, cuatro consumidores
curl -s http://127.0.0.1:8000/health | jq
curl -s http://127.0.0.1:8000/modelo | jq
curl -s http://127.0.0.1:8000/metrics | grep -E "^taxi_" | head -20

# T3 — 9.3 los tests corren sin MLflow y sin red (opcional, si hay tiempo)
uv run pytest tests/api -q
```

**Qué decir:**

- **9.1 (5 min):** la tabla del README sección 4.4 y **la pregunta trampa**: *"`/health`
  devuelve 200 con `model_loaded: false`. ¿Reinicio el contenedor? ¿Le mando tráfico?"*
  **No** reiniciar (liveness) y **no** mandar tráfico (readiness, sobre `model_loaded`).
  Confundir los dos es el error más caro. En `/metrics`, el label `model_version` es el
  puente con la sesión 7.
- **9.2 (4 min), errores que no filtran internals:** al cliente un mensaje estable más un
  `id_correlacion`; al log, la traza completa. Excepción: el 422, porque describe el request
  del cliente. El anti-patrón `detail=f"Error: {str(e)}"` filtra rutas y cadenas de conexión.
- **9.3 (3 min), `def` y no `async def`:** `model.predict` es bloqueante; en una corrutina
  congela el event loop y el servidor atiende **un** request a la vez. Los tests corren sin
  MLflow gracias a la costura `cargar_pyfunc` de `tests/api/conftest.py`.

---

## BLOQUE 10 — Batch y trazabilidad en SQL (152-160 min)

**Archivo:** [`src/taxi/flows/batch.py`](../src/taxi/flows/batch.py). El `make batch` de la
pausa ya terminó (mirar T2).

```bash
# T3
sqlite3 -header -column data/predicciones.db \
  "SELECT batch_id, particion, model_version, model_alias, COUNT(*) AS n,
          ROUND(AVG(prediccion_minutos), 2) AS media_min
     FROM predicciones GROUP BY 1,2,3,4 ORDER BY 1;"
```

**Qué decir (8 min):** cada fila lleva la versión que la produjo. *"Mañana hacen rollback
del modelo. ¿Qué predicciones de esta tabla hay que revisar?"* Sin la columna: "todas" o
"ninguna". Con la columna: un `WHERE`. Los cuatro atajos tentadores del docstring de
`batch.py`: datos sintéticos con semilla fija, kilómetros contra un modelo en millas,
`iterrows()`, y `'stage': 'Production'` como literal. Límite de SQLite: un escritor, sin
acceso remoto; `batch.py` soporta Postgres con `DATABASE_URL`.

---

## BLOQUE 11 — La decisión y las alternativas (160-165 min)

Sin comandos. **Archivos:** README secciones 6 y 7,
[ADR 006](../docs/adr/006-serving-online-vs-batch.md).

1. **La matriz batch / online / streaming** con los cinco criterios. La frase: **empieza en
   batch**; si el consumidor puede esperar al próximo corte, un job es más barato y más
   fácil de auditar que un servicio.
2. **La tabla de alternativas**, tres avisos: `mlflow models serve` es para demos; **BentoML
   es el paso 2 natural**; **MLServer: última release estable de junio de 2025**, no
   presentarlo como vivo sin verificar.

Por qué FastAPI en el curso: **es la capa donde se ven los conceptos.**

---

## BLOQUE 12 — Taller (165-220 min)

**Archivo:** [`taller.md`](../sesiones/s05-deployment/taller.md).

**Arranque (5 min):** leer los ocho criterios de aceptación. *"Se verifican ejecutando, no
leyendo."* Mencionar la colección de `postman/` (Run collection verifica el contrato) y que
`_soluciones/verificar.sh` genera la evidencia, sin abrir las soluciones.

**Circulación (45 min):**

| Lo que verás | Qué preguntar |
|---|---|
| El modelo se copia a la imagen | "¿qué tienen que hacer para cambiar de modelo?" |
| Tests que necesitan MLflow arriba | "¿qué pasa con esto en el CI?" |
| `HEALTHCHECK` con `curl` sobre `python:slim` | "corran `command -v curl` dentro de la imagen" |

**Cierre (5 min):** dos estudiantes proyectan su `docker compose ps` con `(healthy)` y su
`curl /health`.

---

## BLOQUE 13 — Cierre (220-240 min)

Sin comandos hasta la limpieza. **Archivos:** README secciones 8, 9 y 10.

- **13.1 Autoverificación (7 min):** las cinco preguntas del README, 30 segundos de
  silencio cada una, **sin responderlas**. Si nadie sabe la 3 ("cambias de la versión 7 a
  la 8: qué reconstruyes, qué reinicias, qué no se toca"), volver al bloque 8.
- **13.2 Trade-offs (5 min):** la tabla de la sección 8 del README. La fila importante:
  **si su equipo tiene volumen real, el siguiente paso es BentoML, no más FastAPI.**
- **13.3 Qué NO usar (5 min):** `app.run(debug=True, host="0.0.0.0")`, `pickle.load` sin
  linaje, `imagen:latest` como unidad de despliegue.
- **13.4 Tarea y puente (3 min):** terminar el taller y abrir el PR con la salida de
  `verificar.sh`. El puente:

> "Hoy desplegaron a mano: build, tag, push, actualizar, verificar. La próxima vez
> cronometramos eso. Y una pregunta que hoy no tiene respuesta: **su pipeline termina en
> verde y despliega. ¿Qué garantiza eso sobre el modelo que está sirviendo?**"

```bash
# T2 — limpieza al terminar
docker rm -f api-local gatitos 2>/dev/null || true
docker rmi mlops-curso/api:latest 2>/dev/null || true

# T1
make down                 # el stack; los volúmenes conservan el registry
```

---

## Anexo — Plan B si Docker falla en tu equipo

Los bloques 3 a 6 necesitan Docker; sin él, se leen los archivos y se proyectan las
salidas que traen el README de la sesión y el de `intro-dockers`. Ten a mano una captura
de `docker ps` con `(healthy)`.

Los bloques 7 a 11 funcionan sin contenedor:

```bash
# T1 — el registry, con SQLite (bloquea; déjala abierta)
make mlflow

# T3 — champion contra ESTE registry (es otro distinto al del stack)
uv run taxi train --registrar && uv run taxi promote

# T2 — la API en el 8000 (bloquea; déjala abierta)
make serve
```

En el bloque 8, "reiniciar solo el proceso" es `Ctrl+C` en T2 y `make serve` otra vez.
Todo lo demás es idéntico.
