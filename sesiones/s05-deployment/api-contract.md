# Contrato de la API de inferencia

Referencia de trabajo para el taller y para cualquiera que consuma el servicio.
La **fuente de verdad** es [`src/taxi/api/schemas.py`](../../src/taxi/api/schemas.py):
FastAPI deriva de esas clases tanto la validación en runtime como el esquema
OpenAPI. Si este documento y el código discrepan, el código tiene razón — y hay que
corregir este archivo.

Esquema vivo: <http://127.0.0.1:8000/docs> · <http://127.0.0.1:8000/openapi.json>

**Base URL local:** `http://127.0.0.1:8000`

---

## Resumen

| Método | Ruta | Autenticación | Códigos posibles |
|---|---|---|---|
| `GET` | `/` | — | 307 o 308 (redirige a `/docs`) |
| `GET` | `/health` | — | 200 |
| `GET` | `/modelo` | — | 200, 503 |
| `POST` | `/predict` | — | 200, 422, 500, 503 |
| `POST` | `/predict/batch` | — | 200, 422, 500, 503 |
| `GET` | `/metrics` | — | 200 (formato de exposición Prometheus) |

**Sin autenticación, a propósito y con una advertencia.** El servicio del curso
corre en `localhost` y en un laboratorio efímero. Un servicio real expuesto a
internet necesita al menos una API key por cliente o un token verificado en un
*gateway*, más *rate limiting* — y ambos son responsabilidad de la capa de entrada,
no de este código. Lo que **no** es aceptable es lo que hace el contraejemplo de la
sesión 6: publicar el puerto a `0.0.0.0/0` sin ninguna de las dos cosas.

---

## `GET /health`

