
# Curso MLOps: Orquestacion de Pipelines de ML

Este modulo enseña como **automatizar, programar y hacer resilientes** tus pipelines de machine learning usando herramientas de orquestacion. Trabajamos principalmente con **Prefect** y exploramos **Mage** como alternativa visual, ambas aplicadas al mismo problema: predecir la duracion de viajes en taxi en NYC.

## Diagramas de Apoyo

En la carpeta [`diagrams/`](diagrams/) encontraras 12 diagramas organizados en 5 fases pedagogicas. Estan diseñados para explicar Prefect paso a paso, desde la motivacion hasta arquitectura de produccion:

| Fase | Diagramas | Pregunta que responde |
|---|---|---|
| **1. Motivacion** | [01 - El Problema](diagrams/01_el_problema.png), [02 - Los 5 Pilares](diagrams/02_cinco_pilares.png) | POR QUE necesito orquestacion? |
| **2. Conceptos Core** | [03 - Flow y Task](diagrams/03_flow_y_task.png), [04 - Grafo de Dependencias](diagrams/04_grafo_dependencias.png), [05 - Estados](diagrams/05_estados_ejecucion.png) | QUE es Prefect y como funciona? |
| **3. Resiliencia** | [06 - Reintentos](diagrams/06_reintentos.png), [07 - Caching](diagrams/07_caching.png) | COMO hago mi pipeline robusto? |
| **4. Deployment** | [08 - Deployment y Cron](diagrams/08_deployment.png), [09 - Arquitectura](diagrams/09_arquitectura.png) | COMO lo pongo a correr automaticamente? |
| **5. Aplicacion ML** | [10 - Pipeline NYC Taxi](diagrams/10_pipeline_ml_completo.png), [11 - Prefect + MLflow](diagrams/11_prefect_mlflow.png), [12 - Panorama](diagrams/12_panorama_orquestadores.png) | COMO aplico esto a ML en la vida real? |

Para regenerar los diagramas: `python diagrams/generate_diagrams.py`

---

## 1. Que problema resuelve la orquestacion?

> Ver: [Diagrama 01 - El Problema](diagrams/01_el_problema.png)

Sin orquestacion, un pipeline de ML es un script que ejecutas manualmente. Esto genera problemas reales:

| Sin orquestacion | Con orquestacion |
|---|---|
| Ejecutas scripts a mano | Se ejecutan automaticamente (cron, triggers) |
| Si falla, no te enteras | Alertas, logs y reintentos automaticos |
| No sabes que paso ni cuando | Dashboard con estado, duracion y resultados |
| Dificil reproducir una ejecucion | Parametros y artefactos versionados |
| Dependencias entre pasos son implicitas | Grafo explicito de dependencias |

> Ver: [Diagrama 02 - Los 5 Pilares](diagrams/02_cinco_pilares.png)

La orquestacion se trata de 5 principios (aplican a **cualquier** herramienta):

1. **Definir pasos claros** (tasks/blocks)
2. **Conectarlos en un flujo** (flow/pipeline)
3. **Automatizar la ejecucion** (scheduling/triggers)
4. **Observar y reaccionar** (dashboard/logs/artefactos)
5. **Manejar errores** (retries/alertas)

---

## 2. Instalacion

### Prefect

