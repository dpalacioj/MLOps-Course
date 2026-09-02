# Guion de clase — Sesión 5: Deployment

Guion minutado para las **4 horas** del formato de sesión del curso. Cada bloque indica
qué archivo abrir, qué comando correr y qué salida esperar.

**Duración total:** 240 min (4 h), con pausa de 15 min.
**Terminales:** 1 hasta el bloque 6; 3 desde el bloque 7 (API, MLflow, cliente).
**Directorio base:** la **raíz del repositorio**. Todos los comandos se corren desde ahí,
salvo el bloque 3, que se corre dentro de `sesiones/s05-deployment/intro-dockers/`.
**Material del estudiante:** [`sesiones/s05-deployment/`](../sesiones/s05-deployment/).

| Tramo | Min | Bloques |
|---|---|---|
| Arranque | 0-15 | 1 |
| El dolor | 15-40 | 2 |
| Bloque A — empaquetar | 40-95 | 3, 4, 5, 6 |
| Pausa | 95-110 | — |
| Bloque B — servir | 110-165 | 7, 8, 9, 10, 11 |
| Taller | 165-220 | 12 |
| Cierre | 220-240 | 13 |

---

## Antes de clase (checklist del instructor)

```bash
# 1. Un @champion tiene que existir, o media sesión no se puede demostrar.
uv run python -c "
from taxi.models import registry
mv = registry.version_por_alias('nyc-taxi-duration', 'champion')
print('champion ->', mv.version if mv else 'NO HAY. Corre: taxi data && taxi train --hpo && taxi promote')
"

# 2. Las imágenes base descargadas, para que el build en vivo no espere la red.
docker pull python:3.11-slim-bookworm
docker pull ghcr.io/astral-sh/uv:0.8.17
docker pull ghcr.io/mlflow/mlflow:v3.15.1

# 3. El stack levanta y baja.
make up && make down

# 4. jq y sqlite3 instalados: se usan en vivo en los bloques 9 y 10.
command -v jq sqlite3
```

**Plan B si Docker falla en el equipo del instructor:** los bloques 7 a 11 funcionan con
`make serve` (uvicorn en local, sin contenedor). Los bloques 3 a 6 son los que necesitan
Docker; si no hay, se leen los archivos y se proyecta la salida de una corrida previa.
Ten a mano una captura del `docker ps` con `(healthy)`.

---

## Mapa de archivos

Lo que se toca en esta sesión. El servicio vive en el paquete; la carpeta de la sesión lo
ejecuta y lo analiza.

```
src/taxi/api/                        # EL servicio, una sola vez
├── schemas.py                       # Bloque 7: el contrato
├── modelo.py                        # Bloque 8: carga por alias
├── metricas.py                      # Bloque 9: instrumentación
└── main.py                          # Bloques 8 y 9: wiring, lifespan, errores

src/taxi/flows/batch.py              # Bloque 10: la misma inferencia, en batch

Dockerfile                           # Bloque 4
.dockerignore                        # Bloque 4
docker-compose.yml                   # Bloque 6
.github/workflows/ci.yml             # Bloque 4 (job `imagen`)

sesiones/s05-deployment/
├── README.md                        # Bloques 2, 11 y 13
├── api-contract.md                  # Bloque 9 y taller
├── taller.md                        # Bloque 12
├── intro-dockers/                   # Bloque 3
│   ├── app.py                       #   una sola app, ENTORNO por variable
│   ├── Dockerfile                   #   la versión mínima correcta
│   ├── .dockerignore
│   ├── pyproject.toml + uv.lock
│   └── templates/index.html
├── postman/                         # Bloque 12 (taller)
└── _soluciones/                     # no publicar antes del taller
    ├── solucion-taller.md
    └── verificar.sh

tests/api/                           # Bloque 9
docs/adr/006-serving-online-vs-batch.md   # Bloque 11
```

---

## BLOQUE 1 — Arranque (0-15 min)

**Archivos:** ninguno. **Terminales:** 0.

