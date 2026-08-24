# Curso de MLOps

**Universidad de Medellín** — Especialización en Inteligencia Artificial

Ocho sesiones de cuatro horas para llevar un modelo de machine learning desde un
notebook hasta producción, con reproducibilidad, orquestación, despliegue,
monitoreo y gobernanza.

> **¿Vienes de la versión anterior del repositorio?** La estructura cambió por
> completo. `docs/MIGRACION.md` dice dónde quedó cada carpeta y por qué.

---

## Empieza aquí

### Paso 0 — diagnostica tu máquina

**Antes de instalar nada.** Este script corre con cualquier Python 3.11 o superior,
sin una sola dependencia, y te dice exactamente qué te falta:

```bash
git clone https://github.com/dpalacioj/MLOps-Course.git
cd MLOps-Course
python3 scripts/smoke_test.py      # en Windows: python scripts\smoke_test.py
```

Va a salir en rojo, y está bien: todavía no has instalado nada. Lo que importa es
**qué** dice en rojo. Cada línea `FAIL` trae el comando que la arregla.

Si te dice que no tienes Python 3.11, instálalo con
[uv](https://docs.astral.sh/uv/) (paso 1) y vuelve aquí.

### Paso 1 — las tres herramientas que el repositorio no puede instalar solo

| Herramienta | Para qué | Cómo |
|---|---|---|
| **uv** | gestiona Python y las dependencias. Sin esto no arranca nada | macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh \| sh`<br>Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| **git-lfs** | los 12 diagramas del curso. Sin esto se ven como texto | macOS: `brew install git-lfs`<br>Windows: `winget install GitHub.GitLFS`<br>Linux: `sudo apt install git-lfs` |
| **make** *(opcional)* | atajos. Ya viene en macOS y Linux | Windows: `winget install GnuWin32.Make`, o copia el comando del `Makefile` |

Cierra y reabre la terminal después de instalar `uv`, para que aparezca en el `PATH`.

En Windows, además, antes de correr cualquier `.ps1`:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Paso 2 — instala y verifica

```bash
git lfs install && git lfs pull   # trae los diagramas
make setup                        # dependencias, hooks de git y pre-commit
make smoke                        # ahora sí debe salir todo en verde
```

**Sin `make`** (Windows sin GnuWin32), los dos equivalentes son:

```bash
uv sync --group dev && uv run pre-commit install
uv run python scripts/smoke_test.py
```

**No sigas hasta que `make smoke` salga limpio.** Docker puede quedar en `WARN`:
no hace falta hasta la sesión 5.

### Si el setup se resiste

Hay un devcontainer listo en `.devcontainer/`: abre el repositorio en un Codespace
o en VS Code con Dev Containers y el entorno queda montado sin instalar nada en tu
máquina. Es el plan B, no la ruta principal.

`make smoke` revisa `uv`, `make`, la versión de Python, las 17 dependencias clave,
los contratos de datos, los archivos de Git LFS, los puertos y Docker. Da `OK`,
`WARN` o `FAIL` línea por línea, y cada `FAIL` trae el comando que lo arregla.

`make` sin argumentos lista todos los comandos disponibles.

---

## Las ocho sesiones

Cada sesión agrega una capa al **mismo sistema**, que el estudiante construye en
su propio repositorio. No son ocho ejercicios sueltos.

| # | Sesión | Pregunta que responde | Carpeta |
|---|---|---|---|
| 1 | Reproducibilidad y disciplina de ingeniería | ¿Por qué la mayoría de los modelos no llega a producción? | [`sesiones/s01-reproducibilidad`](sesiones/s01-reproducibilidad) |
| 2 | Datos como código | ¿Cómo evito que un cambio silencioso en los datos rompa el modelo? | [`sesiones/s02-datos`](sesiones/s02-datos) |
| 3 | Experiment tracking y model registry | ¿Cómo sé cuál de mis 200 experimentos está en producción? | [`sesiones/s03-tracking`](sesiones/s03-tracking) |
| 4 | Orquestación y Continuous Training | ¿Cómo paso de "ejecuté el script" a "el sistema se reentrena solo"? | [`sesiones/s04-orquestacion`](sesiones/s04-orquestacion) |
| 5 | Deployment | ¿Cómo sirvo el modelo sin que "en mi máquina funciona"? | [`sesiones/s05-deployment`](sesiones/s05-deployment) |
| 6 | Cloud y CI/CD | ¿Cómo se despliega y se promueve sin intervención manual? | [`sesiones/s06-cloud-cicd`](sesiones/s06-cloud-cicd) |
| 7 | Monitoreo, drift y gobernanza | ¿Cómo sé que el modelo sigue sirviendo, y cuándo reentrenar? | [`sesiones/s07-monitoreo`](sesiones/s07-monitoreo) |
| 8 | LLMOps | ¿Qué cambia y qué no cuando el modelo es un LLM? | [`sesiones/s08-llmops`](sesiones/s08-llmops) |

### Carga real, declarada

Esta tabla es la **única fuente de verdad** sobre tiempos. Si algún otro
documento dice otra cosa, este manda.

| Sesión | Aula | Trabajo autónomo |
|---|---|---|
| S1 a S8 | 4 h cada una = **32 h** | 3 h por sesión = 24 h |
| Hitos del proyecto (3) | — | 4 h cada uno = 12 h |
| Entrega final + peer review | — | 10 h |
| **Total** | **32 h** | **~46 h** |

Es una carga alta para un posgrado, y está medida en lugar de ser una sorpresa.

### Formato de cada sesión

| Tramo | Min | Qué pasa |
|---|---|---|
| Arranque | 0-15 | Recap de la sesión anterior por un estudiante + revisión del CI de los talleres |
| **El dolor** | 15-40 | Demo en vivo de lo que se rompe *sin* la herramienta de hoy |
| Bloque A | 40-95 | Concepto → implementación guiada |
| Pausa | 95-110 | |
| Bloque B | 110-165 | Concepto → implementación guiada |
| Taller | 165-220 | Los estudiantes trabajan; se entrega en clase |
| Cierre | 220-240 | Autoverificación, alternativas y trade-offs, **qué NO usar**, tarea |

Dos reglas del formato. **Primero el dolor**: nunca se abre una herramienta antes
de sentir el problema que resuelve. Y **el cierre nombra lo deprecado**: cada
sesión dice explícitamente qué APIs y qué herramientas ya no se usan, con fecha.
Eso es lo que separa un curso de posgrado de un tutorial.

---

## El caso guía

**NYC Green Taxi**, con particiones mensuales fijas. La forma del dataset es la
forma del problema de MLOps: los datos llegan por particiones mensuales, y eso da
—sin inventar nada— un disparador natural de reentrenamiento, drift **real**
(estacionalidad, tarifas, tráfico) y un *train/serve skew* verificable.

| Uso | Particiones |
|---|---|
| Entrenamiento | 2023-01, 2023-02, 2023-03 |
| Validación | 2023-04 |
| Holdout fijo (juez del gate de promoción) | 2023-05 |
| Producción simulada (monitoreo) | 2023-07, 2024-01 |

Están fijas en `src/taxi/config.py` a propósito: un curso no puede depender de que
la NYC TLC haya publicado el mes corriente. Dos targets sobre el mismo dataset:
`duration` para regresión y `viaje_largo = duration > 30` para clasificación, lo
que permite enseñar umbrales y matriz de costos sin traer un segundo dataset.

Las decisiones de diseño están documentadas en [`docs/adr/`](docs/adr).

---

## Estructura del repositorio

```
sesiones/s01…s08/       Material de clase: README, notebooks, taller y soluciones
src/taxi/               El caso guía como paquete instalable
  config.py               particiones, nombres, umbrales — fuente de verdad única
  data/                   contratos Pandera y descarga con verificación de hash
  features/contract.py    la ÚNICA definición de features del curso
  models/                 entrenamiento, HPO, registry, evaluación
  api/                    FastAPI con Pydantic v2 y métricas Prometheus
  flows/                  pipelines de Prefect 3
  monitoring/             detección de drift
tests/                  308 tests: unitarios, de datos y de API
scripts/                smoke_test, gate de promoción, model card, hooks
proyecto/               Proyecto final: enunciado, rúbrica, starter template
instructor/             Ocho guiones de clase con bloques minutados
docs/                   ADRs, mapa de migración, cierre del curso
observabilidad/          Prometheus y dashboards de Grafana versionados
referencia/             Material opcional de consulta
```

---

## Stack

Versiones verificadas ejecutando el código en agosto de 2026. El `uv.lock` las
fija; el nightly avisa si alguna se rompe.

| Capa | Herramienta | Alternativas que el curso discute |
|---|---|---|
| Entorno y dependencias | `uv` 0.12 | Poetry 2.x (vivo y mantenido), pip-tools, conda |
| Calidad | Ruff 0.16 (lint + format), mypy | Black — **no mezclar con Ruff** |
| Contratos de datos | Pandera 0.32 | Great Expectations Core 1.x, Pydantic |
| Tracking y registry | MLflow 3.15 | W&B, Comet, Neptune |
| HPO | Optuna 4.9 | Ray Tune |
| Orquestación | Prefect 3.8 | Airflow 3.3, Dagster 1.13, ZenML, Metaflow |
| Serving | FastAPI 0.141 + Pydantic 2.13 | BentoML, KServe, Ray Serve |
| Contenedores | Docker + Compose | — |
| Cloud | AWS (ECR, App Runner, S3, RDS) | Cloud Run, Container Apps |
| Monitoreo | Evidently 0.7 + Prometheus | Arize Phoenix, Langfuse |
| CI/CD | GitHub Actions | — |

**Modelos:** scikit-learn 1.9 y XGBoost 3.2.

---

## Evaluación

| Componente | Peso | Cómo se verifica |
|---|---|---|
| Talleres de sesión (8, se descarta el más bajo) | 30 % | El CI del repositorio del estudiante |
| Hitos del proyecto (3: tras S2, S4 y S6) | 15 % | PR revisado |
| Proyecto final — instructor | 40 % | [`proyecto/rubrica-instructor.md`](proyecto/rubrica-instructor.md) |
| Proyecto final — peer review recibido | 10 % | Promedio recortado |
| Participación en peer review | 5 % | Completó sus 2 revisiones |

La rúbrica del instructor está publicada desde el primer día, con anclas escritas
para los niveles 1, 3 y 5 de cada dimensión y la columna de qué comando mira el
instructor para asignar el puntaje.

El proyecto final tiene [requisitos duros de dataset](proyecto/README.md): sin eje
temporal no hay split honesto, ni drift, ni reentrenamiento. Hay una
[lista curada de datasets](proyecto/datasets-curados.md) verificados contra esos
requisitos.

---

## Comandos frecuentes

```bash
make smoke        # verifica el entorno
make data         # descarga y prepara las particiones (verifica SHA-256)
make train        # entrena y registra el candidato en MLflow
make promote      # el gate decide si el candidato pasa a @champion
make drift        # reporte de drift: referencia contra producción simulada
make serve        # API de inferencia en http://127.0.0.1:8000/docs
make up           # stack completo: MLflow, MinIO, Postgres, Prometheus, Grafana
make check        # lo mismo que verifica el CI, en local
```

---

## Créditos

Basado en el curso original de
[CamilaCortex/MLOps_UdM](https://github.com/CamilaCortex/MLOps_UdM), de
**María Camila Durango** y **Mateo Cano Solís**. Buena parte del material que
mejor funciona en clase viene de ahí: la progresión "sin tracking → tracking
básico → tracking completo", los tres escenarios de arquitectura de MLflow, la
progresión escalonada de Prefect y el guion de clase de orquestación.

Rediseño y mantenimiento: **David Palacio**.

## Lecturas recomendadas

- *Designing Machine Learning Systems* — Chip Huyen
- *Machine Learning Engineering* — Andriy Burkov
- *Hidden Technical Debt in Machine Learning Systems* — Sculley et al., NeurIPS 2015

## Contribuir

Ver [`CONTRIBUTING.md`](CONTRIBUTING.md): convenciones de ramas, conventional
commits, estilo de idioma y cómo se sincroniza con el repositorio original.
