# Ejercicio guiado: orquestar el pipeline de clasificación

## Cómo está planteado

El enunciado es un **archivo Python con los cuerpos de función vacíos**, `TODO`
numerados y criterios de aceptación verificables. Se completa y se ejecuta.

Dos cosas que este formato evita a propósito. Un "ejercicio guiado" hecho de
celdas `%%writefile` con el código ya escrito no exige resolver nada: ejecutarlas
en orden es todo el trabajo. Y `%%writefile` escribe rutas relativas al directorio
de trabajo del kernel, así que ejecutado desde la carpeta equivocada **sobreescribe
archivos del curso**. Aquí no hay nada que sobreescribir.

## El problema

El mismo dataset y las mismas features, pero el target es binario:
`viaje_largo = duration > 30 min` (`taxi.features.contract.TARGET_CLASIFICACION`).
El modelo registrado se llama `taxi.config.MODELO_CLASIFICACION`.

Cambiar de regresión a clasificación cambia tres cosas, y las tres son el punto
del ejercicio:

1. **La métrica.** El accuracy es engañoso con clases desbalanceadas: si el 85 %
   de los viajes no son largos, predecir siempre "no" da 85 % de accuracy y cero
   valor. Se usan `f1`, `roc_auc` y `average_precision`.
2. **El umbral.** Un clasificador devuelve una probabilidad; el umbral es una
   decisión de negocio, no un hiperparámetro. `0.5` es un default, no una
   respuesta.
3. **El artifact.** La tabla de métricas por umbral es lo que permite discutir esa
   decisión con quien la tiene que tomar.

## Qué entregar

`ejercicio_flow.py` completo, y en la UI de Prefect un flow run en estado
`Completed` con sus artifacts.

## Criterios de aceptación

| # | Criterio | Cómo se verifica |
|---|---|---|
| 1 | El flow corre end-to-end sin intervención | `uv run python ejercicio_flow.py` termina en `Completed` |
| 2 | La task de datos tiene `retries` **con backoff creciente** | `retry_delay_seconds` es una lista ascendente |
| 3 | El contrato de datos se valida antes de entrenar | una partición truncada hace fallar el flow |
| 4 | Hay una tabla de métricas por umbral, con al menos 5 umbrales | artifact `metricas-por-umbral` visible en el run |
| 5 | Se registra el candidato con alias `candidate` | `mlflow` muestra la versión con ese alias |
| 6 | **Nada** promueve a `champion` | `get_model_version_by_alias(..., "champion")` no cambia tras correr el flow |
| 7 | El flow devuelve un dict con `run_id`, `model_version` y métricas | se ve en el valor de retorno y en el log |

## Pistas

- Reutiliza `taxi.flows.training.preparar` tal cual: preparar los datos es
  idéntico en los dos problemas, y duplicarlo sería repetir el error del repo
  anterior.
- `taxi.data.loaders.preparar_particion` ya deja la columna `viaje_largo`.
- Para el modelo: `sklearn.linear_model.LogisticRegression` alcanza y entrena en
  segundos. Envuélvelo igual que `taxi.models.train` envuelve los suyos
  (`ADiccionarios` → `DictVectorizer` → estimador) o usa `_envolver` si te sirve.
- El umbral se aplica sobre `predict_proba(...)[:, 1]`.
