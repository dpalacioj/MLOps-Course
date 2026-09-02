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

Cada sesión arranca mostrando el problema antes que la herramienta, tiene una
parte práctica que se trabaja en clase, y cierra revisando qué alternativas
existen y qué prácticas ya quedaron viejas. Aparte de las horas de clase, cuenten
con unas horas semanales para el proyecto.

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

## Qué hay en cada carpeta

| Carpeta | Qué contiene |
|---|---|
| `sesiones/s01…s08/` | El material de cada clase. Cada sesión trae su `README.md` (la lectura principal), `notebooks/` para la parte práctica, `taller.md` con el ejercicio, y `_soluciones/` — que conviene no abrir antes de intentar el taller |
| `src/taxi/` | El caso guía (los taxis de Nueva York) como paquete Python instalable. Es el código que los notebooks importan y el ejemplo vivo de todo lo que el curso enseña: `config.py` reúne las decisiones, `data/` carga y valida, `features/` construye variables, `models/` entrena y registra, `api/` sirve el modelo, `flows/` lo orquesta y `monitoring/` lo vigila |
| `tests/` | Los tests del paquete: unitarios, de contrato de datos y de la API. `make test` los corre |
| `scripts/` | Herramientas sueltas: `smoke_test.py` (el diagnóstico del entorno), `promote.py` (el gate de promoción de la sesión 6), `model_card.py`, y los hooks propios del repositorio |
| `proyecto/` | Todo lo del proyecto final: el enunciado, la rúbrica con la que se califica, la plantilla de peer review, una lista de datasets verificados y un `starter-template/` listo para copiar |
| `data/` | Aquí caen los datos al correr `make data`. **No se versiona** (salvo `metadata.json`, que registra de dónde vino cada archivo y su hash) |
| `docs/` | Las decisiones de diseño del repositorio (`adr/`) y el mapa de migración desde la estructura anterior |
| `observabilidad/` | La configuración de Prometheus y los dashboards de Grafana que usa `make up` (sesión 7) |
| `instructor/` | Notas de clase del docente, sesión por sesión |
| `referencia/` | Guías de consulta opcionales (comandos de Docker, etc.). No hacen falta para seguir el curso |
| `.devcontainer/` | El plan B: abre el repo en GitHub Codespaces y el entorno queda montado sin instalar nada |
| `.github/workflows/` | El CI del repositorio: lint, tests, build de la imagen y el pipeline de despliegue |

Y los archivos sueltos de la raíz: `pyproject.toml` y `uv.lock` declaran y fijan
las dependencias, `Makefile` es la lista de comandos (`make` a secas los
muestra), `Dockerfile` y `docker-compose.yml` arman los servicios locales, y
`.pre-commit-config.yaml` define los hooks que se instalan con `make setup`.

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

La nota del curso sale del **proyecto final en grupo**: un sistema de ML de punta
a punta con tracking, pipeline, deployment y monitoreo. El enunciado completo,
la rúbrica y el mecanismo de peer review están en
[`proyecto/`](proyecto/README.md).

Los talleres de cada sesión son opcionales y funcionan como **bonus**: entregarlos
con juicio a lo largo del semestre puede sumar hasta 1.0 unidad a la nota final.
No entregarlos no resta.

Para elegir dataset hay una [lista ya verificada](proyecto/datasets-curados.md),
y en [`proyecto/starter-template/`](proyecto/starter-template/) hay un esqueleto
de repositorio para quien prefiera no arrancar de cero.

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
