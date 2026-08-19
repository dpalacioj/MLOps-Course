# Taller S01 — Un repositorio que otra persona pueda reconstruir

**Duración:** 55 min en clase. Se entrega en clase.
**Sobre:** **tu propio** repositorio de proyecto, no el del curso.
**Entregable:** un PR hacia `main` de tu repositorio, con el CI **verde** y el
enlace al `run` pegado en la descripción.

---

## Contexto

Hoy no hay modelo. Hay una pregunta: **¿puede otra persona clonar tu repositorio y
llegar al mismo resultado que tú, sin preguntarte nada?**

Todo lo que construyas en las siete sesiones siguientes se apoya en esto. Un
`experiment tracking` impecable sobre un entorno irreproducible registra números que
no significan nada, porque no se sabe con qué versiones se calcularon.

El objetivo **no** es "usar `uv`". Es que tu repositorio tenga una interfaz única,
un entorno declarado y una comprobación automática que **pueda fallar**.

Este es también el andamio del [hito 1 del
proyecto](../../proyecto/README.md), que se entrega 5 días después de la sesión 2.
Lo que hagas hoy no es trabajo desechable.

---

## 1. El repositorio y el paquete instalable

Crea (o reutiliza) el repositorio de tu proyecto y dale forma de **paquete Python
instalable**, no de carpeta con scripts:

```
mi-proyecto/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── .gitattributes
├── .pre-commit-config.yaml
├── Makefile
├── README.md
├── docs/adr/000-stack.md
├── src/miproyecto/
│   ├── __init__.py
│   └── config.py
├── scripts/smoke_test.py
└── tests/
    └── test_config.py
```

Requisitos:

- `src/` layout (el paquete dentro de `src/`, no en la raíz). Evita el error de
  importar el código del directorio de trabajo en lugar del instalado, que es cómo
  se descubre que los tests pasaban por accidente;
- `[project.scripts]` con al menos un comando, o un `python -m miproyecto`
  funcionando;
- **`config.py` como única fuente de verdad** de rutas, semillas y particiones. Si
  una constante aparece en dos archivos, ya divergió. Mira
  [`src/taxi/config.py`](../../src/taxi/config.py) como referencia.

Puedes copiar el andamio de
[`proyecto/starter-template/`](../../proyecto/starter-template/), que ya tiene esta
forma.

## 2. El entorno, declarado y bloqueado

- `pyproject.toml` con `requires-python` y tus dependencias **con rangos**, no
  fijadas a una versión exacta;
- un grupo `dev` con al menos `ruff`, `pytest` y `pre-commit`;
- **`uv.lock` commiteado**, en el mismo commit que el `pyproject.toml`;
- el `README` dice, en las tres primeras líneas, cómo se reconstruye el entorno.

Si usas Poetry, sirve igual: `poetry.lock` commiteado y `poetry install` en el CI.
Lo que no vale es un `requirements.txt` hecho con `pip freeze`.

## 3. El `Makefile` como interfaz única

Mínimo cuatro `targets`, y el `help` por defecto:

```make
setup      instala dependencias y hooks
smoke      verifica el entorno (exit code != 0 si algo falla)
test       corre pytest
lint       ruff check + ruff format --check
```

El criterio: **el CI llama a estos mismos `targets`**. Si el CI ejecuta comandos
distintos de los tuyos, tienes dos definiciones de "está bien".

## 4. `smoke_test.py`: un diagnóstico que puede fallar

Escribe tu propio `scripts/smoke_test.py`. No copies el del curso: el tuyo tiene que
comprobar **tus** cosas. Mínimo cuatro verificaciones, y al menos una específica de
tu proyecto:

- versión de Python en el rango que declaraste;
- tus dependencias **importan de verdad** (no `pip list`: `import`);
- tu paquete es importable y sus constantes son coherentes;
- algo tuyo: que el `dataset` de muestra exista, que el puerto que usas esté libre,
  que una función clave devuelva lo esperado.

