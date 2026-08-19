# Ejercicio 01 — Agregar experiment tracking con MLflow

**Notebook:** [`ejercicio-01-agregar-tracking.ipynb`](ejercicio-01-agregar-tracking.ipynb)
**Duración estimada:** 25 min
**Dataset:** NYC Green Taxi, las particiones del caso guía

---

## Contexto

En [`../notebooks/01-sin-tracking.ipynb`](../notebooks/01-sin-tracking.ipynb)
entrenamos un modelo de duración de viajes **sin ningún sistema de tracking**. El
resultado fueron tres `print` y ninguna forma ordenada de comparar, reproducir o
recuperar nada.

Aquí tomas un entrenamiento que **ya funciona** y le agregas tracking. El código
base no se toca: la práctica es instrumentar, no modelar.

## Objetivo

Registrar en MLflow, para un `RandomForestRegressor` ya entrenado:

1. **Tags** — metadata para poder filtrar runs después.
2. **Parámetros** — los hiperparámetros con los que se entrenó.
3. **Métricas** — `rmse`, `mae`, `r2` sobre validación.
4. **Artefactos** — la tabla de predicciones y la gráfica de residuales.

Al terminar, todo tiene que ser visible en la UI de MLflow.

## Prerrequisitos

```bash
make data      # materializa data/processed/2023-*.parquet
make mlflow    # tracking server en http://127.0.0.1:5001
```

Comprueba que <http://127.0.0.1:5001> carga antes de seguir.

> **Sobre el puerto:** todo el curso usa 5001 porque en macOS AirPlay Receiver
> ocupa el puerto por defecto de `mlflow server` y responde un HTTP 403 que no
> explica nada. El valor vive en `taxi.config.MLFLOW_PORT`.

---

## Pasos

### Paso 1 — Ejecutar el código base (ya está completo)

Las primeras celdas cargan los datos con `taxi.models.train`, entrenan el
pipeline y calculan las métricas. No modifiques nada: ejecútalas.

Al terminar tendrás en memoria `df_train`, `df_valid`, `modelo`, `y_pred`,
`rmse`, `mae`, `r2`, y dos archivos en un directorio temporal
(`predictions.csv` y `residuals.png`).

### Paso 2 — `# TODO 1`: conectar con MLflow

```python
import mlflow

mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)  # http://127.0.0.1:5001
mlflow.set_experiment("nyc-taxi-ejercicio-01")
```

`set_tracking_uri` dice **dónde** se guarda; `set_experiment` crea el contenedor
que agrupa tus runs. Usa `config.MLFLOW_TRACKING_URI` en lugar de escribir la URL:
si el puerto cambia, cambia en un solo sitio.

### Paso 3 — `# TODO 2`: tags

Tres tags, dentro del `with mlflow.start_run(...)`:

| Tag | Valor |
|---|---|
| `problem_type` | `regression` |
| `model_family` | `random_forest` |
| `dataset` | las particiones de entrenamiento, p. ej. `2023-01,2023-02,2023-03` |

Un tag de datos que no dice **qué** datos no sirve de nada. Constrúyelo con
`",".join(p.etiqueta for p in config.PARTICIONES_TRAIN)`.

### Paso 4 — `# TODO 3`: parámetros

`n_estimators`, `max_depth`, `random_state`. Son los valores que hacen falta para
volver a producir este entrenamiento.

### Paso 5 — `# TODO 4`: métricas

`rmse`, `mae`, `r2`. Las tres ya están calculadas.

> Fíjate en que el código base usa `root_mean_squared_error`. El truco
> `mean_squared_error(..., squared=False)` **ya no funciona**: ese parámetro fue
> eliminado de scikit-learn (verificado contra 1.9.0).

### Paso 6 — `# TODO 5`: artefactos

`mlflow.log_artifact(ruta_csv)` y `mlflow.log_artifact(ruta_png)`.

Los dos archivos se escribieron en un directorio temporal a propósito: un
artefacto que vive en tu disco y no en el artifact store no es trazable, y además
ensucia el repositorio de todo el mundo.

### Paso 7 — Verificar

Ejecuta la celda de verificación (cuenta tags, params, métricas y artefactos) y
después revísalo en la UI: experimento **nyc-taxi-ejercicio-01** → tu run.

---

## Criterios de completitud

Tu ejercicio está completo cuando en la UI de MLflow puedes ver:

| Elemento | Cantidad mínima | Ejemplos |
|---|---|---|
| Tags | 3 | `problem_type`, `model_family`, `dataset` |
| Parámetros | 3 | `n_estimators`, `max_depth`, `random_state` |
| Métricas | 3 | `rmse`, `mae`, `r2` |
| Artefactos | 2 | `predictions.csv`, `residuals.png` |

Registrar **más** de lo pedido está bien y de hecho es lo que hace la solución de
referencia (añade `holdout_evaluado`, `filas_train` y `filas_valid`). Registrar
menos, no.

Y además:

| # | Criterio | Cómo lo verificas |
|---|---|---|
| 5 | El run está en el experimento `nyc-taxi-ejercicio-01` | la celda de verificación lo encuentra por nombre |
| 6 | El tag `dataset` nombra particiones concretas | `2023-01,2023-02,2023-03`, no `nyc_taxi` |
| 7 | Los tres runs del bonus 1 son comparables entre sí | mismos tags de datos, distinto `max_depth` |

---

## Bonus (opcional)

1. **Comparar.** `max_depth=20`, vuelve a ejecutar y compara los dos runs. La
   pregunta no es cuál gana, es **con qué evidencia** lo decides.
2. **Un artefacto más.** Un scatter `y_true` vs `y_pred`, con
   `mlflow.log_figure(fig, "graficos/dispersion.png")`.
3. **`mlflow.autolog()`.** Sustituye tu logging manual. ¿Qué registra que tú no
   registraste? Y sobre todo: **¿qué no registra?** (mira tus tags de datos).
4. **Loguear el modelo.** Con `signature` e `input_example`. Con este pipeline
   necesitarás `skops_trusted_types=["taxi.models.train.ADiccionarios"]`;
   descubre por qué leyendo el error que aparece si no lo pasas.

---

## Qué NO hacer en este ejercicio

- `mlflow.log_metric("rmse", np.sqrt(mean_squared_error(y, p)))` — usa
  `root_mean_squared_error`.
- Escribir `predictions.csv` en la carpeta del repositorio.
- Loguear el modelo con `artifact_path=` (deprecado; hoy es `name=`).
- Poner el modelo en el registry: eso es el ejercicio 02, y **registrar no es
  promover**.
