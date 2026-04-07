# Proyecto Final MLOps - Universidad de Medellin

## Objetivo

El objetivo de este proyecto es aplicar todo lo aprendido en el curso para construir un proyecto de machine learning end-to-end que demuestre competencias en experiment tracking, orquestación, deployment, monitoreo y mejores prácticas.

## Enunciado del Problema

Para el proyecto, deberás construir un proyecto de ML completo que incluya:

- Seleccionar un dataset de tu interés
- Entrenar un modelo en ese dataset con tracking de experimentos
- Crear un pipeline de entrenamiento de modelo
- Desplegar el modelo (batch, web service o streaming)
- Monitorear el rendimiento del modelo
- Seguir las mejores prácticas

## Ideas de Proyectos

- UC Irvine: <https://archive.ics.uci.edu/datasets/>
- Kaggle: <https://www.kaggle.com/datasets?search=machine+learning>, <https://www.kaggle.com/datasets>
- Google Research: <https://datasetsearch.research.google.com/>
- fivethirtyeight: <https://data.fivethirtyeight.com/>, <https://github.com/fivethirtyeight/data/tree/master>
- openml: <https://www.openml.org/search?type=data&sort=runs&status=active>
- AWS: <https://registry.opendata.aws/>
- Awesome public datasets: <https://github.com/awesomedata/awesome-public-datasets>
- Azure: <https://learn.microsoft.com/en-us/azure/azure-sql/public-data-sets?view=azuresql>

## Tecnologías Recomendadas

### Cloud Platforms

- **AWS**: SageMaker, Lambda, ECS, RDS
- **GCP**: Vertex AI, Cloud Functions, Cloud Run, BigQuery
- **Azure**: Machine Learning, Functions, Container Instances, SQL Database

### Experiment Tracking & Model Registry

- **MLflow**: Tracking, registry y deployment
- **Weights & Biases**: Experimentos y colaboración
- **DVC**: Versionado de datos y experimentos

### Workflow Orchestration

- **Prefect**: Orquestación moderna y flexible
- **Airflow**: Workflows complejos y programación

### Monitoring & Observability

- **Grafana**: Métricas y dashboards
- **Datadog**: Monitoreo completo de aplicaciones

### CI/CD

- **GitHub Actions**: Automatización de workflows
- **Jenkins**: Automatización personalizable

## Guidelines por Fase

### Fase 1: Planificación y Setup

#### 1.1 Selección del Proyecto

- [ ] Elegir un problema de ML que te apasione
- [ ] Definir métricas de éxito claras
- [ ] Establecer alcance del proyecto (MVP vs. funcionalidad completa)
- [ ] Crear timeline realista --> armar una tabla con tiempos y responsables
- [ ] Definir que problema de negocio solucionaria "hipoteticamente" (si aplica).

#### 1.2 Setup del Entorno

- [ ] Crear repositorio Git con estructura clara
- [ ] Configurar entorno virtual (Poetry/uv)
- [ ] Instalar dependencias básicas

#### 1.3 Análisis del Dataset

- [ ] Explorar y entender los datos
- [ ] Crear EDA (Exploratory Data Analysis)
- [ ] Definir estrategia de preprocesamiento
- [ ] Establecer baseline de rendimiento

### Fase 2: Experiment Tracking

#### 2.1 Configuración de MLflow

- [ ] Instalar y configurar MLflow
- [ ] Crear estructura de experimentos
- [ ] Configurar tracking de parámetros y métricas
- [ ] Implementar logging automático

#### 2.2 Experimentos Iniciales

- [ ] Probar diferentes algoritmos (Random Forest, XGBoost)
- [ ] Experimentar con hiperparámetros
- [ ] Implementar cross-validation
- [ ] Documentar resultados y aprendizajes

#### 2.3 Model Registry

- [ ] Registrar mejores modelos
- [ ] Versionar modelos con tags
- [ ] Implementar staging/production
- [ ] Crear documentación de modelos

### Fase 3: Pipeline de Entrenamiento

#### 3.1 Prefect Workflows

- [ ] Instalar y configurar Prefect
- [ ] Crear flows para preprocesamiento
- [ ] Implementar flow de entrenamiento
- [ ] Configurar scheduling automático