1. **Arranque directo** (5 min): dudas sueltas de S04 si las hay, y en una frase propia lo que quedó — flows, tasks,
   schedules, y el pipeline que **registra pero no promueve**. La pregunta de cierre que
   conecta con hoy: *"el modelo está registrado con el alias `@champion`. ¿Quién lo puede
   usar hoy, aparte de nosotros?"*
2. **Revisión del CI de los talleres entregados** (7 min): abrir dos PR de estudiantes y
   mirar el workflow en verde o en rojo. Rutina de todas las sesiones.
3. **Encuadre de hoy** (3 min): "Su modelo está en un registry y no le sirve a nadie más
   que a ustedes. Hoy lo convertimos en algo que otro sistema puede consumir, y en algo
   de lo que se puede decir con precisión qué versión respondió."

---

## BLOQUE 2 — El dolor (15-40 min)

**Archivos:** el `Dockerfile` (solo la cabecera) y
`sesiones/s06-cloud-cicd/_contraejemplo-insegure-aws/predict.py`.
**Terminales:** 1. **No se abre FastAPI en este bloque.**

### Acto 1 — La imagen que sirve otra cosa (14 min)

Proyectar el bloque de comentarios de la cabecera del [`Dockerfile`](../Dockerfile) y leer
en voz alta las tres líneas del anti-patrón:

```dockerfile
COPY pyproject.toml .
RUN pip install --no-cache-dir mlflow==2.17.2 xgboost==2.1.2 scikit-learn==1.5.2
```

**Decir explícitamente que este error es de este curso**, no un ejemplo inventado. Es la
frase que hace que la clase preste atención.

Después, las versiones reales del entorno:

```bash
uv run python -c "import importlib.metadata as m; print({p: m.version(p) for p in ('mlflow','xgboost','scikit-learn')})"
```

**Preguntar antes de responder:** "el artefacto se entrenó con estas versiones y la imagen
instala las de arriba. ¿Qué pasa al cargarlo?"

Las respuestas que suelen salir y qué contestar:

| Dicen | Contestar |
|---|---|
| "falla" | a veces sí, **y ese es el caso bueno**: es ruidoso |
| "no pasa nada, es compatible" | a veces también, y ahí está el problema |
| "sale un warning" | `InconsistentVersionWarning`. ¿Quién lee los warnings de un contenedor en producción? |

Y el remate: **el peor caso no es el error, es que cargue y prediga distinto de lo que el
gate validó.** Un modelo aprobado en CI y una imagen que sirve otra cosa, sin un solo
error en los logs.

Si quieres reproducirlo en vivo (**opcional, 4 min**), un entorno efímero con la versión
vieja:

```bash
# Requiere red. Si no la hay, sáltalo: el argumento no depende de la demo.
uv run --isolated --with "scikit-learn==1.5.2" python -c "
import warnings, pickle
warnings.simplefilter('always')
print('sklearn', __import__('sklearn').__version__)
print('Ahora cargariamos un estimador pickled por 1.9.x. Mide y compara el warning.')
"
```

**No prometas una salida concreta**: depende de con qué se entrenó el `@champion` de tu
máquina. Si el warning no aparece, dilo — el punto conceptual (dos resoluciones de
dependencias) se sostiene igual, y admitirlo enseña más que forzar la demo.

Cierre del acto: escribir en el tablero la regla, que es lo único que hay que memorizar.

> Las versiones se resuelven **una** vez, en `uv.lock`. Ningún pin a mano en un
> `Dockerfile`.

### Acto 2 — `pickle.load` de un binario descargado (11 min)

Abrir [`_contraejemplo-insegure-aws/predict.py`](../sesiones/s06-cloud-cicd/_contraejemplo-insegure-aws/predict.py)
y proyectar solo estas tres líneas:

```python
with open("lin_reg.bin", "rb") as f_in:
    (dv, model) = pickle.load(f_in)
```

**La pregunta, y dejar silencio:** *"¿qué código se ejecuta al deserializar ese archivo?"*

