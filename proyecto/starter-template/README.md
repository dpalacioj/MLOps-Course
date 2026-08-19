# TODO(estudiante) 21: nombre del proyecto

> Plantilla del proyecto final del curso de MLOps. **No es un ejemplo para mirar:
> es tu repositorio.** Cópiala, renómbrala y trabaja sobre ella.
>
> Está deliberadamente incompleta. Los `TODO(estudiante) NN` están numerados y son
> el trabajo real; el andamiaje (CI, `Makefile`, contratos, tests, Docker) ya
> funciona para que no gastes las primeras seis horas peleando con `tooling`.

---

## Empezar en cinco minutos

```bash
# 1. Copia la plantilla a tu propio repositorio (sin arrastrar el historial del curso)
cp -r proyecto/starter-template ../mi-proyecto-mlops
cd ../mi-proyecto-mlops
git init

# 2. Instala todo y genera el lockfile
make setup

# 3. Verifica el entorno. Esto es lo que va a correr quien te haga peer review.
make smoke

# 4. Los tests pasan desde el primer commit. Compruébalo.
make test

# 5. Primer commit — con uv.lock incluido
git add -A && git commit -m "chore: scaffold inicial del proyecto"
```

**`uv.lock` va en el primer commit.** El CI corre `uv sync --locked`, que falla si
el lock no está o no coincide con `pyproject.toml`. Es a propósito: es lo que
convierte "instalé las dependencias" en "cualquiera instala exactamente las
mismas".

---

## Renombrar el paquete

`miproyecto` es un placeholder. Cámbialo antes de escribir código propio, porque
después el `rename` toca el doble de archivos.

```bash
NUEVO=predictor_demanda        # snake_case, sin guiones ni tildes

git mv src/miproyecto "src/$NUEVO"
grep -rl 'miproyecto' --include='*.py' --include='*.toml' --include='*.yml' \
  --include='*.yaml' --include='*.md' --include='Makefile' --include='Dockerfile' . \
  | xargs sed -i "s/miproyecto/$NUEVO/g"

make check    # lint + tipos + tests. Si esto pasa, el rename quedó bien.
```

En macOS, `sed -i` necesita un argumento: `sed -i '' "s/.../.../g"`.

Revisa a mano que quedaron consistentes: `pyproject.toml` (`name`, `packages`,
`project.scripts`, `mypy.files`, `coverage.source`), `Dockerfile` (`CMD`),
`docker-compose.yml` y el `Makefile`.

---

## Qué hay aquí y por qué

```
pyproject.toml            deps + ruff + mypy + pytest en un solo archivo
uv.lock                   lo genera `make setup`. VA AL REPOSITORIO
Makefile                  interfaz única: el CI corre estos mismos targets
.pre-commit-config.yaml   ruff, gitleaks, nbstripout, archivos grandes
.github/workflows/ci.yml  lint -> tipos -> tests -> smoke -> secretos -> imagen
.env.example              qué variables hace falta configurar (sin secretos)
.gitignore                artefactos fuera; configuración dentro
Dockerfile                uv sync --locked, no-root, healthcheck sin curl
docker-compose.yml        MLflow con registry + la API

src/miproyecto/
  config.py               particiones FIJAS, semillas, umbrales. Fuente única
  data/contract.py        contrato de datos ejecutable (Pandera)
  data/loaders.py         descarga + hash + limpieza + split temporal
  features/contract.py    la ÚNICA definición de features del proyecto
  models/train.py         entrenamiento con tracking, signature e input_example
  models/promote.py       gate de promoción: política pura + escritura de alias
  api/schemas.py          contrato HTTP (Pydantic v2)
  api/main.py             FastAPI con lifespan; carga el modelo por alias
  monitoring/check_drift.py  drift como check con exit code, no como PDF

tests/unit/               config, gate de promoción, política de drift
tests/data/               contrato (acepta el bueno, RECHAZA el roto), features
tests/api/                contrato HTTP, /health, validación
tests/fixtures/           muestra válida y muestra rota A PROPÓSITO

scripts/smoke_test.py     verificación del entorno en un comando
notebooks/01_eda.ipynb    explora y narra; no define lógica
docs/                     ADR, dataset card, model card, contrato de la API,
                          política de reentrenamiento, riesgos
```

Tres propiedades del andamiaje que conviene no romper:

1. **Una sola definición de cada cosa.** Features en `features/contract.py`,
   constantes en `config.py`, hiperparámetros en `models/train.py:PARAMS`. Si un
   valor aparece dos veces, se van a desincronizar.
2. **La política se separa de la infraestructura.** El gate de promoción y el
   detector de `drift` son funciones puras; hablar con MLflow es otra función. Por
   eso los tests corren en dos segundos y sin servicios levantados.