#### 3.2 Data Pipeline

- [ ] Implementar ETL para datos
- [ ] Crear transformaciones reproducibles
- [ ] Implementar validación de datos
- [ ] Configurar logging y monitoreo

#### 3.3 Model Pipeline

- [ ] Automatizar proceso de entrenamiento
- [ ] Implementar feature engineering
- [ ] Crear pipeline de evaluación
- [ ] Configurar retraining automático (Nice to have)

### Fase 4: Deployment

#### 4.1 Containerización

- [ ] Crear Dockerfile para la aplicación
- [ ] Optimizar imagen Docker  (Nice to have)

#### 4.2 API Development (si aplica)

- [ ] Crear API REST con FastAPI
- [ ] Implementar endpoints de predicción
- [ ] Agregar validación de inputs

#### 4.3 Cloud Deployment  (Nice to have)

- [ ] Configurar infraestructura en cloud
- [ ] Implementar CI/CD pipeline

### Fase 5: Monitoreo

- [ ] Proponer ideas de monitoreo: Diseño inicial

### Fase 6: Testing y Best Practices

#### 6.1 Testing

- [ ] Implementar unit tests

#### 6.2 Code Quality

- [ ] Configurar linter (flake8, black)
- [ ] Implementar formatter automático
- [ ] Configurar pre-commit hooks  (Nice to have)

#### 6.3 Documentation

- [ ] Crear README detallado
- [ ] Documentar API endpoints (si aplica)
- [ ] Crear guías de deployment

## Estructura del Repositorio Recomendada

```
proyecto-mlops/
├── README.md
├── pyproject.toml
├── .pre-commit-config.yaml
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── src/
│   ├── data/
│   ├── features/
│   ├── models/
│   ├── api/
│   └── monitoring/
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_baseline.ipynb
│   └── 03_experiments.ipynb
├── tests/
│   ├── unit/
├── configs/
├── data/
├── models/
├── logs/
└── docs/
```

## Recursos Adicionales

### Documentación

- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- [Prefect Documentation](https://docs.prefect.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Consejos para el Éxito

1. **Empieza Simple**: Comienza con un MVP y ve iterando
2. **Documenta Todo**: Cada decisión técnica debe estar documentada
3. **Testea Continuamente**: Implementa testing desde el día 1
4. **Usa Git Effectivamente**: Commits frecuentes y mensajes descriptivos
5. **Planifica la Infraestructura**: Piensa en escalabilidad desde el inicio
6. **Colabora**: Usa peer review para mejorar tu código
7. **Mantén Simplicidad**: No sobre-ingenierices la solución

## Evaluación

### ¿Cómo se calcula la nota?

| Componente | Peso | Quién evalúa |
|---|---|---|
| **Evaluación del instructor** | 70% | El profesor revisa cada proyecto con la rúbrica |
| **Promedio de peer reviews** | 20% | Cada proyecto recibe ~5-6 revisiones de compañeros |
| **Participación en peer review** | 10% | ¿Completaste tus 2 revisiones asignadas? Sí = 10%, No = 0% |

> Para el promedio de peer reviews se elimina la nota más alta y la más baja
> para evitar sesgos. Se promedian las restantes.

### Peer Review (revisión entre pares)

Al revisar código ajeno aprendes patrones, errores comunes y formas de resolver
problemas que no se te habían ocurrido.

**Cada persona** (no el grupo) debe revisar **2 proyectos** de otros grupos.
La asignación se comunicará por el canal del curso una vez se entreguen todos
los proyectos.

### ¿Cómo hacer la revisión?

1. Clona el repositorio del proyecto que te asignaron
2. Usa la plantilla `peer-review-template.md` (está en esta misma carpeta) como
   guía mientras revisas. Ahí están los criterios y checkboxes para cada sección.
3. Cuando termines, llena el **Google Form** con tus respuestas y puntuaciones.
   El enlace estará disponible tanto en este repositorio como en el aula virtual (Moodle).

La revisión toma ~20 minutos por proyecto. No tienes que escribir un ensayo —
solo verifica, marca y comenta donde sea necesario.
