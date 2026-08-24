# Calidad automática: `ruff`, `mypy`, `pre-commit`, `nbstripout` y CI

> **Bloque B de la sesión 1**, segunda mitad (140-165 min).
> **Fecha de revisión:** agosto de 2026. Verificado en esta máquina:
> `ruff 0.16.3`, `mypy 2.3.1`, `pre-commit 4.6.2`, `nbstripout 0.9.1`.
> Referencias oficiales: [docs.astral.sh/ruff](https://docs.astral.sh/ruff/) ·
> [mypy.readthedocs.io](https://mypy.readthedocs.io/) ·
> [pre-commit.com](https://pre-commit.com/).

Este documento reemplaza a `04-tooling.md`, `08-pre-commit.md`,
`06-github-actions.md` y `09-cicd-guide.md`. Los cuatro explicaban las mismas
herramientas y **se contradecían** en la más importante: dos recomendaban Black
junto con Ruff. Aquí hay una sola respuesta y está argumentada.

---

## 1. La regla que ordena todo el documento

> **El `hook` local y el CI ejecutan exactamente lo mismo.**

Si divergen pasa esto, en este orden: (1) el `hook` aprueba algo que el CI rechaza;
(2) la gente descubre `--no-verify`; (3) el `hook` deja de existir en la práctica;
(4) el CI se convierte en el sitio donde te enteras, quince minutos después, de un
error que podías haber visto en tres segundos.

Por eso [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) y
[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) de este repositorio
corren los mismos comandos, y el `Makefile` los expone con un solo nombre:

```bash
make check     # = lint + typecheck + test-fast. Lo mismo que el CI, en local
```

---

## 2. Ruff: lint **y** formato, y por qué no se mezcla con Black

Ruff hace dos trabajos distintos con el mismo binario:

```bash
uv run ruff check .              # LINT: encuentra errores, imports sin usar, bugs
uv run ruff check --fix .        # y los corrige donde puede
uv run ruff format .             # FORMATO: reescribe el estilo, de forma determinista
uv run ruff format --check .     # solo comprueba. Es lo que corre el CI
```

La configuración vive en [`pyproject.toml`](../../pyproject.toml), no en un archivo
aparte, y las familias de reglas están elegidas a propósito:

```toml
[tool.ruff.lint]
select = [
    "E",    # pycodestyle
    "F",    # pyflakes        -> imports sin usar, variables sin definir
    "I",    # isort           -> orden de imports (reemplaza isort)
    "UP",   # pyupgrade       -> sintaxis moderna para tu target-version
    "B",    # bugbear         -> bugs reales, no estilo
    "SIM",  # simplify
    "C4",   # comprehensions
    "RUF",  # reglas propias de ruff
]
```

`B` (bugbear) merece un comentario porque es la que aporta más: no comprueba estilo,
comprueba **bugs**. El clásico es `B006`, un argumento por defecto mutable
(`def f(xs=[])`), que en un pipeline de datos produce un error que aparece en la
segunda llamada y no en la primera.

### Por qué **no** Black y Ruff a la vez

La documentación de Ruff lo dice así, textualmente:

> "While the formatter is designed to be a drop-in replacement for Black, it is not
> intended to be used interchangeably with Black on an ongoing basis, as the
> formatter *does* differ from Black in a few conscious ways."
> — [docs.astral.sh/ruff/formatter](https://docs.astral.sh/ruff/formatter/)

Es decir: es un reemplazo, no un compañero. Las diferencias son pocas —Ruff formatea
las expresiones dentro de las llaves de un f-string, Black no— pero **una sola línea
distinta es suficiente** para el escenario que arruina un PR:

1. tú guardas con `ruff format` (el `hook`);
2. tu compañero guarda con la extensión "Black Formatter" de VS Code y
   `formatOnSave`;
3. cada `push` reformatea archivos que nadie tocó;
4. el diff del PR tiene cientos de líneas de ruido y la revisión se vuelve
   imposible;
5. y el CI, que corre `ruff format --check`, está **rojo para los dos**.

Eso responde la autoverificación nº 4 del README. La decisión de este repositorio
está escrita en dos sitios, para que no se pierda:
[`pyproject.toml`](../../pyproject.toml) (`# NO mezclar con Black`) y
[`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) (`# NO agregar Black
aquí`).

**Matiz honesto:** nada de esto significa que Black sea malo, ni que haya que
migrar un proyecto que ya lo usa y funciona. Black es excelente y sigue mantenido.
Lo que no se puede es tener **los dos a la vez**. Elige uno por repositorio y
déjalo escrito.

### Notebooks y material didáctico

`extend-exclude` saca los notebooks del lint, y hay una excepción declarada:

```toml
[tool.ruff.lint.per-file-ignores]
"sesiones/**" = ["E402"]  # material didáctico: imports después de prosa
```

Es una decisión, no un descuido: en un notebook o en un documento de clase, poner el
`import` justo donde se explica es mejor pedagogía que agruparlos todos arriba. El
comentario que dice por qué está en el archivo, que es donde alguien lo va a leer.

---

## 3. `mypy`: tipos donde importan

```bash
uv run mypy          # usa la config de pyproject.toml
```

```toml
[tool.mypy]
python_version = "3.11"
files = ["src/taxi", "scripts"]   # solo el código de producción
disallow_untyped_defs = true      # aquí sí: toda función anotada
ignore_missing_imports = true     # el ecosistema de ML no está todo tipado

[[tool.mypy.overrides]]
module = ["tests.*", "sesiones.*"]
disallow_untyped_defs = false     # en tests y material, no
```

**La decisión importante es el alcance.** Tipar el 100 % de un repositorio de ML es
una batalla perdida: `pandas`, `mlflow` y media docena más no tienen `stubs`
completos. Tipar `src/` con `disallow_untyped_defs` y dejar tests y notebooks fuera
compra el 90 % del beneficio por el 20 % del esfuerzo.

Qué te da de verdad en un pipeline de datos: `mypy` atrapa el `None` que se propaga
tres funciones más abajo, la firma que cambiaste sin actualizar a los dos llamantes,
y el `dict[str, float]` que en realidad recibe `str`. No atrapa lo que la mayoría
espera: **no** valida el contenido de un `DataFrame`. Que `df` sea de tipo
`pd.DataFrame` no dice nada de sus columnas ni de sus rangos. Eso es lo que hace un
contrato de datos, y es la sesión 2.

---

## 4. `nbstripout`: notebooks sin `outputs`

```yaml
- repo: https://github.com/kynan/nbstripout
  rev: 0.8.1
  hooks:
    - id: nbstripout
```

Tres razones para quitar los `outputs` antes de commitear, en orden de gravedad:

1. **Filtran información del entorno de quien ejecutó.** Rutas absolutas, nombres de
   usuario, ocasionalmente tokens impresos por accidente. En el material anterior de
   este curso, los `outputs` de tres notebooks contenían la ruta del disco de la
   autora original.
2. **Hacen el diff ilegible.** Un `output` es JSON con base64. Cambiar una celda de
   texto produce un diff de 400 líneas y el PR no se puede revisar.
3. **Engordan el repositorio.** El notebook `01-panorama-mlops.ipynb` pesaba 175 KB
   para 33 celdas, de los cuales ~82 KB eran **una** imagen pegada en base64 en el
   campo `attachments` de una celda de markdown.

Compruébalo tú, en cualquier notebook del repositorio:

```bash
uv run python -c "
import nbformat, pathlib
p = pathlib.Path('sesiones/s02-datos/notebooks/02-validacion-temporal-y-leakage.ipynb')
nb = nbformat.read(p, as_version=4)
print('KB:', p.stat().st_size // 1024, '| celdas:', len(nb.cells))
print('celdas con outputs:', sum(1 for c in nb.cells if c.get('outputs')))
print('celdas con attachments:', sum(1 for c in nb.cells if 'attachments' in c))
"
```

**Consecuencia práctica:** el notebook que commiteas no lleva resultados. Si un
resultado importa —una tabla, una métrica— no lo dejes en un `output`: escríbelo en
una celda de markdown, o guárdalo como artefacto en `reports/`. Y para versionar la
**fuente** de un notebook complejo, el patrón de este repositorio es un generador
(`_generar_notebooks.py`): un `.py` revisable en un PR que produce el `.ipynb`.

---

## 5. `pre-commit`: el guardián, y qué comprueba de verdad

Un `hook` es un script que Git ejecuta automáticamente en un momento concreto.
`pre-commit` gestiona esos scripts, los instala en entornos aislados y los ejecuta
**solo sobre los archivos en `staging`** (no sobre todo el repositorio), que es lo
que lo mantiene rápido.

```bash
uv run pre-commit install --install-hooks         # ya lo hace `make setup`
uv run pre-commit install --hook-type commit-msg
uv run pre-commit run --all-files                 # la primera vez, o cuando dudes
uv run pre-commit run ruff-format --all-files     # un hook concreto
uv run pre-commit autoupdate                      # sube los `rev` de los repos
```

Los `hooks` de este repositorio, agrupados por lo que protegen:

| Grupo | `Hooks` | Qué evita |
|---|---|---|
| Higiene | `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-json`, `check-merge-conflict`, `check-case-conflict`, `mixed-line-ending --fix=lf` | diffs de ruido, YAML roto que solo se descubre en CI, marcadores `<<<<<<<` olvidados, y el clásico de Windows/macOS: dos archivos que difieren solo en mayúsculas |
| Tamaño | `check-added-large-files --maxkb=500` | binarios en el historial. El límite es 500 KB porque en el repositorio anterior había tres artefactos de modelo commiteados |
| Secretos | `detect-private-key`, `gitleaks` | una clave privada o un token en el historial. **Esto es lo que no se puede deshacer** |
| Estilo | `ruff-check --fix`, `ruff-format` | lo de §2 |
| Notebooks | `nbstripout` | lo de §4 |
| Mensajes | `conventional-pre-commit` (etapa `commit-msg`) | historial ilegible |
| Propios del curso | `sin-rutas-absolutas`, `mlflow-sin-stages`, `mypy-src` | ver abajo |

### Los tres `hooks` propios, y por qué existen

No son adorno: cada uno codifica un bug que costó tiempo de clase.

- **`sin-rutas-absolutas`**
  ([`scripts/hooks/sin_rutas_absolutas.py`](../../scripts/hooks/sin_rutas_absolutas.py))
  bloquea rutas de usuario tipo `/Users/<alguien>/` o `C:\Users\<alguien>`. Motivo
  real: el `prefect.yaml` del módulo de orquestación tenía
  `set_working_directory` apuntando al disco de quien lo escribió, y
  `prefect deploy --all` fallaba en cualquier otra máquina. Es el error que no rompe
  nada para el autor y lo rompe todo para el resto.
- **`mlflow-sin-stages`** bloquea `transition_model_version_stage` y
  `models:/<nombre>/Production`. El curso enseña `aliases` + `tags`
  ([ADR 002](../../docs/adr/002-aliases-en-vez-de-stages.md)); si el código usara la
  API deprecada, el material y el repositorio dirían cosas distintas.
- **`mypy-src`** corre `mypy` sobre `src/taxi` y `scripts`, con
  `pass_filenames: false` para que analice el proyecto completo y no archivo por
  archivo (el análisis de tipos necesita ver el todo).

### Cuando un `hook` falla

```
$ git commit -m "feat: add drift check"
ruff-check...............................................................Failed
- hook id: ruff-check
- files were modified by this hook
```

El `hook` **corrigió** el archivo y el commit no se hizo. No es un castigo: el
arreglo ya está aplicado en tu disco. Revísalo y vuelve a intentar:

```bash
git diff          # mira qué te cambió: es tu responsabilidad, no del hook
git add -A
git commit -m "feat: add drift check"
```

**Sobre `--no-verify`.** Sí, existe. Y si lo estás usando de forma habitual, el
problema no eres tú: es que los `hooks` tardan demasiado o comprueban algo distinto
del CI. Arregla eso, en lugar de convivir con un guardián al que has aprendido a
esquivar.

---

## 6. CI: el mismo comando, en una máquina limpia

El CI no es "otra herramienta": es **tus comandos, en una máquina que no es la
tuya**. Ahí está todo su valor, porque elimina la variable "algo que instalé hace
seis meses y ya no recuerdo".

El [workflow de este repositorio](../../.github/workflows/ci.yml) tiene cinco
`jobs`, y conviene ver qué añade cada uno:

| `Job` | Qué corre | Qué protege |
|---|---|---|
| `calidad` | `ruff check`, `ruff format --check`, `mypy` | lo mismo que tus `hooks` |
| `tests` | `pytest -m "not slow and not integration"` con cobertura, en **ubuntu y windows** | Windows está en la matriz a propósito: buena parte de los fallos de esta sesión eran específicos de esa plataforma |
| `smoke` | `scripts/smoke_test.py --rapido`, con `checkout` **`lfs: true`** | que el entorno del curso se pueda reconstruir, y que los punteros LFS se resuelvan |
| `secretos` | `gitleaks-action` con `fetch-depth: 0` | secretos en **todo el historial**, no solo en el último commit |
| `imagen` | `docker build`, y luego comprueba que **no corre como root** y que `/health` responde | que una imagen verde en CI sea una imagen que arranca (S05) |

Dos detalles del `header` que merecen mirarse:

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

Cancela el `run` anterior de la misma rama. Sin esto, cinco `pushes` seguidos
ocupan cinco `runners` calculando resultados que a nadie le importan.

Y el comentario que encabeza el archivo, que es la lección del `job`:

```
# El CI anterior terminaba en:
#     uv run pytest -q || echo "No tests configured yet"
# Un pipeline que no puede fallar es peor que no tener pipeline: produce
# confianza injustificada.
```

Ese `|| echo` es el anti-patrón más caro de todos: el paso siempre salía verde, así
que nadie se enteró de que el repositorio tenía 50 errores de `ruff` y 67 archivos
sin formatear. **Un `step` que no puede fallar no es una comprobación, es
decoración.**

### CI mínimo para tu proyecto

Con `uv` (recomendado):

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  calidad:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
          cache-dependency-glob: uv.lock
      - run: uv sync --group dev --locked
      - run: uv run ruff check --output-format=github .
      - run: uv run ruff format --check --diff .
      - run: uv run mypy
      - run: uv run pytest -q
```

Con Poetry, si es tu stack:

```yaml
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pipx install poetry
      - run: poetry install --no-interaction
      - run: poetry run ruff check .
      - run: poetry run ruff format --check .
      - run: poetry run pytest -q
```

Tres reglas para los dos casos:

1. **`--locked`** (o `poetry install` con `poetry.lock` commiteado). Si el CI puede
   resolver dependencias por su cuenta, no está probando tu entorno.
2. **Sin `continue-on-error` y sin `|| echo`.** Si un paso no puede fallar, bórralo.
   Las plantillas del material anterior traían `continue-on-error: true` en el `step`
   de lint, que es exactamente el mismo error.
3. **Rápido.** Por debajo de cinco minutos, o nadie lo espera y todo el mundo
   mergea sin mirar. El `cache` de `setup-uv` es lo que lo consigue.

Y una vez que el CI es fiable, el paso que le da autoridad: en GitHub →
*Settings → Branches → Branch protection rules*, marcar los `checks` como
**requeridos**. Un CI que no bloquea el `merge` es una opinión.

---

## 7. VS Code, si es tu editor

Extensiones que se recomiendan y para qué sirven de verdad:

| Extensión | ID | Para qué |
|---|---|---|
| Python | `ms-python.python` | intérprete, `debugger`, notebooks |
| Pylance | `ms-python.vscode-pylance` | autocompletado y navegación (`Go to definition`) |
| Ruff | `charliermarsh.ruff` | lint y formato **en el editor**, con las reglas de tu `pyproject.toml` |
| GitLens | `eamodio.gitlens` | `blame` en línea: quién cambió esto y en qué commit |

### El intérprete: la pregunta que todos hacen

**"¿En qué ambiente ejecuto esto?"** La respuesta es siempre la misma: el `.venv`
que está **dentro del repositorio**, no el Python del sistema ni el `base` de
conda.

Cómo saber en cuál estás, y es lo único que hay que memorizar:

```bash
which python     # macOS y Linux
where python     # Windows
```

Si la ruta que imprime no termina en `MLOps-Course/.venv/bin/python`, estás en el
ambiente equivocado. Y la comprobación de fondo:

```bash
python -c "import taxi; print('ambiente correcto')"
```

Si eso falla con `ModuleNotFoundError`, el intérprete no es el del proyecto.

**La forma de no pensar nunca en esto:** prefija los comandos con `uv run`.

```bash
uv run pytest              # usa el .venv del proyecto, sin importar qué esté activado
uv run python scripts/smoke_test.py
```

Por eso todos los `targets` del `Makefile` llevan `uv run`: eliminan la clase
entera de errores de "lo ejecuté en el ambiente equivocado".

Un detalle que confunde: en la terminal puedes ver **dos** ambientes a la vez,
así:

```
(mlops-curso) (base) Mac:MLOps-Course usuario$
```

No está roto. Conda activó `base` al abrir la terminal y encima se activó el
`.venv` del proyecto. El que manda es el de la izquierda, el último activado.

Este repositorio trae `.vscode/settings.json` versionado, así que al abrir la
carpeta VS Code ya selecciona el intérprete correcto. Si aun así te lo pregunta:
`Cmd/Ctrl` + `Shift` + `P` → **Python: Select Interpreter** → el que diga
`./.venv`. Para un notebook, el selector de `kernel` está arriba a la derecha y
hay que apuntarlo al mismo `.venv`.

Los ajustes que trae el repositorio:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": { "source.fixAll.ruff": "explicit" }
  }
}
```

Y **desinstala o desactiva la extensión "Black Formatter"** en este proyecto. Con
`ruff` en `pre-commit` y Black en el editor tienes dos formatters peleándose por los
mismos archivos.

> En Windows la ruta del intérprete es `${workspaceFolder}/.venv/Scripts/python.exe`.

---

## 8. Autoverificación del bloque

1. `ruff check` y `ruff format` hacen cosas distintas. ¿Cuál de las dos puede
   cambiar el significado de tu código, y cuál solo su apariencia?
2. `mypy` pasa en verde y tu `pipeline` entrena con `trip_distance` en kilómetros.
   ¿Por qué no lo detectó? ¿Qué herramienta sí lo haría?
3. ¿Por qué `pre-commit` corre solo sobre los archivos en `staging`, y qué comando
   usas cuando eso no es suficiente?
4. Tu CI tiene `continue-on-error: true` en el paso de lint. ¿Qué te está diciendo
   ese CI cuando sale verde?
5. ¿Cuál de los `hooks` de este repositorio protege contra algo que **no se puede
   deshacer** después?

Siguiente: [`taller.md`](taller.md) · Consulta:
[`troubleshooting-so.md`](troubleshooting-so.md) · Volver: [README](README.md)