Casi nadie responde "cualquiera". Cuando alguien lo diga, o cuando pasen 20 segundos,
explicar: `pickle` no es un formato de datos, es un lenguaje con opcodes; `REDUCE` invoca
un callable con argumentos del propio archivo. Deserializar un pickle es ejecutar un
script que alguien te mandó. Citar la documentación de Python: *"the pickle module is not
secure."*

Segunda pregunta, que aterriza el argumento: *"¿de dónde salió `lin_reg.bin`?"* La
respuesta: no está en el repositorio; según la guía, aparece con un `git clone`. **Nadie
puede decir qué lo produjo.**

Tercer detalle, más sutil y muy útil: el `pickle.load` está **a nivel de módulo**, así que
se ejecuta al importar, antes de que exista un endpoint. No hay forma de aislarlo ni de
fallar limpiamente; si el archivo falta, el proceso muere en el import.

Cierre del bloque (2 min): las dos cosas que rompen un despliegue sin que nada avise son
**el entorno** y **la procedencia del artefacto**. Las dos se resuelven con lo mismo: una
sola fuente de verdad. `uv.lock` para el entorno, el Model Registry para el artefacto.

---

## BLOQUE 3 — Local vs contenedor (40-58 min)

**Archivos:** `sesiones/s05-deployment/intro-dockers/`. **Terminales:** 2.

Es el único bloque que se corre desde otro directorio.

### 3.1 Local (5 min)

```bash
cd sesiones/s05-deployment/intro-dockers
uv run app.py
```

Abrir <http://127.0.0.1:5000>. **Anotar el `hostname` que muestra la página** en el
tablero: se compara en un minuto.

`Ctrl+C`.

### 3.2 Preguntar antes de dockerizar (3 min)

"¿Qué problemas tiene esto como forma de entregar software?" Recoger respuestas y
ordenarlas: Python del host, dependencias del host, cero aislamiento, "en mi máquina
funciona".

Y la frase que enmarca todo el bloque A: **el contenedor convierte el entorno completo en
el artefacto que se despliega.** Eso es todo lo que hace, y es suficiente.

### 3.3 El contenedor (10 min)

```bash
docker build -t gatitos-app .
docker run -d -p 8080:5000 --name gatitos gatitos-app
```

Abrir <http://localhost:8080>: misma página, otro color, **otro `hostname`** — el id del
contenedor. Comparar con el del tablero.

**Qué explicar:** el `app.py` es **el mismo archivo**. Lo único que cambió es la variable
`ENTORNO`, que fija el `Dockerfile`. Es el principio de configuración por entorno, y es lo
mismo que hace la API real con `TAXI_MODELO_URI`.

**Nota para el instructor:** este material cambió. Antes había `app.py` y `app_docker.py`,
dos archivos idénticos al 95% que diferían en el color del fondo. Mencionarlo: es el
anti-patrón del curso aplicado a un ejemplo de juguete, y la corrección es la misma que en
un servicio real.

Las tres verificaciones, que se repiten en el bloque 4 sobre la imagen real:

```bash
docker run --rm --entrypoint sh gatitos-app -c 'id -u'   # != 0
docker ps                                                # STATUS: (healthy)
docker logs gatitos                                      # no vacío
```

Sobre el healthcheck, contar la historia completa: el compose anterior del curso usaba
`curl` sobre una imagen `python:3.11-slim`, **que no lo trae**. El check fallaba siempre,
el contenedor quedaba permanentemente `unhealthy` y cualquier `depends_on:
service_healthy` se colgaba. Es el tipo de bug que nadie mira porque "el servicio
responde".

### 3.4 El cache de capas: medirlo (5 min)

```bash
docker build --no-cache -t gatitos-app .    # línea base
# editar app.py: agregar una URL a GATITOS
docker build -t gatitos-app .               # ¿qué pasos dicen CACHED?
# editar pyproject.toml
docker build -t gatitos-app .               # ahora sí reinstala
```

**Mide y compara los tres tiempos en tu equipo.** No hay cifras en el material a
propósito: dependen de la red, del disco y de si la capa base está descargada. Un número
inventado en un README es peor que ningún número.

Limpieza: `docker stop gatitos && docker rm gatitos && cd -`