**Requisito duro:** `sys.exit(1)` si algo falla. Un diagnóstico que siempre sale
verde es decoración. Referencia:
[`scripts/smoke_test.py`](../../scripts/smoke_test.py).

## 5. `ruff`, `pre-commit` y notebooks limpios

- `[tool.ruff]` configurado en `pyproject.toml` (no un archivo aparte);
- `.pre-commit-config.yaml` instalado y corriendo, con **como mínimo**:
  `ruff-check`, `ruff-format`, `check-added-large-files`, `nbstripout`,
  `detect-private-key`;
- **un solo formatter.** Si encuentras Black en tu configuración o en tu editor,
  quita uno de los dos y escribe en el `README` cuál elegiste;
- `.gitignore` con `.venv/`, `.env`, datos y artefactos de modelo.

Copia la plantilla de [`templates/pre-commit-config.yaml`](templates/pre-commit-config.yaml)
y **lee los comentarios** antes de usarla.

## 6. Git LFS, antes del primer binario

Si tu proyecto va a versionar imágenes, diagramas o una muestra de datos binaria:

```bash
git lfs install
git lfs track "*.png"
git add .gitattributes && git commit -m "chore: track png with git lfs"
# y SOLO ahora, el binario
```

Si tu proyecto no tiene ningún binario, escribe en el `README` una línea diciendo
que no lo necesitas y por qué. Es una decisión válida; lo que no vale es no haberlo
pensado.

## 7. Dos tests que signifiquen algo

Mínimo dos, y no `assert True`. Ideas que sí valen:

- que tus constantes de `config.py` sean coherentes entre sí (que las particiones no
  se solapen, que la semilla esté fijada, que las rutas sean relativas);
- que una función tuya sea determinista: llamada dos veces con la misma entrada,
  devuelve exactamente lo mismo;
- que tu paquete se pueda importar sin efectos secundarios (que importarlo no
  descargue nada ni cree directorios).

Este último es un test que la gente descubre tarde y duele: si `import miproyecto`
hace una llamada de red, tus tests dependen de la red.

## 8. El CI

`.github/workflows/ci.yml` que corra, en una máquina limpia y desde el `lockfile`:
`lint`, `test` y `smoke`. Requisitos:

- instalación **desde el `lock`** (`uv sync --locked` o `poetry install`);
- **ni `continue-on-error` ni `|| true` ni `|| echo`** en ningún paso;
- se dispara en `push` a `main` y en `pull_request`.

Plantilla mínima en [`calidad.md`](calidad.md) §6.

## 9. El ADR del stack

`docs/adr/000-stack.md`, una página, con **tres secciones obligatorias**:
**contexto**, **decisión** y **consecuencias**. Y dentro:

- qué gestor de dependencias elegiste y **qué descartaste**, con una razón que no
  sea "es el más popular";
- una consecuencia **negativa** de tu decisión. Si no encuentras ninguna, no has
  entendido la decisión;
- versiones concretas de lo que elegiste.

Un ADR con `TODO` sin rellenar cuenta como ADR ausente.

---

## Criterios de aceptación

Se revisan en el PR, en este orden. Cada uno es una comprobación con un comando, no
una opinión. **Los seis primeros los verifica tu propio CI**: si tu workflow está
verde, están cumplidos.