Prefect requiere **Python 3.10+** y se instala con un solo comando ([docs oficiales](https://docs.prefect.io/get-started/install)):

```bash
# Con pip
pip install -U prefect

# Con uv (recomendado en este curso)
uv add prefect
```

Para verificar la instalacion:

```bash
prefect version
```

**Dependencias adicionales** que usamos en el pipeline completo:

```bash
uv add mlflow optuna xgboost scikit-learn httpx
```

### Mage

Mage tiene dependencias que pueden entrar en conflicto con Prefect y MLflow, por lo que usamos un **entorno virtual aislado**. El script `setup_and_run.sh` se encarga de todo ([docs oficiales](https://docs.mage.ai/getting-started/setup)):

```bash
cd 03-Orchestration/Mage-pipelines/
chmod +x setup_and_run.sh
./setup_and_run.sh
```

Esto crea un entorno `.venv-mage` separado con `uv`, instala Mage, y abre la UI en `http://localhost:6789`.

> **Nota:** Necesitas tener `uv` instalado. Si no lo tienes: `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

## 3. Conceptos Core de Prefect

> Ver: [Diagrama 03 - Flow y Task](diagrams/03_flow_y_task.png)

### Que es un Flow y que es un Task?

| Concepto | Que es | Para que sirve |
|---|---|---|
| **Flow** | Funcion decorada con `@flow` | Define el pipeline completo |
| **Task** | Funcion decorada con `@task` | Define un paso individual del pipeline |
| **Deployment** | Configuracion de ejecucion | Programa cuando y como se ejecuta un flow |
| **Artifact** | Resultado visual | Muestra resultados en el dashboard (tablas, graficos) |
| **Schedule** | Expresion cron o intervalo | Automatiza la ejecucion periodica |

Referencia: [Prefect Concepts - Flows](https://docs.prefect.io/concepts/flows) | [Tasks](https://docs.prefect.io/concepts/tasks)

### Ejemplo minimo

```python
from prefect import flow, task

@task
def cargar_datos():
    print("Cargando datos...")
    return [1, 2, 3]

@task
def procesar(datos):
    print(f"Procesando {len(datos)} registros")
    return sum(datos)

@flow
def mi_pipeline():
    datos = cargar_datos()
    resultado = procesar(datos)
    print(f"Resultado: {resultado}")

# Ejecutar
mi_pipeline()
```

Con solo agregar `@flow` y `@task`, Prefect automaticamente:
- Registra el estado de cada paso (exito, fallo, en progreso)
- Mide tiempos de ejecucion
- Captura logs
- Permite ver todo en un dashboard

### Grafo de dependencias

> Ver: [Diagrama 04 - Grafo de Dependencias](diagrams/04_grafo_dependencias.png)

Cuando un task recibe el resultado de otro, Prefect entiende la dependencia. Los tasks se ejecutan en el orden correcto automaticamente. Si dos tasks no dependen entre si, Prefect puede ejecutarlos en paralelo.

### Estados de ejecucion

> Ver: [Diagrama 05 - Estados de Ejecucion](diagrams/05_estados_ejecucion.png)

Cada flow y task pasa por estados: `SCHEDULED` -> `PENDING` -> `RUNNING` -> `COMPLETED` o `FAILED`. Si tiene retries configurados, pasa a `RETRYING` antes de volver a `RUNNING`.

Referencia: [Prefect Concepts - States](https://docs.prefect.io/concepts/states)

---

## 4. Resiliencia: Retries y Caching

### Reintentos automaticos

> Ver: [Diagrama 06 - Reintentos](diagrams/06_reintentos.png)

```python
@task(retries=3, retry_delay_seconds=10)
def descargar_datos(url):
    response = httpx.get(url)
    return response.json()
```

Si el task falla (timeout, error de red, etc.), Prefect reintenta automaticamente hasta 3 veces, esperando 10 segundos entre cada intento.

Referencia: [Prefect - Retries](https://docs.prefect.io/concepts/tasks#retries)

### Caching

> Ver: [Diagrama 07 - Caching](diagrams/07_caching.png)

```python
from datetime import timedelta

@task(cache_expiration=timedelta(hours=24))
def cargar_datos(year, month):
    # Solo se ejecuta si no hay cache valido
    return pd.read_parquet(f"https://.../{year}-{month}.parquet")
```

Si los datos no cambian, no los recalcula. Ahorra tiempo en ejecuciones repetidas.

Referencia: [Prefect - Caching](https://docs.prefect.io/concepts/tasks#caching)

---

## 5. Deployment y Scheduling

> Ver: [Diagrama 08 - Deployment](diagrams/08_deployment.png)

La progresion para poner un flow a correr automaticamente:

| Nivel | Metodo | Que hace |
|---|---|---|
| 1 | `python pipeline.py` | Ejecucion manual, una vez |
| 2 | `flow.serve(name='mi-deploy')` | El flow queda escuchando peticiones |
| 3 | `flow.serve(cron='0 2 * * *')` | Se ejecuta solo, todos los dias a las 2am |
| 4 | `prefect deploy --all` (prefect.yaml) | Config declarativa, multiples deployments |

### Expresiones cron

| Expresion | Significado |
|---|---|
| `* * * * *` | `minuto  hora  dia  mes  dia_semana` |
| `0 2 * * *` | Todos los dias a las 2:00 AM |
| `*/5 * * * *` | Cada 5 minutos |
| `0 9 * * 1-5` | Lunes a viernes a las 9 AM |
| `0 0 1 * *` | El primer dia de cada mes a medianoche |

Referencia: [Prefect - Schedules](https://docs.prefect.io/concepts/schedules) | [Guia de prefect.yaml](00-intro-prefect/infrastructure/prefect-yaml-guide.md)

### Arquitectura de Prefect

> Ver: [Diagrama 09 - Arquitectura](diagrams/09_arquitectura.png)

Prefect tiene tres componentes principales:
- **Tu codigo** (pipeline.py con `@flow` y `@task`)
- **Prefect Server** (API REST + scheduler + base de datos)
- **Dashboard UI** (localhost:4200 o app.prefect.cloud)

Puedes usar el servidor local (gratis, `prefect server start`) o Prefect Cloud (managed, tier gratuito disponible).

Referencia: [Prefect - Server & Cloud](https://docs.prefect.io/host)

---

## 6. Progresion de Aprendizaje

### 6.1. Ejemplos basicos (carpeta `00-intro-prefect/`)

Los archivos en `flows/` estan diseñados para seguirse en orden:

1. **`weather1-bare.py`** - Flow basico: una funcion con `@flow` que consulta una API del clima
2. **`weather1-flow.py`** - Lo mismo pero ya como flow completo
3. **`weather1-serve.py`** - Servir el flow como deployment local (el flow queda "escuchando")
4. **`weather1-serve-params.py`** - Deployment con parametros configurables
5. **`weather1-serve-schedule.py`** - Deployment con schedule automatico
6. **`weather1-deploy.py`** - Deployment remoto
7. **`serve-two-flows.py`** - Servir multiples flows desde un mismo archivo
8. **`serve-two-flows-scheduled.py`** - Multiples flows con schedules diferentes

Para ejecutar cualquier ejemplo:

```bash
# Ejecutar un flow directamente
uv run python 00-intro-prefect/flows/weather1-bare.py

# Iniciar el servidor de Prefect (para ver el dashboard)
uv run prefect server start

# En otra terminal, servir un flow
uv run python 00-intro-prefect/flows/weather1-serve.py
```

El dashboard estara disponible en `http://localhost:4200`.

### 6.2. Funcionalidades avanzadas (carpeta `workflows/`)

- **`retries.py`** - Reintentos automaticos cuando un task falla
- **`simple-artifacts.py`** - Crear artefactos visuales en el dashboard
- **`artifacts-ml.py`** - Artefactos especificos para pipelines de ML
- **`runtime_context.py`** - Acceder a informacion del flow en ejecucion

### 6.3. Pipeline completo de ML (carpeta `Prefect-pipelines/`)

> Ver: [Diagrama 10 - Pipeline ML Completo](diagrams/10_pipeline_ml_completo.png)

El directorio `Prefect-pipelines/` contiene un pipeline real de ML que:

1. **Descarga datos** de taxis de NYC (formato parquet) desde [NYC TLC](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
2. **Valida** volumen y calidad de los datos
3. **Crea features** con [DictVectorizer](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.DictVectorizer.html) (PULocationID, DOLocationID)
4. **Optimiza hiperparametros** con [Optuna](https://optuna.readthedocs.io/) (20 trials)
5. **Entrena** un modelo [XGBoost](https://xgboost.readthedocs.io/) con los mejores parametros
6. **Registra** todo en [MLflow](https://mlflow.org/docs/latest/) (metricas, modelo, artefactos)
7. **Genera** un resumen visual como artefacto de Prefect

#### Ejecutar el pipeline

```bash
cd Prefect-pipelines/

# Ejecucion unica
uv run python pipeline.py --year 2025 --month 1

# Deployment automatico (cada 2 minutos, para practicar)
uv run python deploy.py
```

#### Arquitectura modular

El pipeline sigue una arquitectura modular en `src/`:

```
src/
├── config/          # Constantes (year, month, nombres de experimento)
│   ├── constants.py
│   └── mlflow_setup.py
├── data/            # Carga desde URL, validacion, utilidades
│   ├── loaders.py
│   ├── validators.py
│   └── utils.py
├── features/        # DictVectorizer sobre columnas categoricas
│   └── engineering.py
└── models/          # Optuna optimization + entrenamiento XGBoost
    └── optimization.py
```

### 6.4. Integracion Prefect + MLflow

> Ver: [Diagrama 11 - Prefect + MLflow](diagrams/11_prefect_mlflow.png)

| Prefect responde | MLflow responde |
|---|---|
| CUANDO se ejecuta el pipeline | QUE parametros usaste |
| En QUE ORDEN se ejecutan los pasos | QUE metricas obtuviste |
| QUE HACER si falla (retries) | QUE modelo entrenaste |
| ESTADO general (dashboard) | COMPARAR experimentos |
| Artefactos (resumenes) | Versionado de modelos (Registry) |

---

## 7. Alternativa Visual: Mage

Mage es un orquestador que usa una **interfaz grafica tipo notebook** en el navegador. Implementamos exactamente el mismo pipeline de NYC Taxi para comparar ambos enfoques.

| Aspecto | Prefect | Mage |
|---|---|---|
| **Filosofia** | Code-first (decoradores Python) | UI-first (bloques visuales) |
| **Unidad basica** | `@flow` + `@task` | Bloques: data_loader, transformer, data_exporter |
| **Edicion** | Tu editor/IDE favorito | UI web tipo notebook |
| **Flujo** | Definido en codigo Python | Definido en `metadata.yaml` / visualmente |
| **Retries/cache** | Decoradores (`retries=3`) | Configuracion en UI o metadata |

Referencia: [Mage Docs - Getting Started](https://docs.mage.ai/getting-started/setup)

### Ejecutar Mage

```bash
cd Mage-pipelines/

# Opcion 1: UI visual (recomendado para aprender)
./setup_and_run.sh

# Opcion 2: Solo ejecutar el pipeline (sin UI)
./setup_and_run.sh --run
```

La UI se abre en `http://localhost:6789`. Ahi puedes ver los bloques conectados, ejecutarlos individualmente, y ver logs en tiempo real.

> Para una comparacion detallada entre Prefect, Mage, Airflow y Dagster, revisa el notebook [`comparacion_orquestadores.ipynb`](Mage-pipelines/comparacion_orquestadores.ipynb).

---

## 8. Panorama de Herramientas de Orquestacion

> Ver: [Diagrama 12 - Panorama de Orquestadores](diagrams/12_panorama_orquestadores.png)

| Herramienta | Enfoque | Ideal para | Complejidad de setup |
|---|---|---|---|
| **[Prefect](https://docs.prefect.io/)** | Code-first, Python nativo | Equipos de ML/DS, startups | Baja (`pip install prefect`) |
| **[Mage](https://docs.mage.ai/)** | UI visual, tipo notebook | Prototipos, aprendizaje | Baja (pero entorno aislado) |
| **[Apache Airflow](https://airflow.apache.org/)** | DAGs, estandar empresarial | Empresas grandes, ETL complejo | Alta (scheduler + webserver + DB) |
| **[Dagster](https://docs.dagster.io/)** | Assets-first, tipado fuerte | Data engineering con contratos | Media |
| **[Kestra](https://kestra.io/)** | YAML-first, event-driven | Equipos multilenguaje | Media |

### Por que Prefect en este curso?

- **Setup minimo**: `pip install prefect` y funciona, no necesitas levantar servicios extra
- **Python nativo**: Agregas `@flow` y `@task` a funciones normales de Python
- **Bueno para ML**: Artefactos, caching, integracion natural con MLflow
- **Dashboard moderno**: Monitoreo sin configuracion adicional

### Cuando usar cada herramienta?

- **Prefect**: Cuando tu equipo ya programa en Python y quiere orquestar rapido
- **Mage**: Cuando necesitas prototipar visualmente o enseñar conceptos
- **Airflow**: Cuando la empresa ya lo usa o necesitas integraciones masivas (+2000 plugins)
- **Dagster**: Cuando necesitas contratos de datos estrictos entre pasos

---

## 9. Estructura del Modulo

```
03-Orchestration/
├── 00-intro-prefect/              # Conceptos basicos de Prefect
│   ├── flows/                     # Ejemplos progresivos de flows
│   │   ├── weather1-bare.py       # Flow minimo (solo @flow)
│   │   ├── weather1-flow.py       # Flow con decorador
│   │   ├── weather1-serve.py      # Flow servido (deployment local)
│   │   ├── weather1-serve-params.py
│   │   ├── weather1-serve-schedule.py
│   │   ├── weather1-deploy.py
│   │   ├── serve-two-flows.py
│   │   └── serve-two-flows-scheduled.py
│   ├── workflows/                 # Funcionalidades avanzadas
│   │   ├── my-first-task.py       # Tasks basicos
│   │   ├── retries.py             # Reintentos automaticos
│   │   ├── simple-artifacts.py    # Artefactos en dashboard
│   │   ├── artifacts-ml.py        # Artefactos para ML
│   │   ├── runtime_context.py     # Contexto de ejecucion
│   │   ├── get_variable.py        # Variables de configuracion
│   │   ├── create_secret.py       # Secretos
│   │   └── openai_with_secret.py  # Uso de secretos con APIs
│   ├── infrastructure/
│   │   └── prefect-yaml-guide.md  # Guia de deployments con YAML
│   └── prefect.yaml               # Ejemplo de configuracion
│
├── Prefect-pipelines/             # Pipeline completo NYC Taxi con Prefect
│   ├── pipeline.py                # Flow principal (orquestacion)
│   ├── deploy.py                  # Deployment con schedule (cron)
│   └── src/                       # Codigo modular del pipeline
│       ├── config/                # Constantes y setup de MLflow
│       ├── data/                  # Carga y validacion de datos
│       ├── features/              # Feature engineering
│       └── models/                # Optuna + XGBoost + MLflow
│
├── Mage-pipelines/                # Mismo pipeline con Mage (alternativa visual)
│   ├── comparacion_orquestadores.ipynb  # Comparacion detallada Prefect vs Mage
│   ├── setup_and_run.sh           # Script para instalar y ejecutar Mage
│   ├── pyproject.toml             # Dependencias aisladas para Mage
│   ├── test_blocks.py             # Tests de los bloques
│   └── nyc_taxi_project/          # Proyecto Mage
│       ├── data_loaders/          # Bloque: carga de datos
│       ├── transformers/          # Bloques: validacion y features
│       ├── data_exporters/        # Bloque: entrenamiento
│       ├── pipelines/             # Definicion del pipeline (metadata.yaml)
│       └── utils/                 # Constantes compartidas
│
├── diagrams/                      # Diagramas educativos (12 PNGs)
│   ├── generate_diagrams.py       # Script para regenerar los diagramas
│   ├── 01_el_problema.png         # Fase 1: Motivacion
│   ├── 02_cinco_pilares.png
│   ├── 03_flow_y_task.png         # Fase 2: Conceptos core
│   ├── 04_grafo_dependencias.png
│   ├── 05_estados_ejecucion.png
│   ├── 06_reintentos.png          # Fase 3: Resiliencia
│   ├── 07_caching.png
│   ├── 08_deployment.png          # Fase 4: Deployment
│   ├── 09_arquitectura.png
│   ├── 10_pipeline_ml_completo.png  # Fase 5: Aplicacion ML
│   ├── 11_prefect_mlflow.png
│   └── 12_panorama_orquestadores.png
│
└── README.md                      # Este archivo
```

---

## 10. Referencias

### Documentacion oficial
- [Prefect 3.x Docs](https://docs.prefect.io/) - Guia completa, quickstart, API reference
- [Prefect GitHub](https://github.com/PrefectHQ/prefect) - Codigo fuente y ejemplos
- [Mage AI Docs](https://docs.mage.ai/) - Guia de Mage, setup, bloques
- [Mage AI GitHub](https://github.com/mage-ai/mage-ai) - Codigo fuente
- [Apache Airflow Docs](https://airflow.apache.org/docs/) - Referencia del estandar de la industria
- [Dagster Docs](https://docs.dagster.io/) - Framework assets-first
- [Kestra Docs](https://kestra.io/docs) - Orquestacion YAML-first

### Herramientas usadas en el pipeline
- [MLflow](https://mlflow.org/docs/latest/) - Experiment tracking y model registry
- [Optuna](https://optuna.readthedocs.io/) - Optimizacion de hiperparametros
- [XGBoost](https://xgboost.readthedocs.io/) - Gradient boosting
- [scikit-learn DictVectorizer](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.DictVectorizer.html) - Feature encoding
- [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) - Dataset publico

### Recursos de aprendizaje
- [MLOps Zoomcamp - Module 3: Orchestration](https://github.com/DataTalksClub/mlops-zoomcamp/tree/main/03-orchestration) - Material base de referencia
- [Prefect vs Airflow](https://docs.prefect.io/latest/resources/airflow-vs-prefect/) - Comparacion oficial
- [Mage vs Airflow](https://docs.mage.ai/about/comparison/airflow) - Comparacion oficial de Mage
- [Notebook de comparacion](Mage-pipelines/comparacion_orquestadores.ipynb) - Comparacion detallada Prefect vs Mage vs Airflow vs Dagster (dentro de este repositorio)

### Libros recomendados
- *"Fundamentals of Data Engineering"* - Joe Reis & Matt Housley (capitulos de orquestacion)
- *"Designing Machine Learning Systems"* - Chip Huyen (pipelines de ML en produccion)
