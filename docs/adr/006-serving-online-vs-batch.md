# ADR 006 — Servir el caso guía en línea y en batch, y no en streaming

- **Estado:** aceptada
- **Fecha:** 2026-08
- **Alcance:** sesión 5, `src/taxi/api/`, `src/taxi/flows/batch.py`, `Dockerfile`
- **Decisores:** equipo docente del curso de MLOps

## Contexto

La sesión de deployment del repositorio anterior enseñaba tres cosas al mismo tiempo,
sin distinguirlas: cómo funciona Docker, cómo se escribe una API y cómo se sirve un
modelo. El resultado eran 2.806 líneas de markdown para cuatro horas de clase, tres
implementaciones distintas del mismo servicio y ninguna discusión sobre **cuándo
conviene cada forma de servir**.

Peor: la forma se elegía por defecto. Había una API porque el material era sobre APIs, y
un batch porque había una carpeta llamada `batch-deploy`. Nada en el material ayudaba a
un estudiante a decidir qué necesitaba su proyecto.

Hallazgos concretos de la auditoría que esta decisión tiene que resolver:

1. **El artefacto se copiaba entre módulos con `shutil.copytree`.** Dos scripts
   `copy_model.py` en cadena; uno apuntaba a `03-Orchestration/Prefect-pipelines`, un
   directorio que ya no existe. El modelo quedaba versionado por el sistema de archivos
   y cambiar de modelo exigía reconstruir la imagen.
2. **El batch generaba datos sintéticos con `np.random.seed(42)` fijo**, así que cada
   corrida horaria producía **los mismos datos** — inservible para monitoreo. Y
   documentaba kilómetros mientras alimentaba un modelo entrenado en millas.
3. **El `Dockerfile` pinneaba a mano** `mlflow==2.17.2`, `xgboost==2.1.2`,
   `scikit-learn==1.5.2` mientras copiaba (y luego ignoraba) el `pyproject.toml`. El
   artefacto se había entrenado con otras versiones: `InconsistentVersionWarning` en cada
   arranque, y un modelo validado en CI sirviendo predicciones potencialmente distintas.
4. **La fila persistida del batch llevaba `'stage': 'Production'`** como literal, un
   valor que miente en cuanto el modelo cambia de estado y que además viene del
   vocabulario de stages, deprecado en MLflow (ver [ADR 002](002-aliases-en-vez-de-stages.md)).

## Decisión

**El caso guía se sirve de dos formas —online y batch— desde un solo código, y la
elección entre ellas se enseña como una decisión con criterios explícitos. Streaming se
nombra y no se implementa.**

### 1. Las dos formas, con un solo camino de features

| Forma | Entrada | Implementación | Consumidor del caso guía |
|---|---|---|---|
| **Online** | un request HTTP | `src/taxi/api/` (FastAPI + uvicorn) | la app que estima el tiempo antes de aceptar el viaje |
| **Batch** | una partición mensual | `src/taxi/flows/batch.py` (Prefect + SQLite/Postgres) | el reporte de planeación de flota |

Las dos reusan `taxi.features.contract` para construir features. **No hay dos
implementaciones de la misma derivación**, y esa es la decisión más importante de la
lista: el training/serving skew casi nunca viene de un bug en el modelo, viene de dos
implementaciones de la misma feature que se desincronizan.

### 2. El modelo se resuelve del registry por alias, siempre

```python
mlflow.pyfunc.load_model("models:/nyc-taxi-duration@champion")
```

Ni `copytree`, ni `COPY model/`, ni un `run_id` en el código. La imagen contiene el
código que sabe pedir el modelo; el modelo lo resuelve el registry en el arranque.

### 3. Streaming se enseña como criterio, no como implementación

Se incluye en la matriz de decisión con sus cinco criterios y se dice explícitamente qué
haría falta (broker, estado en ventana, manejo de orden y reprocesamiento) y por qué no
se implementa: la parte difícil no es llamar al modelo.

### 4. Los criterios de la matriz de decisión

Declarados para que la elección se pueda discutir y no dependa de la moda:

| Criterio | Pregunta que responde |
|---|---|
| Latencia tolerada | ¿hay alguien esperando una respuesta? |
| Volumen por ejecución | ¿una fila o millones? |
| Frescura de features | ¿la del último corte, la del request o la del evento? |
| Costo | ¿se paga por tener el servicio disponible o solo por ejecutar? |
| Complejidad operativa | ¿qué hay que vigilar, y qué pasa cuando falla? |

Y una regla práctica por defecto: **empezar en batch**. Si el consumidor puede esperar
al próximo corte, un job programado es más barato de operar y más fácil de auditar.

### 5. Las versiones se resuelven una vez, en `uv.lock`

Ningún pin escrito a mano en un `Dockerfile` para las librerías que **deserializan el
modelo**. Local, CI, entrenamiento y serving instalan del mismo lockfile.

Excepción documentada, no escondida: la etapa `mlflow-server` del `Dockerfile` instala
`psycopg2-binary` y `boto3` con *floor pins*. Son drivers de un servicio de
**infraestructura** que no toca el pickle del modelo, y no están en `uv.lock` porque el
proyecto no los necesita. La deuda está anotada en el propio archivo; la solución limpia
a futuro es un extra en `pyproject.toml`.

### 6. La unidad de despliegue es el digest

`imagen@sha256:…`, no `imagen:latest`. Se introduce en la sesión 5 y se usa en la 6.

## Alternativas consideradas

### A. Solo online