| # | Criterio | Cómo se verifica |
|---|---|---|
| 1 | El **workflow del CI pasa** | el `check` del PR está verde y el enlace al `run` está en la descripción |
| 2 | `make smoke` sale **OK** | el `job` del CI que lo corre termina con exit code 0. Y con un fallo inyectado a propósito, devuelve distinto de 0 |
| 3 | `pytest` corre **≥ 2 tests** | la salida dice `2 passed` o más. `assert True` no cuenta: el revisor los lee |
| 4 | `ruff check` **sin errores** | `ruff check .` en el CI, y `ruff format --check .` sin diferencias |
| 5 | **Existe `uv.lock`** (o `poetry.lock`) y está commiteado | `ls uv.lock` y `git log --oneline -- uv.lock`. Además, el CI instala con `--locked` y pasa |
| 6 | El entorno se reconstruye **desde cero** | el `job` del CI parte de una máquina limpia: si pasa, está demostrado |
| 7 | El **ADR** tiene contexto, decisión y consecuencias | las tres secciones existen, con contenido, sin `TODO`, y las consecuencias incluyen al menos una negativa |
| 8 | El `Makefile` es la **interfaz única** | los comandos del CI son `make <target>`, no comandos sueltos distintos |
| 9 | **Un solo formatter** | no hay Black y `ruff format` a la vez, en el repositorio ni en la configuración del editor commiteada |
| 10 | **Sin secretos ni binarios grandes** | `.env` está gitignorado, existe `.env.example`, y `git ls-files -s` no muestra `.pkl`/`.bin`/`.parquet` fuera de LFS |

### Autocomprobación antes de abrir el PR

```bash
make lint
make test
make smoke ; echo "exit code: $?"      # tiene que ser 0
uv run pre-commit run --all-files
git status --short                      # tiene que estar limpio
ls -la uv.lock pyproject.toml .python-version docs/adr/000-stack.md
```

Y la prueba que de verdad decide, la única que simula a tu revisor:

```bash
cd /tmp && rm -rf verificacion && git clone <url-de-tu-repo> verificacion
cd verificacion && make setup && make smoke && make test
```

Si eso falla, tu proyecto no es reproducible **todavía**, por bien que se vea el
`README`. Es exactamente lo que hará quien te haga `peer review`.

---

## Si acabas antes

1. Añade `mypy` sobre `src/` con `disallow_untyped_defs = true` y deja el CI verde.
2. Añade Windows a la matriz de tests (`os: [ubuntu-latest, windows-latest]`) y
   arregla lo que se rompa. Te vas a llevar una sorpresa con las rutas.
3. Añade el `hook` de `conventional commits` en la etapa `commit-msg`.
4. Protege `main` en *Settings → Branches*: `checks` requeridos y sin `push`
   directo. Es lo que convierte tu CI de una opinión en una regla.
5. Escribe el borrador de tu `docs/dataset-card.md` con el `dataset` que estás
   considerando. Es la mitad del hito 1, que se entrega 5 días después de S02.

---

## Errores que van a aparecer, con su causa

| Síntoma | Causa habitual |
|---|---|
| `ModuleNotFoundError: miproyecto` en el CI, y en local funciona | falta `[tool.hatch.build.targets.wheel] packages = ["src/miproyecto"]` (o el equivalente de tu `backend`), así que el paquete no se instala |
| `The lockfile is not up to date` | commiteaste `pyproject.toml` sin `uv.lock`. Corre `uv lock` y añade los dos |
| El CI sale verde con los tests rotos | hay un `|| true`, un `continue-on-error` o un `|| echo` en el paso |
| `pre-commit` "no hace nada" | falta `pre-commit install`, o estás commiteando con `--no-verify` |
| El PR tiene 300 líneas de reformateo | dos formatters: Black en el editor y `ruff format` en el `hook` |
| `make: command not found` en Windows | ver [`troubleshooting-so.md`](troubleshooting-so.md) §6 |
| `uv sync` borró un paquete que necesitabas | lo instalaste con `uv pip install`; nunca se declaró. Ver [`entorno.md`](entorno.md) §3 |
| `smoke_test.py` sale verde con el entorno roto | hace `pip list` en lugar de `import`, o no llama a `sys.exit(1)` |

---

Solución de referencia: [`_soluciones/`](_soluciones/). **No la abras antes de
intentarlo**: el valor está en el intento, y con la solución delante el intento no
ocurre.
