# Proyecto Final MLOps - Universidad de Medellín

## Objetivo

El objetivo de este proyecto es aplicar todo lo aprendido en el curso para
construir un proyecto de machine learning end-to-end que demuestre competencias
en experiment tracking, orquestación, deployment, monitoreo y mejores prácticas.

## Enunciado del Problema

Para el proyecto, deberás construir un proyecto de ML completo que incluya:

- Seleccionar un dataset de tu interés
- Entrenar un modelo en ese dataset con tracking de experimentos
- Crear un pipeline de entrenamiento de modelo
- Desplegar el modelo (batch, web service o streaming)
- Monitorear el rendimiento del modelo
- Seguir las mejores prácticas

El deployment en la nube es deseable pero **no** es obligatorio: un despliegue
local bien hecho (contenedor, API, monitoreo) vale tanto como uno en la nube a
medias.

El proyecto es **en grupo**. El trabajo se hace en un repositorio de GitHub del
grupo, y todos los integrantes deben tener commits propios: la contribución
individual se mira en el historial.

## Ideas de Proyectos

- UC Irvine: <https://archive.ics.uci.edu/datasets/>
- Kaggle: <https://www.kaggle.com/datasets?search=machine+learning>, <https://www.kaggle.com/datasets>
- Google Research: <https://datasetsearch.research.google.com/>
- fivethirtyeight: <https://data.fivethirtyeight.com/>, <https://github.com/fivethirtyeight/data/tree/master>
- openml: <https://www.openml.org/search?type=data&sort=runs&status=active>
- AWS: <https://registry.opendata.aws/>
- Awesome public datasets: <https://github.com/awesomedata/awesome-public-datasets>
- Azure: <https://learn.microsoft.com/en-us/azure/azure-sql/public-data-sets?view=azuresql>

Si no quieren arriesgarse con el dataset, en
[`datasets-curados.md`](datasets-curados.md) hay una lista ya verificada: datasets
públicos, descargables sin cuenta, con suficientes filas y columnas para que las
fases de validación y monitoreo tengan sentido. Un consejo al elegir: si el
dataset tiene alguna noción de tiempo (fechas, períodos, cortes), la fase de
monitoreo les va a quedar mucho más natural, porque pueden comparar un período
contra otro en lugar de inventarse el drift.

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

- **Evidently**: Drift y calidad de datos
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
- [ ] Configurar entorno virtual (uv o Poetry)
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
- [ ] Promover el mejor modelo con un alias (por ejemplo `@champion`), que es lo
      que vimos en clase; los stages de MLflow están deprecados
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
- [ ] Optimizar imagen Docker (Nice to have)

#### 4.2 API Development (si aplica)

- [ ] Crear API REST con FastAPI
- [ ] Implementar endpoints de predicción
- [ ] Agregar validación de inputs

#### 4.3 Cloud Deployment (Nice to have)

- [ ] Configurar infraestructura en cloud
- [ ] Implementar CI/CD pipeline

### Fase 5: Monitoreo

- [ ] Implementar al menos un reporte de drift (referencia vs. datos nuevos),
      como el que hicimos en la sesión de monitoreo
- [ ] Proponer el diseño de monitoreo completo: qué medirían, con qué umbral y
      qué harían si se dispara

### Fase 6: Testing y Best Practices

#### 6.1 Testing

- [ ] Implementar unit tests

#### 6.2 Code Quality

- [ ] Configurar linter y formatter (ruff cubre los dos; flake8/black también
      sirven si los prefieren)
- [ ] Configurar pre-commit hooks (Nice to have)

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

En [`starter-template/`](starter-template/) hay un esqueleto con esta estructura
ya montada (pyproject, Makefile, CI, tests de ejemplo). Pueden copiarlo y
trabajar sobre él, o armar el suyo desde cero; las dos opciones son válidas.

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

Si van cortos de tiempo, [`mvp-minimo-aprobable.md`](mvp-minimo-aprobable.md)
lista lo mínimo que debe funcionar para que el proyecto se sostenga.

## Evaluación

**El proyecto final es el 100 % de la nota del curso.**

### ¿Cómo se calcula la nota?

| Componente | Peso | Quién evalúa |
|---|---|---|
| **Evaluación del instructor** | 70 % | El profesor revisa cada proyecto con la [rúbrica](rubrica-instructor.md) |
| **Promedio de peer reviews** | 20 % | Cada proyecto recibe varias revisiones de compañeros |
| **Participación en peer review** | 10 % | ¿Completaste tus 2 revisiones asignadas? Sí = 10 %, No = 0 % |

> Para el promedio de peer reviews se elimina la nota más alta y la más baja
> para evitar sesgos. Se promedian las restantes.

La rúbrica está publicada desde el primer día en
[`rubrica-instructor.md`](rubrica-instructor.md). Léanla antes de empezar, no al
final: ahí está exactamente qué se mira en cada dimensión y qué diferencia un 3
de un 5.

### Bonus por talleres

Los talleres de cada sesión son **opcionales**: no son requisito y no restan si
no se entregan. Pero suman. Los talleres entregados a lo largo del curso dan un
bonus de **hasta 1.0 unidad** sobre la nota final.

Por ejemplo: si el proyecto queda en 3.5 y entregaste los talleres con juicio
durante el semestre, la nota final puede llegar a 4.5. El bonus nunca baja la
nota y la nota final no pasa de 5.0.

### Peer Review (revisión entre pares)

Al revisar código ajeno aprendes patrones, errores comunes y formas de resolver
problemas que no se te habían ocurrido.

**Cada persona** (no el grupo) debe revisar **2 proyectos** de otros grupos.
La asignación se comunicará por el canal del curso una vez se entreguen todos
los proyectos.

### ¿Cómo hacer la revisión?

1. Clona el repositorio del proyecto que te asignaron
2. Usa la plantilla [`peer-review-template.md`](peer-review-template.md) (está en
   esta misma carpeta) como guía mientras revisas. Ahí están los criterios y
   checkboxes para cada sección.
3. Cuando termines, llena el **Google Form** con tus respuestas y puntuaciones.
   El enlace estará disponible tanto en este repositorio como en el aula virtual
   (Moodle).

Un tip para que la revisión sea rápida: empieza clonando el repo y tratando de
levantarlo con lo que diga su README. Lo que encuentres en ese intento ya es la
mitad de la revisión.
