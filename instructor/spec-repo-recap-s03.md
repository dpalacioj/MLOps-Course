# Spec — Repositorio de recapitulación (sesiones 1 a 3)

> **Cómo usar este documento:** copia todo lo que hay debajo de la línea horizontal
> y pégalo como primer prompt de Claude Code dentro de un repositorio vacío (recién
> creado con `git init`). El documento está escrito como instrucciones directas
> para el agente que va a construir el proyecto.
>
> **Nombre sugerido del repositorio:** `mlops-recap-lab`
> (alternativas: `churn-mlops-lab` si quieres que el nombre delate el caso,
> o `mlops-essentials-lab` si prefieres algo más corporativo).

---

# Construye `mlops-recap-lab`: un mini-proyecto de recapitulación de MLOps

## Contexto y propósito

Soy instructor de un curso de MLOps para profesionales que **no** son ingenieros de
software (vienen de finanzas, biología, analítica, etc.). Llevamos tres sesiones:

1. **Reproducibilidad**: entornos con `uv`, `pyproject.toml` vs `uv.lock`,
   Makefile como interfaz única de comandos, código en paquete en vez de notebook.
2. **Datos**: limpieza, tipos de columnas, contratos de datos (aquí solo tocaremos
   la limpieza básica).
3. **Tracking**: MLflow con params, métricas, tags, artifacts, `signature`,
   `input_example`, y Model Registry gobernado con **aliases y tags, nunca stages**.

Los estudiantes están **abrumados**: demasiadas piezas nuevas a la vez. Este
repositorio es un ejercicio de recapitulación donde todas las piezas aparecen
**una sola vez, en su versión más simple posible**, conectadas de punta a punta.
La regla de diseño número uno es: **si dudas entre agregar algo o no, no lo
agregues.** Nada de Docker, nada de CI, nada de tests, nada de type hints
exhaustivos, nada de configuración avanzada. Un solo camino feliz.

Todo el contenido visible para el estudiante (README, notebooks, comentarios,
mensajes de los scripts) va **en español**, y **las columnas del dataset también**:
el estudiante debe leer sus datos sin traducir. Los nombres de código (paquete,
módulos, funciones, variables) van en inglés, que es la convención que ven en el
curso.

No toques la configuración de firma de commits: la máquina donde se creará el
repo ya firma con GPG por configuración global de git.

## El caso: predicción de churn de clientes

Problema de clasificación binaria con datos **sintéticos** generados por un script
(nada de descargas). El dataset debe tener columnas de tipos deliberadamente
variados, porque el ejercicio de limpieza depende de eso:

| Columna | Tipo | Descripción |
|---|---|---|
| `id_cliente` | string | identificador, se descarta en el entrenamiento |
| `tipo_plan` | string (categórica) | `"basico"`, `"estandar"`, `"premium"` |
| `meses_contrato` | int | meses de antigüedad del contrato, 1 a 72 |
| `cargo_mensual` | float | cargo mensual, correlacionado con el plan |
| `llamadas_soporte` | int | llamadas a soporte en el último trimestre |
| `pago_automatico` | bool | tiene pago automático activado |
| `abandono` | int (0/1) | **target**: el cliente se fue (churn) |

Requisitos del generador (`generate.py`):

- ~5.000 filas, `numpy` con **semilla fija** (la reproducibilidad es tema de la
  sesión 1, así que la semilla se comenta explícitamente en el código).
- El target debe tener una relación aprendible pero no trivial: más
  `llamadas_soporte` y menos `meses_contrato` suben la probabilidad de abandono;
  `pago_automatico` la baja. Un modelo razonable debería quedar entre 0,75 y 0,90
  de ROC AUC — ni perfecto ni aleatorio.
- **Suciedad intencional**, para que el paso de limpieza tenga sentido:
  - ~3% de nulos en `cargo_mensual`,
  - `tipo_plan` con variantes de capitalización (`"Basico"`, `"BASICO"`, `"basico"`),
  - ~20 filas duplicadas exactas,
  - unos pocos `cargo_mensual` negativos (imposibles).
- Guarda el resultado en `data/raw/clientes.csv`.

## Estructura exacta del repositorio