---

## BLOQUE 4 — El `Dockerfile` real (58-78 min)

**Archivos:** [`Dockerfile`](../Dockerfile), [`.dockerignore`](../.dockerignore),
[`ci.yml`](../.github/workflows/ci.yml). **Terminales:** 1.

Abrir el `Dockerfile` de la raíz **al lado** del de `intro-dockers`. La sesión de este
bloque es la diferencia entre los dos.

### 4.1 Las siete decisiones (12 min)

Recorrer con la tabla del [README sección 4.1](../sesiones/s05-deployment/README.md) proyectada.
Dedicar tiempo real a tres:

**Multi-stage.** Preguntar: "¿por qué dos etapas si la app es la misma?" Respuesta: `uv`,
el cache de compilación y las dev-deps se quedan en el `builder`. Menos peso y **menos
superficie de ataque**: `ruff`, `mypy` y `pytest` no tienen nada que hacer en una imagen
de producción.

```bash
docker build -t mlops-curso/api:local .
docker images | grep mlops-curso
docker history mlops-curso/api:local | head -15
```

**`runtime` va al final, a propósito.** `docker build` sin `--target` construye la última
etapa, y el job `imagen` del CI depende de eso. Mover `runtime` hacia arriba haría que el
CI verificara la imagen equivocada. Es el tipo de acoplamiento que hay que dejar
comentado.

**El `.dockerignore` y sus tres razones**, en orden de importancia: seguridad,
correctitud, velocidad. La de seguridad es la que sorprende:

> Un `.env` copiado por un `COPY . .` descuidado **no se borra** agregando un `RUN rm`.
> La capa anterior sigue ahí, y es pública si la imagen es pública.

### 4.2 Las tres verificaciones, ahora sobre la imagen real (5 min)

```bash
docker run --rm --entrypoint sh mlops-curso/api:local -c 'id -u'   # 1001

docker run -d --name api-local -p 8000:8000 \
  -e TAXI_MODELO_URI=ninguno mlops-curso/api:local
sleep 5 && docker ps --filter name=api-local
curl -s http://127.0.0.1:8000/health | jq
```

**Salida esperada** (el `version_api` puede diferir):

```json
{
  "status": "degradado",
  "model_loaded": false,
  "model_name": null,
  "model_version": null,
  "model_uri": "ninguno",
  "version_api": "1.0.0"
}
```

**Qué explicar:** `TAXI_MODELO_URI=ninguno` **no es un truco de demo**, es lo que permite
que el CI verifique la imagen sin levantar un registry. Y `/health` devuelve **200**, no
503, porque es un *liveness* check — se explica a fondo en el bloque 9.

### 4.3 El CI ya verifica esto (3 min)

Abrir el job `imagen` de [`ci.yml`](../.github/workflows/ci.yml) y leer los dos pasos.

**La frase:** "un criterio que verifica una persona se deja de verificar en la tercera
semana. Este está automatizado, y es un criterio de aceptación de su taller."

Señalar también el `docker logs api` antes del `exit 1`: un job que falla sin dejar el log
obliga a reproducir el fallo en local.

Limpieza: `docker rm -f api-local`

---

## BLOQUE 5 — Del tag mutable al digest inmutable (78-88 min)

**Archivos:** ninguno; terminal y tablero. **Terminales:** 1.

Es el bloque que prepara la sesión 6. Diez minutos, y son de los mejor invertidos de la
sesión.

```bash
docker inspect --format='{{.Id}}' mlops-curso/api:local
docker tag mlops-curso/api:local mlops-curso/api:latest
docker inspect --format='{{.Id}}' mlops-curso/api:latest   # el MISMO id
```

Después, la demostración de que el tag es un puntero:

```bash
# Cambiar cualquier cosa del código y reconstruir con el MISMO tag
docker build -t mlops-curso/api:latest .
docker inspect --format='{{.Id}}' mlops-curso/api:latest   # OTRO id, mismo nombre
```

**La pregunta:** *"si esto pasó entre que probaron staging y que desplegaron producción,
¿cómo se dan cuenta?"* Respuesta: no se dan cuenta. Los logs de las dos corridas dicen
`latest`.

