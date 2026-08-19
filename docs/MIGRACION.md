# Mapa de migración — qué pasó con cada carpeta

Este documento existe para una pregunta concreta: **¿se borró algo mío?**

**Respuesta corta: no.** Nada se perdió. Todo lo que había en `main` sigue en la
historia de git y se recupera con un comando. Lo que cambió es *dónde* vive cada
cosa y, en varios casos, su contenido.

---

## Primero, lo tranquilizador

La rama `refactor/rediseno-curso-8-sesiones` **no toca `main`**. Para volver a
donde estabas:

```bash
git checkout main
```

Y para recuperar cualquier archivo individual de la versión anterior, estés en la
rama que estés:

```bash
# Ver un archivo como estaba en main
git show main:03-Orchestration/Prefect-pipelines/pipeline.py

# Traerlo de vuelta al working tree
git checkout main -- 03-Orchestration/Prefect-pipelines/pipeline.py

# Ver el historial completo de algo que se movió (git sigue los renames)
git log --follow -- sesiones/s04-orquestacion/README.md
```

Los movimientos se hicieron con `git mv` donde fue posible, así que git los
reconoce como *renames* y el historial de cada archivo sigue intacto.

---

## Los números

| Tipo de cambio | Archivos |
|---|---|
| Nuevos | 276 |
| Movidos o renombrados (git lo detecta como rename) | 33 |
| Reescritos (git los cuenta como borrado + nuevo porque el contenido cambió mucho) | ~120 |
| Eliminados a propósito, sin sucesor | 16 |
| Modificados en el sitio | 6 |

La cifra que importa es la penúltima: **16 archivos** se eliminaron de verdad, y
cada uno con una razón que está más abajo. El resto tiene un sucesor.

---

## Mapa carpeta por carpeta

### `00-Setup/` → `sesiones/s01-reproducibilidad/`

Los 13 documentos numerados más `Resumen.md` y
`01-Intro-ML/clase-entornos-virtuales/README.md` (437 líneas que duplicaban a
tres de los otros) se **consolidaron en cuatro**:

| Antes | Ahora |
|---|---|
| `02-python-envs.md`, `02.1-uv-conda-venv.md`, `03-dependency-management.md`, `clase-entornos-virtuales/README.md` | `entorno.md` |
| `01-git-github.md`, `01.1-conventional-commits.md`, `10-git-lfs.md` | `git.md` |
| `04-tooling.md`, `08-pre-commit.md`, `06-github-actions.md`, `09-cicd-guide.md` | `calidad.md` |
| `07-os-notes.md`, `Resumen.md` | `troubleshooting-so.md` |
| `05-data-and-secrets.md` | repartido entre `entorno.md` y `calidad.md` |

`scripts/` y `templates/` se conservan. Se añadió `notebooks/`, `taller.md`,
`_soluciones/` y `.devcontainer/` en la raíz.

### `01-Intro-ML/` → repartido entre S01 y S02

| Antes | Ahora |
|---|---|
| `01_mlops_intro_notebook.ipynb` | absorbido en `sesiones/s01-reproducibilidad/notebooks/01-del-notebook-al-paquete.ipynb` |
| `02_regression_temporal_notebook.ipynb` | `sesiones/s02-datos/notebooks/02-validacion-temporal-y-leakage.ipynb` |
| `generate_demand_data.py` | `sesiones/s02-datos/notebooks/generate_demand_data.py` |
| `generate_data.py` | **eliminado** (ver abajo) |

### `02-Experiment-Tracking/` → `sesiones/s03-tracking/`

Todo el contenido está, con nombres en kebab-case y los notebooks actualizados a
la API vigente de MLflow 3.15:

| Antes | Ahora |
|---|---|
| `notebooks/01_first_steps_without_tracking.ipynb` | `notebooks/01-sin-tracking.ipynb` |
| `notebooks/02_experiment_tracking_intro.ipynb` | `notebooks/02-tracking-con-mlflow.ipynb` |
| `notebooks/03_mlflow_advanced.ipynb` | `notebooks/03-hpo-y-registry.ipynb` |
| `scripts/train_no_mlflow.py` | `scripts/train-sin-mlflow.py` |
| `scripts/train_with_basic_mlflow.py` | `scripts/train-mlflow-basico.py` |
| `scripts/train_with_full_mlflow.py` | `scripts/train-mlflow-completo.py` |
| `scenarios/scenario-1/2/3.ipynb` | `scenarios/scenario-1-file-store.ipynb`, `-2-server-local`, `-3-aws` |
| `notebooks/00_data_preparation.ipynb` + `scripts/preprocess_data.py` | **eliminados**: eran dos rutas de preprocesamiento incompatibles para el mismo problema. Ahora hay una sola, en `src/taxi/data/` |

### `03-Orchestration/` → `sesiones/s04-orquestacion/`

