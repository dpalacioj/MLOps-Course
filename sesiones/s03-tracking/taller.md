# Taller S03 — Tracking, registry y model card de tu proyecto

**Duración:** 55 min en clase. Se entrega en clase.
**Sobre:** tu propio repositorio de proyecto (no el del curso).
**Entregable:** un PR con el entrenamiento instrumentado, la evidencia de la
reproducción de la métrica y `docs/model-card.md` generada por script.

---

## Contexto

Tu entrenamiento ya es reproducible (S01) y tus datos tienen un contrato (S02).
Hoy dejas de responder "¿cuál era el modelo bueno?" de memoria.

El objetivo no es "usar MLflow". Es que, dentro de tres meses y desde otra
máquina, se pueda **cargar el modelo que está sirviendo, reproducir su métrica y
saber con qué datos se entrenó** sin preguntarle a nadie.

Todo lo que necesitas está en
[`notebooks/02-tracking-con-mlflow.ipynb`](notebooks/02-tracking-con-mlflow.ipynb)
y [`notebooks/03-hpo-y-registry.ipynb`](notebooks/03-hpo-y-registry.ipynb). La
implementación de referencia sobre el caso guía es
[`../../src/taxi/models/train.py`](../../src/taxi/models/train.py).

---

## 1. Instrumenta tu entrenamiento

En **tu** código de entrenamiento, dentro de un `mlflow.start_run()`:

- **params**: todos los hiperparámetros más la semilla y el tamaño de cada split.
- **metrics**: tu métrica técnica principal y al menos dos más. Si tienes una
  métrica de negocio (la de tu propuesta de proyecto), va aquí.
- **tags**: qué datos (particiones o rango de fechas con su hash), qué features,
  y `holdout_evaluado=no`.
- **artifacts**: al menos una figura de diagnóstico.

Nombra el experimento con la convención `s03-<proposito>` de tu proyecto. Un
nombre por problema: si acabas con tres nombres para el mismo modelo, las
comparaciones dejan de ser posibles.

## 2. Un estudio de HPO con runs anidados (≥20 trials)

Un **parent run** para el study y un **child run por trial** (`nested=True`).
En el parent: el espacio de búsqueda, el número de trials y los mejores params.

- El objetivo se mide en **validación**, nunca en el holdout.
- Semilla explícita en el sampler.
- Si tus trials son caros, acota el presupuesto (menos rondas, menos datos) y
  **explícalo en el PR**: la decisión es legítima, esconderla no.

En el caso guía esto es `taxi train --hpo --trials 20` (`make hpo`).

## 3. Signature e `input_example`

El modelo se loguea con `signature` e `input_example`, y la firma declara el tipo
**más permisivo** que el modelo acepta, no el más compacto con el que se entrenó.

Es la trampa que solo aparece al servir: si tu `input_example` lleva una columna
`int16`, la firma queda como `int32` y MLflow rechaza en producción cualquier
petición con `int64` — que es lo que manda cualquier cliente normal. El error
literal es `Can not safely convert int64 to int32`.

Demuestra que la firma sirve: manda una petición que la viole y captura el error.

## 4. Registra el mejor modelo y promuévelo con tag + alias

En este orden:

```python
client.set_model_version_tag(nombre, version, "validation_status", "passed")
client.set_registered_model_alias(nombre, "champion", version)
```

Primero el tag, después el alias. Si el proceso muere en medio, el estado
resultante ("validada pero no promovida") es el seguro.

## 5. Carga por alias y reproduce la métrica

```python
modelo = mlflow.pyfunc.load_model(f"models:/{nombre}@champion")
```

Evalúa **con el mismo código y los mismos datos** que usó el run y compara con la
métrica registrada. Declara la tolerancia que aceptas y por qué.

## 6. Genera la model card por script

Un script que lea los metadatos del registry y escriba `docs/model-card.md`, con
un target de `make`. Debe incluir: versión y run de origen, datos con su hash,
métricas globales **y por subgrupo**, limitaciones y uso no previsto.

La referencia es [`../../scripts/model_card.py`](../../scripts/model_card.py). No
la copies: adáptala a tu problema. Una model card escrita a mano queda
desactualizada en el primer reentrenamiento; una generada, no.

---