Proyectar la tabla del [README sección 4.3](../sesiones/s05-deployment/README.md) y cerrar con la
analogía, que es el punto pedagógico:

> `:latest` es a `@sha256:...` lo que `@champion` es a `versión 7`. Una **referencia
> mutable** sobre **contenido inmutable**. Para enrutar usas la referencia; para desplegar
> y auditar usas el contenido.

Si alguien pregunta cómo se ve el digest de un registro remoto, adelantar una línea de la
sesión 6: `docker inspect --format='{{index .RepoDigests 0}}' <imagen>` después de un
push.

---

## BLOQUE 6 — El stack local con Compose (88-95 min)

**Archivos:** [`docker-compose.yml`](../docker-compose.yml). **Terminales:** 2.

```bash
make up
docker compose ps
```

Siete minutos, tres cosas y ninguna más:

1. **`--artifacts-destination=s3://mlflow/` con `MLFLOW_S3_ENDPOINT_URL` apuntando a
   MinIO, que habla protocolo S3.** Es la pieza que hace transferible la sesión 6: contra
   AWS se borra el endpoint y el resto del comando es idéntico. Adelántalo en una frase.
2. **El servicio `api` no define `healthcheck`.** Lo define la imagen. Explicar por qué:
   el healthcheck depende de qué binarios tiene la imagen, así que pertenece a la imagen.
   Dos definiciones se desincronizan.
3. **No hay clave `version:`.** El compose anterior empezaba con `version: '3.8'`; Compose
   v2 la ignora y avisa que está obsoleta.

`make logs` para ver el arranque en orden, y seguir. **No** dedicar más tiempo: el stack es
infraestructura de apoyo, no el tema.

---

## PAUSA (95-110 min)

Antes de la pausa, lanzar en la terminal 2 y **dejarlo corriendo**:

```bash
make batch      # equivale a: uv run python -m taxi.flows.batch
```

Así el bloque 10 tiene datos que consultar sin esperar. Si `data/` no está preparado,
`uv run taxi data` primero — eso sí tarda, y es la razón de lanzarlo aquí.

---

## BLOQUE 7 — El contrato (110-125 min)

**Archivo:** [`src/taxi/api/schemas.py`](../src/taxi/api/schemas.py). **Terminales:** 3.

### 7.1 La frontera de confianza (4 min)

Empezar con el problema, no con Pydantic:

> "Del otro lado de su API hay clientes que no conocen el modelo y no leyeron el contrato
> de features. ¿Qué pasa si mandan `trip_distance: -40`?"

La respuesta que hay que sacar: **no pasa un error, pasa una predicción absurda** que el
cliente consume como válida. Una respuesta 200 con un valor sin sentido es indistinguible
de una correcta.

### 7.2 Las cuatro decisiones del archivo (8 min)

Leer `ViajeRequest` en pantalla y detenerse en:

| Decisión | Frase para la clase |
|---|---|
| `extra="forbid"` | "`PULocationId` con i minúscula da 422 en lugar de una predicción con el default silencioso. Fallar ruidosamente es más barato que degradar en silencio" |
| rangos 1-265 y 0-100 mi | "los mismos del contrato de datos de S02. Si el modelo nunca vio un valor, la API no debe aceptarlo" |
| `@field_validator` rechaza el offset | "quien manda `08:30:00Z` cree hablar de las 08:30 y el modelo entendería 04:30. Mejor un 422 hoy que un reporte de drift el mes que viene" |
| response separado, con `model_version` | "esto es lo que hace auditable una predicción tres semanas después" |

Señalar también lo que **no** se pide al cliente: `PU_DO`, `hora_pickup`,
`dia_semana_pickup`. "Pedir features derivadas al cliente es pedirle que replique su
pipeline."

### 7.3 Probarlo en vivo (3 min)

Terminal 3, con la API del stack ya arriba:

```bash
curl -sX POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' \
  -d '{"PULocationID": 9999, "DOLocationID": 238, "trip_distance": 2.4}' | jq
```