Descartada. Es la elección por defecto de la mayoría de los cursos y refuerza el error
que esta sesión quiere corregir: creer que "servir un modelo" es sinónimo de "levantar
una API". Además, la trazabilidad por fila —una predicción, una versión de modelo, un
timestamp— es más natural de enseñar y de consultar en batch, y es la base del módulo de
monitoreo.

### B. Solo batch

Descartada. Se perderían el contrato de entrada como frontera de confianza, los endpoints
operativos (`/health`, `/metrics`), el manejo de errores que no filtra internals y la
distinción liveness/readiness. Son cuatro conceptos que solo aparecen cuando hay un
servicio expuesto.

### C. Streaming también, con Kafka en Compose

Descartada por costo/beneficio en cuatro horas. Levantar un broker y explicar *offsets*,
particiones, orden y estado en ventana consume el tiempo de los conceptos de
deployment, y el aporte marginal sobre "el modelo se carga por alias y se llama" es
bajo. Se nombra en la matriz y se dan los puntos de entrada.

### D. Empaquetar con BentoML en lugar de escribir la API

Descartada **para la sesión**, recomendada como paso siguiente. BentoML 1.4 resuelve el
empaquetado versionado y el *adaptive batching* sin escribir HTTP a mano, y es la
elección correcta para un equipo con volumen real. Pero escribir el contrato, el
`lifespan`, la carga por alias y el manejo de errores es lo que permite entender después
**qué** está automatizando BentoML. Con un framework que genera la API, la sesión
enseñaría a usar una herramienta en lugar de a diseñar un servicio.

### E. `mlflow models serve` como servicio del curso

Descartada. Es la ruta de un comando, y la propia documentación de MLflow la enmarca como
adecuada para *"lightweight applications or testing your model locally"*. No hay
validación de entrada propia, ni `/health` con la versión del modelo, ni métricas, ni
control del manejo de errores. Se usa en clase para la demo de treinta segundos y se dice
qué le falta.

### F. KServe o Ray Serve

Descartadas por requisito de infraestructura: exigen Kubernetes o un clúster de Ray.
Montar cualquiera de los dos para servir un modelo en un curso es una decisión de
infraestructura disfrazada de decisión de serving. Se comparan en la tabla de
alternativas de la sesión, con la fecha de evaluación y el enlace a su documentación.

## Consecuencias

### Positivas

- **Una sola definición de features** entre entrenamiento, API y batch. El skew deja de
  ser posible por construcción, no por disciplina.
- **Cambiar de modelo es mover un alias y reiniciar el proceso.** Sin rebuild, sin
  redeploy de imagen. El rollback es la misma operación al revés.
- **Cada predicción es atribuible** a una versión concreta: en la respuesta HTTP
  (`model_version`) y en la fila de la base (`model_version`, `model_alias`, `batch_id`).
- **El material cabe en cuatro horas.** Las 2.806 líneas anteriores quedaron en
  `referencia/` como catálogo opcional, con la advertencia de que describen la API
  anterior.
- **La imagen es verificable en CI sin registry**, gracias al modo degradado
  (`TAXI_MODELO_URI=ninguno`). El job `imagen` comprueba no-root y `/health` en un runner
  limpio.

### Negativas, y asumidas

- **Escribir la API a mano deja trabajo pendiente**: no hay *adaptive batching*, ni
  versionado del servicio como artefacto, ni autoescalado. En un equipo con volumen real
  eso es un costo, y la respuesta correcta es BentoML o KServe.
- **Dos formas de servir es más material que una.** Se compensa porque comparten el
  contrato de features y el registry; lo que se duplica es el ejercicio, no el código.
- **El modo degradado puede confundir.** Un `/health` en 200 con `model_loaded: false`
  parece un éxito y no lo es. Se mitiga con la distinción explícita liveness/readiness en
  el material y en el docstring de `SaludResponse`.
- **Streaming queda como un hueco declarado.** Un estudiante cuyo proyecto lo necesite
  tendrá que aprenderlo fuera. Se prefiere un hueco nombrado a una implementación de
  juguete que enseñe que streaming es fácil.
- **SQLite como destino del batch tiene límites reales**: un escritor a la vez, sin
  concurrencia, sin acceso remoto. Alcanza para clase; en cuanto el batch corre en otra
  máquina que el consumidor, el destino es Postgres. `batch.py` ya lo soporta con
  `DATABASE_URL`.

## Verificación

- `tests/api/` — 4 archivos, sin MLflow y sin red (doble de prueba inyectado por
  `app.dependency_overrides`).
- Job `imagen` de `.github/workflows/ci.yml` — la imagen no corre como root y responde
  `/health`.
- `sesiones/s05-deployment/_soluciones/verificar.sh` — genera la evidencia de los ocho
  criterios del taller.
- `nightly-smoke.yml` — corre el caso guía completo cada noche en un runner limpio.

## Referencias

- Material de la sesión: [`sesiones/s05-deployment/README.md`](../../sesiones/s05-deployment/README.md)
- Contrato de la API: [`sesiones/s05-deployment/api-contract.md`](../../sesiones/s05-deployment/api-contract.md)
- [ADR 001 — un solo caso guía con particiones fijas](001-caso-guia-y-particiones.md)
- [ADR 002 — aliases en vez de stages](002-aliases-en-vez-de-stages.md)
- [ADR 007 — el gate de promoción](007-gate-de-promocion.md)
- Contraejemplo de seguridad: [`sesiones/s06-cloud-cicd/_contraejemplo-insegure-aws/`](../../sesiones/s06-cloud-cicd/_contraejemplo-insegure-aws/)