3. **El CI no puede pasar por accidente.** Ningún paso termina en `|| true`.

---

## Los TODO, en orden

No están en orden de aparición en el código, sino en el orden en que conviene
hacerlos. Los números coinciden con los del código: `grep -rn "TODO(estudiante)"`.

### Antes del hito 1 (dato y baseline)

| # | Qué | Dónde |
|---|---|---|
| 01 | Renombrar el proyecto en `pyproject.toml` | `pyproject.toml` |
| 02 | Renombrar el paquete | `src/miproyecto/` |
| 03 | Adaptar toda la configuración a tu dataset | `config.py` |
| 04 | URL de la fuente real (200 sin autenticación) | `config.py` |
| 05 | Nombre del modelo registrado | `config.py` |
| 08 | Nombres de columnas: crudas y derivadas | `features/contract.py` |
| 09 | Definir el target (y no meterlo en las features) | `features/contract.py` |
| 10 | ≥6 reglas **no triviales** en el contrato de datos | `data/contract.py` |
| 11 | Lectura de tu formato real | `data/loaders.py` |
| 12 | Fuente y licencia en el metadata | `data/loaders.py` |
| 13 | Estrategia de imputación, por columna y justificada | `data/loaders.py` |
| 21 | Descripción del proyecto en una línea | `pyproject.toml` |
| 25 | Variables de entorno reales | `.env.example` |
| 26 | Verificaciones propias en el smoke test | `scripts/smoke_test.py` |
| 27 | EDA completo (5 secciones) | `notebooks/01_eda.ipynb` |
| 28 | ADR del stack | `docs/adr/000-stack.md` |
| 29 | Dataset card | `docs/dataset-card.md` |

### Antes del hito 2 (tracking, registry, pipeline)

| # | Qué | Dónde |
|---|---|---|
| 06 | Justificar la mejora mínima del gate | `config.py` |
| 14 | Estimador y métrica de tu problema, con baseline honesto | `models/train.py` |
| 30 | `scripts/model_card.py` que **genere** la model card | `docs/model-card.md` |

### Antes del hito 3 (deployment, CI/CD, gate)

| # | Qué | Dónde |
|---|---|---|
| 15 | Implementar el gate contra el `registry` | `models/promote.py` |
| 16 | Campos del contrato HTTP | `api/schemas.py` |
| 18 | Descripción del servicio en OpenAPI | `api/main.py` |
| 22 | Job del gate en el CI | `.github/workflows/ci.yml` |
| 23 | Etiquetas OCI de la imagen | `Dockerfile` |
| 24 | Apuntar la API a tu `@champion` | `docker-compose.yml` |
| 31 | Contrato de la API documentado | `docs/api-contract.md` |

### Antes de la entrega final (monitoreo y gobernanza)

| # | Qué | Dónde |
|---|---|---|
| 07 | Justificar el umbral de `drift` | `config.py` |
| 17 | Métricas Prometheus en la API | `api/main.py` |
| 19 | Umbral de `drift` justificado por escrito | `monitoring/check_drift.py` |
| 20 | Conectar el check de `drift` a tus particiones | `monitoring/check_drift.py` |
| 32 | Política de reentrenamiento | `docs/politica-de-reentrenamiento.md` |
| 33 | Registro de riesgos | `docs/riesgos.md` |

---

## Comandos

```bash
make            # lista todos los targets
make setup      # dependencias + uv.lock + pre-commit
make smoke      # verifica el entorno (un comando, esto corre tu revisor)
make data       # descarga y prepara las particiones de config.py
make train      # entrena y registra el candidato con alias @candidate
make promote    # gate: candidato vs @champion en el holdout fijo
make drift      # reporte de drift referencia vs producción simulada
make serve      # API en http://127.0.0.1:8000/docs
make test       # todos los tests
make check      # lint + tipos + tests (lo mismo que el CI)
make up / down  # stack local con docker compose
```

---

## Dos cosas que la rúbrica penaliza y son fáciles de evitar

1. **Un `.env` o una credencial en el repositorio.** No se arregla borrándola en el
   commit siguiente: queda en el historial. Se arregla rotando la credencial.
   `gitleaks` está en el `pre-commit` y en el CI justamente para que no llegue ahí.
2. **Un artefacto binario grande commiteado** (`model.pkl`, un `.parquet` de
   200 MB). El modelo se obtiene del `registry` por alias; los datos se descargan
   con `make data` y se verifican por hash. El hook `check-added-large-files` corta
   a 500 KB.

Y una que no penaliza pero cuesta la nota de reproducibilidad: **no commitear
`uv.lock`**.