**Salida esperada:** 422 con `detalle_validacion` señalando `PULocationID`.

Y el que más impresiona:

```bash
curl -sX POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' \
  -d '{"PULocationId": 43, "DOLocationID": 238, "trip_distance": 2.4}' | jq
```

422 por la `i` minúscula. "Sin `extra='forbid'`, esto habría devuelto una predicción."

---

## BLOQUE 8 — El ciclo de vida y la carga por alias (125-140 min)

**Archivos:** [`main.py`](../src/taxi/api/main.py) (el `lifespan`) y
[`modelo.py`](../src/taxi/api/modelo.py). **Terminales:** 3.

### 8.1 `lifespan`, no `@app.on_event` (4 min)

Leer el `lifespan` y dar las tres razones: `on_event` está deprecado desde FastAPI 0.93,
`lifespan` permite liberar recursos al apagar, y es lo único que se comporta igual bajo
`TestClient` y bajo `uvicorn`.

Las dos decisiones del arranque, con su consecuencia:

- **cargar al arrancar**, no en el primer request → el *cold start* se manifestaría como
  un timeout aparentemente aleatorio tras cada despliegue;
- **no abortar si la carga falla** → un contenedor que muere al arrancar entra en
  `CrashLoopBackOff` y nadie puede leer `/health`, que es donde está el motivo.

### 8.2 La decisión central de la sesión (8 min)

Abrir el docstring de [`modelo.py`](../src/taxi/api/modelo.py) y leer las cuatro
consecuencias del `copy_model.py` que se eliminó. Después mostrar el reemplazo:

```python
mlflow.pyfunc.load_model("models:/nyc-taxi-duration@champion")
```

**La demostración que hay que hacer en vivo** — es la que se recuerda:

```bash
# 1. Qué versión está sirviendo
curl -s http://127.0.0.1:8000/health | jq '{model_version, model_uri}'

# 2. Mover el alias a otra versión (usa una que exista en tu registry)
uv run python -c "from taxi.models import registry; registry.asignar_alias('nyc-taxi-duration', 'champion', '6')"

# 3. Reiniciar SOLO el proceso. Sin rebuild, sin redeploy.
docker compose restart api
sleep 8
curl -s http://127.0.0.1:8000/health | jq '{model_version, model_uri}'
```

**Salida esperada:** el `model_version` cambia; el `model_uri` es el mismo. **No se
reconstruyó nada.**

Y la pregunta de cierre: *"¿cuánto habría tardado esto con el `copy_model.py`?"* Respuesta:
copiar el directorio, reconstruir la imagen, volver a desplegar. Y sin poder decir después
qué versión era.

Dejar el champion como estaba antes de seguir.

### 8.3 El detalle del alias resuelto (3 min)

`_resolver_identidad` en `modelo.py`: con una URI por alias hay que **preguntarle al
registry qué versión resolvía en el momento de la carga** y guardarla.

"Si no lo hacen, en sus logs queda `champion` y dentro de seis meses eso no dice nada."

---

## BLOQUE 9 — Endpoints operativos y errores (140-152 min)

**Archivos:** [`main.py`](../src/taxi/api/main.py),
[`metricas.py`](../src/taxi/api/metricas.py), [`tests/api/`](../tests/api/).
**Terminales:** 3.

### 9.1 Cuatro endpoints, cuatro consumidores (5 min)

Proyectar la tabla del [README sección 3.4](../sesiones/s05-deployment/README.md) y detenerse en
la distinción que más se equivoca:

```bash
curl -s http://127.0.0.1:8000/health | jq
curl -s http://127.0.0.1:8000/modelo | jq
curl -s http://127.0.0.1:8000/metrics | grep -E "^taxi_" | head -20
```

**La pregunta trampa:** *"`/health` devuelve 200 con `model_loaded: false`. ¿Reinicio el
contenedor? ¿Le mando tráfico?"*

Las dos respuestas son distintas y ahí está la lección: **no** reiniciar (liveness: el
proceso está vivo, y reiniciarlo en bucle impide leer el diagnóstico) y **no** mandar
tráfico (readiness: se construye sobre `model_loaded`). Confundir los dos checks es el
error más caro de la lista.