```
mlops-recap-lab/
├── README.md
├── pyproject.toml
├── uv.lock                      # generado por uv, versionado
├── Makefile
├── .gitignore                   # .venv/, data/, mlruns/, mlartifacts/, __pycache__/
├── .pre-commit-config.yaml      # UN solo hook: ruff
├── data/                        # gitignored; solo un .gitkeep
│   ├── raw/
│   └── processed/
├── src/
│   └── churn/
│       ├── __init__.py
│       ├── config.py            # rutas, semilla, MLFLOW_PORT = 5001, nombres
│       ├── data/
│       │   ├── __init__.py
│       │   ├── generate.py      # dataset sintético → data/raw/
│       │   └── clean.py         # limpieza → data/processed/
│       └── models/
│           ├── __init__.py
│           └── train.py         # entrena, loguea y registra en MLflow
└── notebooks/
    ├── 01-explorar-y-limpiar.ipynb
    └── 02-entrenar-y-registrar.ipynb
```

Decisiones no negociables:

- **Paquete `src/churn/` instalable** en modo editable (`uv pip install -e .` lo
  hace `make setup` vía uv). Los notebooks **importan** del paquete
  (`from churn.config import ...`); no duplican lógica.
- **`config.py` es la única fuente de verdad** para rutas, semilla, el nombre del
  experimento, el nombre del modelo registrado y `MLFLOW_PORT = 5001`. Se usa el
  puerto 5001 porque en macOS AirPlay ocupa el 5000 y responde un 403 confuso —
  deja ese comentario en el código.
- Cada script se ejecuta con `python -m churn.data.generate`, etc. — sin CLI
  frameworks, sin argparse elaborado. Como mucho, cero argumentos.

## Limpieza (`clean.py`)

Cuatro pasos, cada uno con un `print` en español que diga qué hizo y cuántas filas
afectó (ej. `"Eliminadas 20 filas duplicadas"`). Es material didáctico: el output
de la terminal cuenta la historia.

1. Eliminar duplicados exactos.
2. Normalizar `tipo_plan` a minúsculas.
3. Eliminar filas con `cargo_mensual` negativo (imposible ≠ nulo: se comenta la
   diferencia).
4. Imputar nulos de `cargo_mensual` con la mediana **por plan**.

Guarda en `data/processed/clientes_limpio.parquet` y termina imprimiendo un
resumen: filas de entrada, filas de salida, nulos restantes (debe ser 0).

## Entrenamiento y registry (`train.py`)

Este es el corazón de la recapitulación de la sesión 3. El script:

1. Se conecta a `http://127.0.0.1:5001` (desde `config.py`) y crea/usa el
   experimento `churn-recap`.
2. Hace un split train/test estratificado con la semilla de `config.py`.
3. Preprocesa dentro de un `Pipeline` de sklearn (`OneHotEncoder` para
   `tipo_plan`, passthrough para el resto) — el preprocesamiento **viaja dentro
   del modelo**, no fuera.
4. Entrena **tres** configuraciones en un loop, una por run:
   `LogisticRegression`, `RandomForestClassifier(n_estimators=50)` y
   `RandomForestClassifier(n_estimators=200)`. Tres runs bastan; no uses Optuna
   ni búsqueda de hiperparámetros aquí.
5. En cada run loguea: los hiperparámetros, `roc_auc` y `accuracy` en test, un
   tag `model_family`, y el modelo con `signature` e `input_example`.
6. **Registra los tres** bajo el mismo nombre de modelo registrado
   (`churn-classifier`), de modo que queden como versiones 1, 2 y 3.
7. Asigna el alias **`champion`** a la versión con mejor `roc_auc`, usando
   `MlflowClient.set_registered_model_alias`. **Nunca uses stages** — están
   deprecados y en el curso se gobierna con aliases y tags.
8. Al final imprime una tabla comparativa de los tres runs (con
   `mlflow.search_runs`, no a ojo) y cuál quedó como champion.

## Notebooks

Los notebooks son **la versión narrada** de los scripts, no otra implementación.
Cada celda de código va precedida de una celda markdown que responde "¿qué vamos a
hacer y por qué?" en dos o tres frases, con analogías cuando ayuden (el registry
como un "estante de versiones etiquetadas", el alias como un "post-it movible que
señala cuál está en producción"). El público no es ingeniero: cero jerga sin
explicar.

- **`01-explorar-y-limpiar.ipynb`**: carga `data/raw/clientes.csv`, muestra los
  problemas uno por uno (los duplicados, la capitalización inconsistente, los
  nulos, los negativos) con el pandas mínimo para verlos, y luego llama a la
  función de limpieza del paquete y verifica el resultado. Cierra con: "esto mismo
  es lo que hace `make data` en un solo comando".