| Antes | Ahora |
|---|---|
| `00-intro-prefect/` | `00-intro-prefect/` (misma progresión didáctica, con 12 bugs corregidos) |
| `Prefect-pipelines/src/` | reimplementado en `src/taxi/flows/` y `src/taxi/models/` |
| `Prefect-pipelines/ejercicio/` | `01-pipeline-ml/ejercicio/` (convertido en ejercicio real, ver abajo) |
| `diagrams/` | `diagrams/` (intactos, siguen en Git LFS) |
| `Mage-pipelines/` | **eliminado** (ver abajo) |

### `04-Deployment/` → `sesiones/s05-deployment/` y `sesiones/s06-cloud-cicd/`

| Antes | Ahora |
|---|---|
| `deploy/web-service/` (la API) | reimplementado en `src/taxi/api/` |
| `deploy/web-service/*.postman_*.json` | `sesiones/s05-deployment/postman/` |
| `deploy/batch-deploy/` | reimplementado en `src/taxi/flows/batch.py` |
| `deploy/intro-dockers/` | `sesiones/s05-deployment/intro-dockers/` (actualizado a `uv`) |
| `deploy/web-service-aws/` | `sesiones/s06-cloud-cicd/_contraejemplo-insegure-aws/` (se conserva **como contraejemplo de seguridad documentado**) |
| `deploy/web-service/GUIA_USO.md` | `referencia/deployment-guia-uso.md` (material opcional) |
| `deploy/intro-dockers/COMANDOS_DOCKER.md` | `referencia/docker-comandos.md` (material opcional) |

### `05-Monitoring/` → `sesiones/s07-monitoreo/`

El README de 205 líneas se reescribió completo y se le agregó lo que no existía:
código ejecutable (`src/taxi/monitoring/`), dos notebooks, plantillas y un
documento de gobernanza.

### `Project/` → `proyecto/`

`Readme.md` → `README.md` (reescrito) y `peer-review-template.md` (reescrito). Se
añadió `rubrica-instructor.md`, `datasets-curados.md`,
`mvp-minimo-aprobable.md` y `starter-template/`.

### `markdowns/` → repartido

| Antes | Ahora |
|---|---|
| `GUIA_CLASE_ORQUESTACION.md` | `instructor/guion-s04-orquestacion.md` |
| `GUIA_INTEGRACION_MLOPS.md` | `docs/cierre-del-curso.md` |
| `GUIA_VISUAL.md` | **eliminado** (ver abajo) |
| `GUIA_MAGE_PASO_A_PASO.md` | **eliminado** (ver abajo) |

### `COURSE_OVERVIEW.md` → `docs/auditoria-2026-04.md`

Se archivó en lugar de borrarse. Era un *snapshot* de auditoría de abril y estaba
obsoleto: referenciaba ~14 archivos inexistentes y afirmaba cosas falsas sobre el
estado del repo (decía que no había `.pre-commit-config.yaml` ni `.env.example`,
y ambos existían).

---

## Los 16 archivos eliminados sin sucesor, y por qué

### 1. `markdowns/GUIA_VISUAL.md` (510 líneas)

Las 13 imágenes que referenciaba apuntaban a `04-Deployment/guia-visual/img/*.svg`,
una carpeta que **nunca existió en el repo**. Sin las figuras, el documento es solo
texto de pie de figura.

> Recuperarlo: `git show main:markdowns/GUIA_VISUAL.md`

### 2. `markdowns/GUIA_MAGE_PASO_A_PASO.md` (875 líneas) y `03-Orchestration/Mage-pipelines/` (9 archivos)

Documentaba un pipeline que no se podía ejecutar. Dos motivos independientes:

- El DAG de Mage vive en `metadata.yaml`, y el `.gitignore` anterior ignoraba
  `*.yaml` globalmente. Los archivos **nunca estuvieron versionados**, así que
  `mage start` abría un proyecto vacío.
- `setup_and_run.sh:57` invocaba `mage_ai.run(...)`, una API que no existe en el
  paquete `mage-ai`.

Además, la última release open source de Mage es de enero de 2026 y el foco
comercial se movió a Mage Pro. Mantener un entorno aislado para eso no se
justifica en 32 horas de clase.

**Lo que sí se conservó:** el notebook de comparación de orquestadores se evaluó
y también se eliminó, porque sus celdas leían el proyecto Mage inexistente. La
comparación de orquestadores ahora vive como tabla en
`sesiones/s04-orquestacion/README.md`, con criterio, fecha de evaluación y enlace
oficial por fila.

> Recuperarlo: `git checkout main -- 03-Orchestration/Mage-pipelines markdowns/GUIA_MAGE_PASO_A_PASO.md`

### 3. `01-Intro-ML/generate_data.py`

Línea 145: `df["dar_promocion"] = random.choices([0, 1], k=len(df))`. El target era
**ruido puro**, sin relación con las features. Se enseñaba un flujo completo de
clasificación sobre un problema sin señal, lo que hace imposible discutir
honestamente overfitting, feature importance o umbrales.

Su función pedagógica la cumple ahora el target binario derivado del caso guía
(`viaje_largo = duration > 30`), que sí tiene señal real.

