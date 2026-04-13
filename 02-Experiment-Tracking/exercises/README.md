# Ejercicio 01: Agregar Experiment Tracking con MLflow

## Contexto

En el notebook `01_first_steps_without_tracking.ipynb` vimos como entrenar un modelo
de prediccion de duracion de viajes de taxi **sin ningun sistema de tracking**.
El resultado fue que no teniamos forma ordenada de guardar parametros, metricas
ni artefactos.

En este ejercicio vas a tomar codigo de entrenamiento que **ya funciona** y agregarle
tracking con MLflow, paso a paso.

---

## Objetivo

Dado un notebook con un modelo `RandomForestRegressor` ya entrenado y evaluado,
tu tarea es **agregar MLflow tracking** para registrar:

1. **Tags** - metadata del experimento (tipo de problema, familia del modelo, dataset)
2. **Parametros** - hiperparametros del modelo (`n_estimators`, `max_depth`, `random_state`)
3. **Metricas** - resultados de evaluacion (`rmse`, `mae`, `r2`)
4. **Artefactos** - archivos generados (tabla de predicciones CSV, grafica de residuales PNG)

Al finalizar, deberas poder ver todo registrado en la **MLflow UI**.

---

## Prerequisitos

Antes de comenzar, asegurate de:

1. **Haber ejecutado la preparacion de datos** (`notebooks/00_data_preparation.ipynb`)
   para que existan los archivos en `data/processed/`.

2. **Tener el servidor MLflow corriendo.** Abre una terminal aparte y ejecuta:

   ```bash
   uv run mlflow server \
       --backend-store-uri sqlite:///mlflow.db \
       --default-artifact-root ./mlruns \
       --host 127.0.0.1 \
       --port 5000
   ```

3. **Verificar** que puedes acceder a `http://127.0.0.1:5000` en tu navegador.

---

## Instrucciones paso a paso

Abre el notebook `ejercicio_01_agregar_tracking.ipynb` y sigue estas instrucciones.

### Paso 1: Ejecutar el codigo base (ya esta completo)

Las primeras celdas cargan los datos y entrenan el modelo. **No necesitas modificar nada aqui**,
solo ejecutalas para tener el modelo entrenado y las metricas calculadas.

Despues de ejecutar, deberias tener en memoria:
- `X_train`, `y_train`, `X_val`, `y_val` (datos)
- `rf` (modelo entrenado)
- `y_pred` (predicciones)
- `rmse`, `mae`, `r2` (metricas calculadas)

### Paso 2: Configurar la conexion a MLflow

Busca la celda marcada con `# TODO 1` y completa:

```python
import mlflow

# Conectar al servidor MLflow
mlflow.set_tracking_uri("http://127.0.0.1:5000")

# Crear/seleccionar un experimento
mlflow.set_experiment("nyc-taxi-ejercicio-01")
```

**Que hace esto:**
- `set_tracking_uri` le dice a MLflow **donde** guardar los datos (nuestro servidor local).
- `set_experiment` crea un contenedor con nombre para agrupar tus runs.

### Paso 3: Registrar tags

Busca `# TODO 2` y agrega tags dentro del bloque `with mlflow.start_run()`:

```python
mlflow.set_tag("problem_type", "regression")
mlflow.set_tag("model_family", "random_forest")
mlflow.set_tag("dataset", "nyc_green_taxi_2023_01_02")
```

**Que son los tags:** Etiquetas de texto libre para organizar y filtrar runs.
No afectan el entrenamiento, pero ayudan a encontrar runs despues.

### Paso 4: Registrar parametros

Busca `# TODO 3` y registra los hiperparametros del modelo:

```python
mlflow.log_param("n_estimators", n_estimators)
mlflow.log_param("max_depth", max_depth)
mlflow.log_param("random_state", random_state)
```

**Que son los parametros:** Los valores de configuracion que usaste para entrenar.
Si manana quieres reproducir este entrenamiento exacto, necesitas estos valores.

### Paso 5: Registrar metricas

Busca `# TODO 4` y registra las metricas de evaluacion:

```python
mlflow.log_metric("rmse", rmse)
mlflow.log_metric("mae", mae)
mlflow.log_metric("r2", r2)
```

**Que son las metricas:** Los resultados numericos que miden que tan bueno es tu modelo.
MLflow te permite comparar metricas entre multiples runs.

### Paso 6: Registrar artefactos

Busca `# TODO 5` y registra los archivos generados:

```python
# a) Tabla de predicciones
mlflow.log_artifact("predictions.csv")

# b) Grafica de residuales
mlflow.log_artifact("residuals.png")
```

**Que son los artefactos:** Cualquier archivo que tu run genera. Pueden ser CSVs,
graficas PNG, modelos serializados, etc. MLflow los guarda asociados al run.

### Paso 7: Verificar en la UI

1. Abre `http://127.0.0.1:5000` en tu navegador.
2. Busca el experimento **"nyc-taxi-ejercicio-01"** en la barra lateral.
3. Haz clic en tu run y verifica que aparezcan:
   - Los 3 tags en la seccion "Tags"
   - Los 3 parametros en la seccion "Parameters"
   - Las 3 metricas en la seccion "Metrics"
   - Los 2 artefactos en la seccion "Artifacts" (puedes descargarlos)

---

## Criterios de completitud

Tu ejercicio esta completo cuando en la MLflow UI puedes ver:

| Elemento    | Cantidad | Ejemplos                          |
|-------------|----------|-----------------------------------|
| Tags        | 3        | problem_type, model_family, dataset |
| Parametros  | 3        | n_estimators, max_depth, random_state |
| Metricas    | 3        | rmse, mae, r2                     |
| Artefactos  | 2        | predictions.csv, residuals.png    |

---

## Bonus (opcional)

Si terminaste rapido, intenta:

1. **Cambiar hiperparametros** (por ejemplo `max_depth=15`, `n_estimators=200`)
   y ejecutar de nuevo. Compara los dos runs en la UI.
2. **Agregar un artefacto extra**: genera una grafica de scatter `y_true vs y_pred`
   y registrala con `mlflow.log_artifact(...)`.
3. **Usar `mlflow.autolog()`** en lugar de logging manual. Que registra automaticamente?
   Que NO registra?

---

## Archivos de referencia

Si te atascas, puedes consultar (pero intenta primero por tu cuenta):

- `notebooks/02_experiment_tracking_intro.ipynb` - Ejemplo completo con MLflow
- `scripts/train_with_basic_mlflow.py` - Version script con logging basico
