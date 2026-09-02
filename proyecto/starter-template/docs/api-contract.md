# Contrato de la API

> La fuente de verdad ejecutable es `src/miproyecto/api/schemas.py`, y el esquema
> OpenAPI se genera de ahí (`/openapi.json`, o `/docs` para navegarlo). Este
> documento explica lo que el esquema no puede: las decisiones y sus por qué.

## Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| `GET` | `/health` | ¿está el proceso vivo **y el modelo cargado**? ¿qué versión? |
| `POST` | `/predict` | una predicción |
| `POST` | `/predict/batch` | un lote (≤ 500 items) |
| `GET` | `/metrics` | TODO(estudiante) 31: métricas Prometheus del servicio |

`/health` mira el modelo a propósito. Un `/health` que devuelve `{"status":"ok"}`
sin mirarlo miente: el proceso está vivo y el servicio no sirve. Ese es el
healthcheck que hace que un orquestador mande tráfico a un contenedor roto.

## Contrato de entrada

TODO(estudiante) 31: tabla de campos con tipo, rango y obligatoriedad. Debe
coincidir con `schemas.py`; si divergen, el documento sobra.

Tres decisiones del contrato, con su motivo:

1. **Solo features crudas.** No se piden features derivadas. Pedírselas al cliente
   es pedirle que replique tu pipeline, y el día que cambies una derivación todos
   los clientes quedan desalineados en silencio.
2. **`extra="forbid"`.** Un campo con typo devuelve 422 en lugar de una predicción
   calculada con el default silencioso.
3. **Rangos iguales a los del contrato de datos.** Si el modelo nunca vio un valor,
   la API tampoco lo acepta.

## Códigos de respuesta

| Código | Cuándo | Qué debe hacer el cliente |
|---|---|---|
| 200 | predicción entregada | usarla |
| 422 | el request viola el contrato | corregir el request; el detalle dice qué campo |
| 503 | el modelo no está cargado | reintentar con backoff |
| 500 | error interno | reportar la referencia que devuelve el mensaje |

El 503 y el 500 se distinguen a propósito: un balanceador reintenta un 503 y no
un 500. Y el detalle de un 500 **nunca** incluye la excepción interna: eso filtra
rutas, nombres de columnas y a veces credenciales. Va al log con un id de
correlación, y al cliente le llega ese id.

## Versionado del contrato

TODO(estudiante) 31: cómo vas a introducir un cambio incompatible. Opciones:
prefijo de versión en la ruta (`/v1/predict`), campo de versión en el payload, o
período de convivencia de dos endpoints. Elige una y dilo aquí.