### 4. Artefactos binarios (9 archivos)

`model.ubj` y `preprocessor.b` estaban duplicados **tres veces** en el repo
(Prefect-pipelines, web-service, batch-deploy), más `lin_reg.bin` y
`models/registered/v1_20260407_152831/`. Uno de ellos tenía la ruta del disco de
la autora original dentro del propio archivo `MLmodel`.

Commitear el modelo *es* el anti-patrón que el curso enseña a evitar: el
artefacto se obtiene del registry (`models:/nyc-taxi-duration@champion`) o se
regenera con `make train` en menos de un minuto.

### 5. Los tres PNG de resultados en `02-Experiment-Tracking/notebooks/`

`residuals_rf.png`, `true_vs_pred.png`, `feature_importance_rf.png` duplicaban lo
que MLflow ya guarda como artifact. Se generan al ejecutar.

### 6. `copy_model.py` (dos archivos) y `queries_batch_predictions`

Los `copy_model.py` promovían modelos con `shutil.copytree` en cadena entre
módulos, en lugar de usar el alias del registry. Contradecían la sesión 3
completa. Uno de ellos apuntaba a `03-Orchestration/Prefect-pipelines`, ruta que
ya no existe.

`queries_batch_predictions` (sin extensión) usaba `#` como comentario SQL, que
**no es válido en SQLite**. Su reemplazo está en
`sesiones/s04-orquestacion/01-pipeline-ml/consultas-predicciones.sql`.

---

## Dos cosas que cambiaron de contenido y conviene que sepas

### El falso ejercicio de Prefect

`Prefect-pipelines/ejercicio/ejercicio_pipeline_clasificacion.ipynb` se titulaba
"Ejercicio Guiado" y **todas** sus celdas eran `%%writefile` con el código ya
completo: era copiar y pegar, no un ejercicio. Peor: ejecutado con el directorio
de trabajo equivocado, **sobreescribía el pipeline real**.

Ahora es un ejercicio de verdad, con cuerpos de función vacíos, TODOs numerados y
criterios de aceptación, en `sesiones/s04-orquestacion/01-pipeline-ml/ejercicio/`.

### El `.gitignore`

Se reescribió. El anterior ignoraba globalmente `*.json`, `*.yaml`, `*.yml`,
`*.txt`, `*.html`, `Dockerfile` y `docker-compose.yml`. Consecuencias reales:

- El `metadata.json` de los modelos no se versionaba, y por eso el servicio web y
  el pipeline batch no podían cargar el modelo.
- El DAG de Mage nunca llegó al repo.
- Un `Dockerfile` nuevo no se habría agregado nunca.

**Efecto para ti:** archivos tuyos que antes estaban ignorados pueden aparecer
ahora como sin trackear. `comandos-de-clase-github.txt` es el caso típico: lo
ignoraba la regla global `*.txt`. No es un error, es la regla vieja dejando de
esconder cosas.

---

## Qué es nuevo

Lo que no existía antes y ahora sí:

| Ruta | Qué es |
|---|---|
| `src/taxi/` | El paquete del caso guía: configuración, contratos de datos, features, entrenamiento, registry, API, flows y monitoreo. Una sola implementación en lugar de tres incompatibles |
| `tests/` | 308 tests (antes había cero de verdad) |
| `scripts/smoke_test.py` | Verifica el entorno en segundos y dice qué arreglar |
| `scripts/promote.py` | El gate de promoción |
| `Makefile` | La interfaz única del repo; el CI usa los mismos targets |
| `Dockerfile`, `docker-compose.yml`, `observabilidad/` | Stack local con MLflow, Postgres, MinIO, Prometheus y Grafana |
| `.github/workflows/` | CI que puede fallar, CD con gate, nightly end-to-end, evals de LLM |
| `sesiones/s08-llmops/` | Sesión nueva completa |
| `proyecto/rubrica-instructor.md` | Era el 70 % de la nota y no existía en el repo |
| `proyecto/starter-template/` | Scaffold de 46 archivos con CI verde desde el primer commit |
| `instructor/guion-s0X-*.md` | Ocho guiones de clase con bloques minutados |
| `docs/adr/` | Siete decisiones de arquitectura documentadas |
| `.devcontainer/` | Plan B para los estudiantes cuyo setup falla |

---

## Si algo no te gusta

Los cinco commits están separados por tema, así que puedes revertir uno sin tocar
el resto:

```bash
git log --oneline main..refactor/rediseno-curso-8-sesiones

# Revertir solo la reestructuración de carpetas, por ejemplo
git revert --no-commit 649df8f
```

O revisar commit por commit antes de mezclar:

```bash
git show 649df8f --stat    # reestructuración y poda
git show 2e7fe95 --stat    # paquete taxi, contratos, CI
git show 61d9d49 --stat    # entrenamiento, gate, API, flows
git show 1bda45a --stat    # sesiones 7 y 8, proyecto final
git show 1f907d3 --stat    # material de las sesiones 1, 3, 5 y 6
```