En `/metrics`, señalar el label `model_version`: "es el puente con la sesión 7. Sin ese
label, un cambio de modelo es invisible en Grafana."

### 9.2 Errores que no filtran internals (4 min)

Leer los dos handlers de `main.py`. La regla, en una tabla en el tablero: al cliente un
mensaje estable más un `id_correlacion`; al log, la traza completa. **Excepción: el 422**,
porque ese detalle describe el request del cliente, no el interior del servidor.

Y el anti-patrón, con su consecuencia concreta: `detail=f"Error: {str(e)}"` filtra rutas
del filesystem, cadenas de conexión y trazas del ORM a cualquiera que sepa mandar un
request malformado.

### 9.3 `def`, no `async def` (3 min)

Leer el comentario deliberado sobre `predecir`. "`model.predict` es bloqueante. En una
corrutina congela el event loop y el servidor atiende **un** request a la vez, sin importar
cuántos workers tenga. Es un cambio de una palabra con efecto medible en el throughput."

Si hay tiempo y curiosidad, los tests que lo cubren:

```bash
uv run pytest tests/api -q
```

Y el dato que importa: **corren sin MLflow y sin red**. Mostrar `tests/api/conftest.py` y
la costura `cargar_pyfunc`. "Un test que depende de un servicio externo no es un test
unitario; es un test de integración disfrazado, y acaba marcado como `skip`."

---

## BLOQUE 10 — Batch y trazabilidad en SQL (152-160 min)

**Archivo:** [`src/taxi/flows/batch.py`](../src/taxi/flows/batch.py). **Terminales:** 2.

El batch que se lanzó en la pausa ya terminó.

```bash
sqlite3 -header -column data/predicciones.db \
  "SELECT batch_id, particion, model_version, model_alias, COUNT(*) AS n,
          ROUND(AVG(prediccion_minutos), 2) AS media_min
     FROM predicciones GROUP BY 1,2,3,4 ORDER BY 1;"
```

**Qué explicar** (5 min): cada fila lleva la versión que la produjo. La pregunta que lo
justifica:

> "Mañana hacen rollback del modelo. ¿Qué predicciones de esta tabla hay que revisar?"

Sin la columna, la respuesta es "todas" o "ninguna". Con la columna, es una cláusula
`WHERE`.

Después, las cuatro trampas que el docstring de `batch.py` enumera (3 min):
`np.random.seed(42)` fijo en el generador (cada corrida produce **los mismos datos**
— inservible para monitoreo), kilómetros contra un modelo entrenado en millas,
`iterrows()` en el bucle de predicción, y `'stage': 'Production'` como literal.

Nombrar el límite de SQLite —un escritor, sin concurrencia, sin acceso remoto— y que
`batch.py` soporta Postgres con `DATABASE_URL`.

---

## BLOQUE 11 — La decisión y las alternativas (160-165 min)

**Archivos:** [README sección 2 y sección 6](../sesiones/s05-deployment/README.md),
[ADR 006](../docs/adr/006-serving-online-vs-batch.md). **Terminales:** 0.

Cinco minutos, dos tablas, y es el bloque que ordena todo lo anterior.

1. **La matriz batch / online / streaming** con los cinco criterios, y el caso guía en las
   tres formas. La frase que se llevan: **empieza en batch**; si el consumidor puede
   esperar al próximo corte, un job es más barato de operar y más fácil de auditar que un
   servicio.
2. **La tabla de alternativas**, con tres avisos concretos:
   - `mlflow models serve` es para demos: sin validación propia, sin `/health` con
     versión, sin métricas;
   - **BentoML 1.4 es el paso 2 natural** — empaquetado versionado y *adaptive batching*
     sin escribir HTTP a mano;
   - **MLServer: última release estable 1.7.1, de junio de 2025.** No presentarlo como
     proyecto vivo sin verificarlo antes de la cohorte.