## Criterios de aceptación (medibles)

| # | Criterio | Cómo lo verificas | Evidencia que entregas |
|---|---|---|---|
| 1 | Existe un `run_id` cuya métrica **se reproduce** cargando el modelo desde `@champion` | evalúas el modelo cargado sobre la misma partición y comparas con la métrica del run | los dos números y la diferencia: `run = …`, `reproducido = …`, `|Δ| = …`, más la **tolerancia declarada** |
| 2 | El modelo registrado tiene `signature` e `input_example` | UI → Models → versión → *Source Run* → `artifacts/<name>/MLmodel` | captura del `MLmodel` con las dos secciones |
| 3 | La model card se **regenera** con un comando | `make model-card` dos veces seguidas produce el mismo archivo | el comando, su salida y el `docs/model-card.md` en el PR |
| 4 | Hay **≥20 runs** en el experimento de HPO, anidados | `len(mlflow.search_runs(experiment_names=["<tu-experimento>"]))` y la UI mostrando el árbol parent/child | el número y una captura del parent con sus hijos |
| 5 | La versión promovida tiene `validation_status=passed` y el alias `champion` | `client.get_model_version_by_alias(nombre, "champion").tags` | la salida del comando |
| 6 | La firma **rechaza** una petición mal tipada | mandas la petición inválida y capturas la excepción | el mensaje de error |
| 7 | Los runs son comparables entre sí | todos tienen los mismos tags de datos y features | `mlflow.search_runs(...)` con las columnas de tags |

### Sobre el criterio 1: la tolerancia se declara, no se supone

Un criterio de aceptación sin tolerancia no se puede verificar. Con el mismo
modelo, los mismos datos y el mismo código, la diferencia debería ser **cero
exacto** (verificado en el caso guía: `5.265417876913725` en los dos lados). Si no
lo es, di cuánto aceptas y por qué:

| Diferencia | Qué significa |
|---|---|
| `0.0` | reproducibilidad completa |
| `~1e-6` | coma flotante: orden de operaciones o número de hilos distinto |
| decimales visibles | evaluaste otros datos, otro subconjunto u otra definición de la métrica |
| enorme | estás cargando otro modelo: revisa a qué versión apunta el alias |

Las tres últimas filas no son "casi bien". Son un hallazgo que hay que explicar en
el PR.

### Sobre el criterio 4: 20 runs, no 200

Veinte trials **informados** (TPE) le ganan a doscientos aleatorios, y el
presupuesto de cómputo es parte de la decisión de ingeniería. Si tu modelo es
caro, dilo y acota; lo que no vale es entregar 200 runs sin criterio ni 3 runs
llamándolos búsqueda.

---

## Qué NO entregar

- `transition_model_version_stage`, `get_latest_versions`, URIs
  `models:/<nombre>/Production`, `archive_existing_versions`.
- `log_model(..., artifact_path=...)` — hoy es `name=`.
- `mean_squared_error(..., squared=False)` — el parámetro ya no existe.
- El modelo y el preprocesador como **dos artefactos separados**. Uno solo, con el
  preprocesamiento dentro.
- Un `try/except` alrededor del `log_model`: convierte "no se guardó el modelo" en
  un warning, y el run queda en verde sin modelo.
- Métricas del holdout en los runs de la búsqueda. El holdout es el juez del gate
  de S06 y se mira **una vez**, al final.
- La model card escrita a mano.
- El `run_id` copiado a mano en el código. Resuélvelo con `mlflow.search_runs()`.

---

## Si algo falla

| Síntoma | Causa habitual |
|---|---|
| `HTTP 403` al conectar | estás apuntando al puerto por defecto de MLflow, ocupado por AirPlay en macOS. Usa 5001 |
| `RestException: ... does not exist` al registrar | el servidor no tiene backend de base de datos: sin eso no hay registry |
| `The saved sklearn model references untrusted types` | el default de serialización es `skops`: declara `skops_trusted_types` o elige `cloudpickle` a sabiendas |
| `Can not safely convert int64 to int32` | tu `input_example` tiene tipos demasiado estrechos |
| La métrica no se reproduce | otra partición, otro subconjunto, u otra definición de la métrica |
| `database is locked` | dos procesos escribiendo en el mismo SQLite |
