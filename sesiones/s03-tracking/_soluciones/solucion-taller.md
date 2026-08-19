# Solución de referencia — Taller S03

Enunciado: [`../taller.md`](../taller.md). Aquí está resuelto **sobre el caso
guía**, que es lo que el instructor puede mostrar en pantalla. El taller se
entrega sobre el proyecto de cada estudiante, así que lo que se compara son los
criterios de aceptación, no el código.

Todos los comandos se corren desde la raíz del repositorio.

---

## 0. Preparación

```bash
make data                 # materializa las particiones y escribe metadata.json con los SHA-256
make mlflow               # tracking server en 127.0.0.1:5001 (SQLite + ./mlartifacts)
```

## 1 y 3. Entrenamiento instrumentado, con `signature` e `input_example`

```bash
uv run taxi train --modelo xgboost --registrar
```

La implementación es `taxi.models.train._loguear_entrenamiento`. Lo que registra,
y por qué cada cosa:

| Qué | Ejemplo | Para qué |
|---|---|---|
| tags de datos | `particiones_train=2023-01,2023-02,2023-03` | sin esto, dos runs no son comparables |
| tags de features | `features=PU_DO,PULocationID,...` | detecta que alguien cambió el contrato |
| `holdout_evaluado` | `no` | deja ver en la UI qué runs miraron el juez |
| params del estimador | `m_max_depth`, `m_learning_rate`, … | reproducibilidad |
| params del dato | `filas_train`, `filas_valid`, `n_features_vectorizadas` | detecta cambios de muestreo o de cardinalidad |
| métricas globales | `train_rmse`, `valid_rmse`, `valid_mae`, `valid_r2` | comparación |
| métricas por subgrupo | `rmse_hora_madrugada`, `rmse_dist_muy_larga`, … | lo que el promedio esconde |
| figuras | importancia de features, residuales | diagnóstico |
| `signature` + `input_example` | tipos ensanchados a `int64`/`float64` | contrato con los consumidores |

**Evidencia del criterio 2** (signature e `input_example`):

```bash
# el MLmodel de la version registrada
uv run python -c "
import mlflow
from taxi import config
info = mlflow.models.get_model_info(config.uri_modelo())
print(info.signature)
print('input_example:', bool(info.saved_input_example_info))
"
```

## 2. HPO con runs anidados

```bash
make hpo          # taxi train --hpo --trials 20
```

**Evidencia del criterio 4** (≥20 runs, anidados):

```bash
uv run python -c "
import mlflow
from taxi import config
mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
runs = mlflow.search_runs(experiment_names=[config.EXPERIMENTOS['hpo']])
print('runs en el experimento:', len(runs))
hijos = runs['tags.mlflow.parentRunId'].notna().sum()
print('con parent run:', hijos)
"
```

Tienen que salir al menos 22 runs: el parent del study, los 20 trials y el run
`mejor-modelo`. Si `con parent run` sale 0, los trials se crearon sueltos y falta
`nested=True`.

## 4. Promoción con tag y alias

En el taller se promueve a mano para ver el mecanismo. En el caso guía ya está
automatizado y conviene mostrar las dos formas:

```bash
# a mano, en el orden correcto: primero el tag, despues el alias
uv run python -c "
from taxi import config
from taxi.models import registry
mv = registry.ultima_version(config.MODELO_REGRESION)
registry.marcar_validacion(config.MODELO_REGRESION, mv.version, 'passed')
registry.asignar_alias(config.MODELO_REGRESION, config.ALIAS_PRODUCCION, mv.version)
"

# o con el gate, que es lo que hara el CI en S06
uv run taxi promote --dry-run     # evalua e informa, no escribe nada
```

**Evidencia del criterio 5:**

```bash
uv run python -c "
from taxi import config
from taxi.models import registry
mv = registry.version_por_alias(config.MODELO_REGRESION, config.ALIAS_PRODUCCION)
print('champion:', mv.version, '| tags:', mv.tags)
"
```

## 5. Reproducir la métrica desde `@champion`

```bash
uv run python -c "
from taxi import config
from taxi.models import evaluate, registry, train
modelo = registry.cargar_por_alias()
mv = registry.version_por_alias(config.MODELO_REGRESION, config.ALIAS_PRODUCCION)
metricas, _ = evaluate.evaluar_modelo(modelo, train.cargar_valid(), prefijo='valid_')
del_run = registry.metricas_de_version(config.MODELO_REGRESION, mv.version)['valid_rmse']
print(f'run          = {del_run!r}')
print(f'reproducido  = {metricas[\"valid_rmse\"]!r}')
print(f'diferencia   = {abs(del_run - metricas[\"valid_rmse\"]):.2e}')
"
```

**Evidencia del criterio 1.** En el caso guía la diferencia es **cero exacto**
(medido: `5.265417876913725` en los dos lados), porque el modelo, los datos y el
código de evaluación son los mismos objetos. La tolerancia declarada del taller es
por tanto `0.0`, y cualquier cosa distinta de cero es un hallazgo, no un margen.

Las tres condiciones que hacen que salga exacto, y que son lo que hay que
verificar en la entrega del estudiante:

1. El preprocesamiento va **dentro** del artefacto. Si el vectorizador se ajusta
   otra vez al evaluar, el vocabulario cambia y el número también.
2. La evaluación usa el **mismo código** (`evaluate.evaluar_modelo`), no una copia
   reescrita en el notebook.
3. Los datos son la **misma partición completa**, no una muestra. Evaluar sobre
   `df_valid.head(2000)` da otro número, y es correcto que lo dé.

## 6. Model card

```bash
make model-card           # escribe docs/model-card.md
```

**Evidencia del criterio 3:** correrlo dos veces seguidas y comprobar que el
contenido no cambia (salvo la línea de fecha de generación). El archivo lleva un
aviso `ARCHIVO GENERADO` en la cabecera precisamente para que nadie lo edite a
mano.

Si el servidor de MLflow no está levantado, el script emite la card en **modo
degradado**: sin versión y sin métricas, con un aviso en amarillo. Es
intencional —un fallback que tarda cuatro minutos en activarse no es un
fallback— y conviene mostrarlo: la card degradada **no** sirve como evidencia.

---

## Cómo se corrige el taller

| # | Criterio | Qué mirar en el PR | Falla típica |
|---|---|---|---|
| 1 | Métrica reproducida desde `@champion` | los dos números, la diferencia y la tolerancia **declarada** | evalúan sobre otra partición y presentan la diferencia como "ruido" |
| 2 | `signature` e `input_example` | el `MLmodel` de la versión | firma inferida con tipos estrechos (`int32`) |
| 3 | Model card regenerable | el comando en el `Makefile` y el archivo en el PR | card escrita a mano |
| 4 | ≥20 runs anidados | el conteo y la captura del árbol | 20 runs sin parent |
| 5 | Tag + alias | la salida del comando | alias sin tag, o tag después del alias |
| 6 | La firma rechaza una petición mala | el mensaje de error | no lo probaron |
| 7 | Runs comparables | tabla de `search_runs` con los tags | tags distintos entre runs del mismo experimento |

**Lo que hace que un taller esté bien y no solo completo:** que el estudiante
pueda explicar *por qué* el número se reproduce. Quien entiende las tres
condiciones de arriba entendió la sesión; quien copió los comandos, no.