Y decir por qué FastAPI en el curso: **porque es la capa donde se ven los conceptos.**
Escribir el contrato y el `lifespan` a mano es lo que permite entender después qué
automatiza BentoML.

---

## BLOQUE 12 — Taller (165-220 min)

**Archivo:** [`sesiones/s05-deployment/taller.md`](../sesiones/s05-deployment/taller.md).

Se entrega en clase, sobre el repositorio de proyecto de cada estudiante.

**Arranque del taller (5 min).** Leer en voz alta los **ocho criterios de aceptación** y
decir la regla: *"se verifican ejecutando, no leyendo. Si un criterio no se puede
comprobar con un comando, no cuenta."*

Recordar dos cosas que ahorran media hora de soporte:

- la colección de [`postman/`](../sesiones/s05-deployment/postman/) trae tests en cada
  request: *Run collection* verifica el contrato completo;
- `_soluciones/verificar.sh` genera la evidencia del PR. **Mostrar que existe** sin abrir
  las soluciones.

**Circulación (45 min).** Los tres problemas que vas a encontrar, en orden de frecuencia:

| Lo que verás | Qué preguntar |
|---|---|
| El modelo se copia a la imagen | "¿qué tienen que hacer para cambiar de modelo?" |
| Tests que necesitan MLflow arriba | "¿qué pasa con esto en el CI?" |
| `HEALTHCHECK` con `curl` sobre `python:slim` | "corran `command -v curl` dentro de la imagen" |

**Cierre del taller (5 min).** Pedir a dos estudiantes que proyecten su `docker compose
ps` con `(healthy)` y su `curl /health`. Ver el criterio cumplido en la máquina de otro
vale más que la rúbrica.

---

## BLOQUE 13 — Cierre (220-240 min)

**Archivos:** [README sección 7 y sección 8](../sesiones/s05-deployment/README.md).

### 13.1 Autoverificación (7 min)

Las cinco preguntas del README, en voz alta, con 30 segundos de silencio cada una. **No
las respondas**: que cada uno detecte su propio vacío. Si nadie sabe la 3 ("cambias de la
versión 7 a la 8: qué reconstruyes, qué reinicias, qué no se toca"), vuelve al bloque 8:
es la idea central.

### 13.2 Trade-offs, dicho honestamente (5 min)

Lo que se ganó hoy y lo que costó:

| Ganamos | Nos costó |
|---|---|
| contrato explícito y validado | hay que escribirlo y mantenerlo |
| carga por alias: cambiar de modelo sin rebuild | dependencia de que el registry esté arriba |
| imagen reproducible desde el lock | los builds son más lentos que un `pip install` sin lock |
| dos formas de servir | dos caminos que mantener (comparten features, eso sí) |
| todo escrito a mano en FastAPI | sin *adaptive batching*, sin versionado del servicio, sin autoescalado |

La última fila es la importante: **si su equipo tiene volumen real, el siguiente paso es
BentoML, no más FastAPI.**

### 13.3 Qué NO usar (5 min)

Recorrer la tabla del README sección 8. Detenerse en tres, y en el porqué:

- `app.run(debug=True, host="0.0.0.0")` → **ejecución remota de código**. Se ve entero en
  la sesión 6.
- `pickle.load` de un artefacto sin linaje → el acto 2 del dolor.
- `imagen:latest` como unidad de despliegue → el puente con la sesión que viene.

### 13.4 Tarea y puente a la sesión 6 (3 min)

**Tarea:** terminar el taller si quedó incompleto y abrir el PR con la salida de
`verificar.sh` pegada.

**El puente**, con una pregunta abierta que se responde la próxima sesión:

> "Hoy desplegaron a mano: build, tag, push, actualizar, verificar. La próxima vez
> cronometramos eso. Y una pregunta que hoy no tiene respuesta: **su pipeline termina en
> verde y despliega. ¿Qué garantiza eso sobre el modelo que está sirviendo?**"

Dejar la pregunta sin responder. Es el acto 2 del dolor de la sesión 6.

### Limpieza

```bash
make down
docker rm -f api-local gatitos 2>/dev/null || true
```