*Liveness check.* Responde **200 mientras el proceso esté vivo**, incluso sin
modelo cargado.

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_name": "nyc-taxi-duration",
  "model_version": "7",
  "model_uri": "models:/nyc-taxi-duration@champion",
  "version_api": "1.0.0"
}
```

En modo degradado (`TAXI_MODELO_URI=ninguno`, o la carga falló) sigue siendo 200:

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

| Campo | Para qué sirve |
|---|---|
| `status` | legible para una persona: `ok` o `degradado` |
| `model_loaded` | **es el campo del readiness check**: si es `false`, no mandes tráfico |
| `model_version` | qué artefacto está respondiendo *ahora* |
| `model_uri` | con qué URI se pidió. Se expone porque el error más común en clase es apuntar al registry equivocado |
| `version_api` | versión del paquete que sirve, leída de la metadata de la distribución |

**Por qué 200 y no 503 sin modelo:** si devolviera 503, el orquestador reiniciaría
el contenedor en bucle y nadie podría leer el diagnóstico. *Liveness* responde
"¿reinicio este proceso?"; *readiness* responde "¿le mando tráfico?". Son dos
preguntas y aquí se separan.

---

## `GET /modelo`

Metadatos para una **persona**, no para el orquestador.

```json
{
  "model_name": "nyc-taxi-duration",
  "model_version": "7",
  "model_uri": "models:/nyc-taxi-duration@champion",
  "features": ["PU_DO", "PULocationID", "DOLocationID", "trip_distance", "hora_pickup", "dia_semana_pickup"],
  "umbral_viaje_largo_min": 30.0
}
```

Exponer `features` evita la conversación más repetida de un equipo de ML: "¿el
modelo usa la hora del pickup o no?". Devuelve **503** con el envelope de error si
no hay modelo cargado.

---

## `POST /predict`

### Request

```json
{
  "PULocationID": 43,
  "DOLocationID": 238,
  "trip_distance": 2.4,
  "pickup_datetime": "2023-05-15T08:30:00"
}
```

| Campo | Tipo | Obligatorio | Restricción | Nota |
|---|---|---|---|---|
| `PULocationID` | entero | sí | 1 a 265 | *taxi zone* de la NYC TLC |
| `DOLocationID` | entero | sí | 1 a 265 | idem |
| `trip_distance` | número | sí | 0 a 100 | **MILLAS**, no kilómetros |
| `pickup_datetime` | fecha-hora | no | sin zona horaria, ≤ 30 días en el futuro | hora local de Nueva York |

Reglas del contrato que sorprenden y son deliberadas:

- **Campos desconocidos se rechazan** (`extra="forbid"`). `PULocationId` con `i`
  minúscula da 422, no una predicción con un default silencioso.
- **No se piden features derivadas.** `PU_DO`, `hora_pickup` y `dia_semana_pickup`
  las calcula el servidor reusando el mismo contrato de features que el
  entrenamiento. Pedírselas al cliente es pedirle que replique el pipeline: en el
  primer cambio de una derivación, todos los clientes quedan desalineados.
- **`pickup_datetime` con offset se rechaza en lugar de convertirse.** Un cliente
  que manda `2023-05-15T08:30:00Z` cree hablar de las 08:30 y el modelo entendería
  04:30. Un 422 hoy es más barato que un reporte de drift el mes que viene.
- **Si se omite `pickup_datetime` se usa la hora actual en Nueva York.** Es una
  comodidad para `/docs` y para el caso "pídeme un taxi ahora", con un costo real:
  la predicción deja de ser reproducible, porque la hora es una feature. **En
  producción, mándalo siempre explícito.**

### Response 200

```json
{
  "duration_min": 12.47,
  "viaje_largo": false,
  "model_name": "nyc-taxi-duration",
  "model_version": "7",
  "latencia_ms": 3.412
}
```

| Campo | Nota |
|---|---|
| `duration_min` | duración predicha, en minutos |
| `viaje_largo` | `duration_min >= 30`. El umbral vive en `config.py`: es una decisión de negocio, no de la API |
| `model_version` | **el campo que hace auditable la predicción.** Sin él, una predicción mala es imposible de atribuir tres semanas después |
| `latencia_ms` | latencia de la llamada de inferencia, no del request HTTP completo |

---

## `POST /predict/batch`

Entre 1 y **500** viajes en una sola llamada de inferencia.

```json
{
  "viajes": [
    {"PULocationID": 43,  "DOLocationID": 238, "trip_distance": 2.4, "pickup_datetime": "2023-05-15T08:30:00"},
    {"PULocationID": 161, "DOLocationID": 236, "trip_distance": 5.2, "pickup_datetime": "2023-05-15T09:00:00"}
  ]
}
```

> La clave del lote es `viajes`. Si mandas `trips`, `data` o cualquier otro nombre,
> el 422 que recibes dice `Field required` para `viajes` y `Extra inputs are not
> permitted` para la clave que mandaste: es `extra="forbid"` haciendo su trabajo.

### Response 200

```json
{
  "predicciones": [
    {"duration_min": 12.47, "viaje_largo": false, "model_name": "nyc-taxi-duration", "model_version": "7", "latencia_ms": 4.108},
    {"duration_min": 21.03, "viaje_largo": false, "model_name": "nyc-taxi-duration", "model_version": "7", "latencia_ms": 4.108}
  ],
  "total": 2,
  "model_name": "nyc-taxi-duration",
  "model_version": "7",
  "latencia_ms": 4.108
}
```

`latencia_ms` es la del **lote completo**, y es el mismo valor en cada elemento a
propósito: la inferencia está vectorizada y no existe un costo por elemento medible
por separado. Repartirlo entre N daría un número inventado.

Por qué existe el endpoint: amortiza el costo fijo por llamada (parseo,
construcción del DataFrame, *overhead* de `predict`) sobre N viajes. En inferencia
sklearn ese costo fijo suele dominar, así que un lote de 100 no tarda 100 veces más
que uno de 1. **Mídelo** en el taller con `time` y dos requests.

Por qué el tope de 500 vive en el schema y no en el endpoint: un límite declarado
aparece en OpenAPI y el cliente lo ve antes de escribir el request. Y existe por dos
razones operativas: acota la memoria por request (un lote sin límite es un vector de
DoS) y acota la latencia de cola, porque un lote gigante bloquea al worker.

---

## `GET /metrics`

Formato de exposición de Prometheus: texto plano, una métrica por línea. **No
aparece en el esquema OpenAPI** a propósito (`include_in_schema=False`): lo consume
Prometheus, no un cliente de la API.

| Métrica | Tipo | Labels | Qué responde |
|---|---|---|---|
| `taxi_predicciones_total` | counter | `model_version`, `clase` | throughput y la proporción largo/corto (prediction drift observable sin labels) |
| `taxi_inferencia_duracion_segundos` | histogram | `model_version` | latencia de inferencia; permite p95 por versión |
| `taxi_errores_total` | counter | `tipo` | `validacion`, `modelo_no_disponible`, `inferencia`, `interno` |
| `taxi_modelo_info` | gauge | `model_name`, `model_version`, `model_uri` | *info metric*: el valor siempre es 1, la información está en los labels |

El label `model_version` es el puente con la sesión 6: es lo que permite comparar
latencia y distribución de predicciones **antes y después de una promoción**. Sin
ese label, un cambio de modelo es invisible en Grafana.

Se explota a fondo en la sesión 7.

---

## Errores

Un solo envelope para toda la API:

```json
{
  "error": "El request no cumple el contrato de la API.",
  "id_correlacion": null,
  "detalle_validacion": [
    {
      "type": "greater_than_equal",
      "loc": ["body", "PULocationID"],
      "msg": "Input should be greater than or equal to 1",
      "input": -5
    }
  ]
}
```

| Código | Cuándo | `id_correlacion` | `detalle_validacion` |
|---|---|---|---|
| **422** | el request no cumple el contrato | no | **sí**: describe el request del cliente |
| **500** | el modelo falló al predecir, o desalineamiento de filas | sí | no |
| **503** | no hay modelo cargado | no | no |

La regla: **al cliente va un mensaje estable; el detalle técnico va al log del
servidor** con el mismo `id_correlacion`. Con ese id, quien opera el servicio
encuentra la traza en segundos.

El 422 es la única excepción y tiene razón de ser: ese detalle describe lo que el
cliente mandó, no el interior del servidor. Es información que necesita para
corregirse.

El atajo tentador es `HTTPException(detail=f"Error: {str(e)}")`: una línea, y el
cliente "ve qué pasó". Lo que ve son rutas del filesystem, cadenas de conexión con
credenciales, nombres de columnas y trazas del ORM, y lo ve cualquiera que sepa
mandar un request malformado. El test `test_error_interno_no_filtra_el_mensaje_de_la_excepcion`
en [`tests/api/test_prediccion.py`](../../tests/api/test_prediccion.py) es el que
impide que ese atajo vuelva a entrar.

---

## Variables de entorno del servicio

| Variable | Default | Para qué |
|---|---|---|
| `TAXI_MODELO_URI` | `models:/nyc-taxi-duration@champion` | qué modelo servir. `ninguno` arranca en modo degradado (así verifica el CI la imagen sin registry) |
| `MLFLOW_TRACKING_URI` | `http://127.0.0.1:5001` | dónde está el registry |
| `TAXI_CORS_ORIGENES` | `http://localhost:3000,http://127.0.0.1:3000` | orígenes permitidos, separados por coma. **No pongas `*`** |
| `TAXI_LOG_LEVEL` | `INFO` | nivel de log |
| `TAXI_API_HOST` / `TAXI_API_PORT` | `127.0.0.1` / `8000` | solo para `python -m taxi.api.main` |

