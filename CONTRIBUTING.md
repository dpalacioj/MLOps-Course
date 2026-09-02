# Guia de Contribucion

Este repositorio es un fork de [CamilaCortex/MLOps_UdM](https://github.com/CamilaCortex/MLOps_UdM).
Las instrucciones a continuacion documentan el flujo de trabajo para desarrollar sobre **este fork**
sin afectar el repositorio original.

---

## Remotes

| Remote | Repositorio | Uso |
|--------|------------|-----|
| `origin` | `dpalacioj/MLOps-Course` | Tu fork — aqui haces push |
| `upstream` | `CamilaCortex/MLOps_UdM` | Repo original — para traer cambios de Camila |

Verificar configuracion:

```bash
git remote -v
```

## Sincronizar con el repo original

Cuando Camila publique cambios que quieras incorporar:

```bash
git fetch upstream
git merge upstream/main
```

O si prefieres traer solo commits especificos:

```bash
git fetch upstream
git cherry-pick <commit-hash>
```

## Crear ramas

Seguimos [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
Las ramas deben tener el formato `<tipo>/<descripcion-en-kebab-case>`:

```bash
# Ejemplos validos
git checkout -b feat/add-monitoring-module
git checkout -b fix/mlflow-tracking-bug
git checkout -b docs/update-readme

# Esto sera rechazado por el hook pre-push
git checkout -b mi-rama-nueva       # falta el tipo
git checkout -b feature/Add_Thing   # debe ser kebab-case en minusculas
```

Tipos permitidos: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`, `hotfix`, `release`

## Hacer commits

Los mensajes de commit deben seguir el formato:

```
<tipo>[scope opcional]: <descripcion>
```

```bash
# Ejemplos validos
git commit -m "feat: add monitoring module with Evidently"
git commit -m "fix(tracking): correct MLflow metric logging"
git commit -m "docs: update course overview"
git commit -m "feat!: redesign experiment pipeline"   # breaking change

# Esto sera rechazado por el hook commit-msg de pre-commit
git commit -m "updated stuff"
git commit -m "fix bug"           # falta el ':'  y la descripcion
```

El hook `commit-msg` de `pre-commit` valida automaticamente el formato.
Se instala con `make setup`.

## Crear Pull Requests

Por ser un fork, GitHub redirige los PRs hacia el repo de Camila por defecto.
Para crear PRs en **este fork**, siempre especificar `--repo`:

```bash
gh pr create \
  --repo dpalacioj/MLOps-Course \
  --base main \
  --head nombre-de-tu-rama \
  --title "tipo: descripcion del PR"
```

Si usas la interfaz web de GitHub, asegurate de cambiar el dropdown **"base repository"**
de `CamilaCortex/MLOps_UdM` a `dpalacioj/MLOps-Course` antes de crear el PR.

## Setup para nuevos clones

Si clonas este repo desde cero, configura los hooks y el upstream:

```bash
git clone git@github.com:dpalacioj/MLOps-Course.git
cd MLOps-Course
git remote add upstream https://github.com/CamilaCortex/MLOps_UdM.git
make setup   # instala dependencias y los hooks de pre-commit
```

---

## Convenciones del curso

Se fijaron en el rediseño de agosto de 2026. Antes no había convención y la
inconsistencia era visible: unos documentos con tildes y emojis, otros sin
tildes; nombres de archivo en `Readme.md`, `README.md`, `GUIA_VISUAL.md` y
`ejercicio-setup.md` conviviendo; el puerto de MLflow en 5000 en unos archivos y
5001 en otros.

### Idioma

- **Prosa en Markdown: español con acentuación completa.**
- **Python: sin tildes** en docstrings, comentarios y strings. Es una concesión
  deliberada a la portabilidad de encoding entre Windows, macOS y Linux.
- **Términos técnicos en inglés, sin traducir, y en `código`**: flow, task,
  deployment, drift, tracking, registry, gate, lockfile, digest, healthcheck.
- **Sin emojis en material evaluable.** Son ruido para lectores de pantalla y no
  aportan información.

### Nombres de archivo

`kebab-case` en ASCII. Sin mayúsculas salvo los archivos convencionales de la raíz
(`README.md`, `CONTRIBUTING.md`, `Makefile`, `Dockerfile`).

### Puertos

| Servicio | Puerto |
|---|---|
| MLflow | **5001** |
| Prefect | 4200 |
| API de inferencia | 8000 |
| MinIO (consola) | 9001 |
| Prometheus | 9090 |
| Grafana | 3000 |

El 5001 para MLflow no es capricho: en macOS el 5000 lo ocupa AirPlay Receiver.
Está fijado en `src/taxi/config.py` y en `.env.example`, y ese es el único lugar
donde se declara.

### Estructura de todo README de sesión

1. `## Objetivos` — en verbos observables y verificables, no "entender X".
2. El **por qué** antes de la herramienta.
3. Los bloques de contenido.
4. `## Autoverificación` — 4 o 5 preguntas.
5. `## Qué NO usar` — APIs deprecadas y herramientas estancadas, **con fecha**.

### Tablas comparativas

Declaran **criterio de evaluación, fecha y un enlace a la documentación oficial
por fila**. Una tabla que asigna "complejidad de setup: baja/media/alta" sin decir
cuándo se evaluó ni contra qué no es auditable, y en un curso de posgrado eso
importa.

### Ejercicios

Todo ejercicio tiene **criterios de completitud medibles** y una **solución de
referencia** en `_soluciones/`. El modelo a seguir es
`sesiones/s03-tracking/exercises/`, con su tabla de criterios.

### Notebooks

- Se commitean **sin outputs**. El hook `nbstripout` lo aplica.
- No definen lógica: la importan de `src/taxi`. El notebook es exploración y
  narrativa; la lógica vive en el paquete, donde se puede testear.
- Sin `attachments` en base64.

### Datos y artefactos

- **Nunca** commitear modelos ni datasets. El modelo se obtiene del registry
  (`models:/nyc-taxi-duration@champion`) o se regenera con `make train`. El hook
  `check-added-large-files` bloquea archivos de más de 500 KB.
- Los datos se descargan con `make data`, que verifica SHA-256 y escribe la
  procedencia en `data/raw/metadata.json`.

### Hooks propios

Además de ruff, gitleaks y nbstripout, hay dos verificaciones locales:

| Hook | Qué bloquea |
|---|---|
| `sin-rutas-absolutas` | `/Users/…`, `/home/…`, `C:\Users\…`. El repo tenía la ruta del disco de la autora original en `prefect.yaml`, lo que hacía fallar `prefect deploy` en cualquier otra máquina |
| `mlflow-sin-stages` | `transition_model_version_stage`, `models:/<n>/Production`, `artifact_path=`, `mean_squared_error(squared=False)`. El curso enseña aliases y tags; el código debe ser coherente con eso |

Si necesitas mostrar una API deprecada como contraejemplo, márcalo explícitamente
y añade la ruta al `exclude` del hook, explicando por qué.

### Antes de abrir un PR

```bash
make check    # ruff + mypy + tests (lo mismo que el CI)
make smoke
```

Regla de contenido, aprendida de los 1.385 líneas de guía que documentaban código
inexistente: **ningún markdown nuevo describe código que no esté en el repositorio
y cubierto por el nightly.**