- **`02-entrenar-y-registrar.ipynb`**: la progresión completa paso a paso —
  entrenar un modelo y loguearlo, ver el run en la UI, entrenar los otros dos,
  compararlos con `search_runs`, registrar, poner el alias, y **cargar el modelo
  por alias** (`models:/churn-classifier@champion`) y predecir sobre 5 filas.
  Termina con la pregunta que responde todo el ejercicio: "si mañana la versión 4
  es mejor, ¿qué cambias? Solo el post-it. El código que carga por alias no se
  toca."
- Ambos guardados **sin outputs** ejecutados.

## Makefile

Solo esto, con una línea de comentario encima de cada target. `.PHONY` incluido.

```makefile
setup:    # uv sync + pre-commit install
data:     # python -m churn.data.generate && python -m churn.data.clean
mlflow:   # mlflow server con backend sqlite en puerto 5001 (queda en primer plano)
train:    # python -m churn.models.train
lint:     # ruff check . y ruff format .
all:      # data + train (mlflow debe estar corriendo aparte; el target lo recuerda con un echo)
```

## Hook de pre-commit

Un solo hook para que el concepto se digiera: `ruff` (check con `--fix` y format)
desde el repo oficial `astral-sh/ruff-pre-commit`. Nada más — ni nbstripout, ni
detect-secrets, ni trailing-whitespace. El README explica en tres líneas qué pasa
al hacer commit y por qué eso evita discusiones de estilo en el equipo.

## Dependencias (`pyproject.toml`)

Runtime: `pandas`, `scikit-learn`, `mlflow`, `pyarrow`, `numpy`.
Grupo dev: `ruff`, `pre-commit`, `jupyter` (o `ipykernel`).
Python `>=3.11`. Genera el `uv.lock` real ejecutando `uv sync`, y verséalo.

## README.md

Es la guía del estudiante y sigue este orden:

1. **Qué es esto** (2 frases) y un diagrama sencillo en Mermaid del flujo de
   datos: generar → limpiar → entrenar → registrar → cargar por alias.
2. **Cómo leer este repositorio**: un segundo diagrama Mermaid (`flowchart TD`)
   que es el **mapa de lectura** — le dice al estudiante en qué orden abrir los
   archivos y qué pregunta responde cada uno. Cada nodo es un archivo o carpeta
   real del repo, y las flechas son el orden de lectura, no el flujo de datos.
   Usa esta estructura como base (ajusta el texto si mejora, no la simplifiques):

   ```mermaid
   flowchart TD
       A["README.md<br/>¿de qué va esto?"] --> B["Makefile<br/>¿qué comandos existen?"]
       B --> C["pyproject.toml + uv.lock<br/>¿con qué dependencias?"]
       C --> D["notebooks/01-explorar-y-limpiar<br/>¿qué tienen de malo los datos?"]
       D --> E["notebooks/02-entrenar-y-registrar<br/>¿cómo comparo y promuevo modelos?"]
       E --> F["src/churn/<br/>lo mismo, pero como paquete"]
       F --> F1["config.py — la única fuente de verdad"]
       F --> F2["data/generate.py y data/clean.py"]
       F --> F3["models/train.py"]
       F --> G[".pre-commit-config.yaml<br/>¿quién vigila el estilo?"]
   ```

3. **Mapa de recapitulación**: una tabla de tres filas — qué pieza de este repo
   corresponde a qué sesión del curso (entorno/Makefile/hook → sesión 1,
   dataset/limpieza → sesión 2, tracking/registry → sesión 3).
4. **Puesta en marcha**: `git clone`, `make setup`, `make data`, `make mlflow`
   (en su propia terminal), `make train`, abrir la UI. Cada comando con una línea
   que dice qué se espera ver.
5. **Recorrido sugerido**: seguir el mapa de lectura del punto 2 — primero los
   dos notebooks en orden, después leer los scripts y notar que hacen lo mismo.
6. **Ejercicios de apropiación** (sin solución en el repo), por ejemplo: agregar
   una cuarta configuración de modelo y decidir si merece el alias; romper el
   lint a propósito y ver al hook rechazar el commit; agregar una columna nueva
   al generador y seguir el error hasta la `signature`.

## Verificación antes de terminar

Ejecuta tú mismo la secuencia completa y no des el trabajo por terminado hasta que
pase: `make setup`, `make data`, levantar `make mlflow` en background, `make train`,
y comprobar con `MlflowClient` que existen 3 versiones de `churn-classifier` y que
el alias `champion` apunta a la de mejor ROC AUC. Verifica también que
`git commit` con un archivo mal formateado es rechazado por el hook. Deja un
commit inicial limpio con todo el contenido (sin coautorías de herramientas).