Sobre `TAXI_CORS_ORIGENES=*`: el servicio **avisa y desactiva las credenciales**,
porque `Access-Control-Allow-Origin: *` junto a `Allow-Credentials: true` es una
combinación inválida que el navegador rechaza. Declara los orígenes.

---

## Ejemplos ejecutables

```bash
# Salud
curl -s http://127.0.0.1:8000/health | jq

# Predicción individual
curl -sX POST http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"PULocationID": 43, "DOLocationID": 238, "trip_distance": 2.4,
       "pickup_datetime": "2023-05-15T08:30:00"}' | jq

# Lote
curl -sX POST http://127.0.0.1:8000/predict/batch \
  -H 'Content-Type: application/json' \
  -d '{"viajes": [
        {"PULocationID": 43,  "DOLocationID": 238, "trip_distance": 2.4},
        {"PULocationID": 161, "DOLocationID": 236, "trip_distance": 5.2}]}' | jq

# 422 esperado: zona fuera de rango
curl -sX POST http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"PULocationID": 9999, "DOLocationID": 238, "trip_distance": 2.4}' | jq

# 422 esperado: campo desconocido
curl -sX POST http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"PULocationId": 43, "DOLocationID": 238, "trip_distance": 2.4}' | jq

# Métricas de una versión concreta
curl -s http://127.0.0.1:8000/metrics | grep taxi_
```

En Postman: importa los dos archivos de [`postman/`](postman/) y selecciona el
entorno *NYC Taxi API — Local*.

Los tests que verifican este contrato están en
[`tests/api/`](../../tests/api/) y corren **sin MLflow y sin red**: el modelo se
sustituye por un doble de prueba a través de la costura `cargar_pyfunc` y el
cargador se inyecta con `app.dependency_overrides`.
