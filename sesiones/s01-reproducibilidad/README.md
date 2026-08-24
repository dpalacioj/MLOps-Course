# Sesión 1 — Reproducibilidad y disciplina de ingeniería

> **Fecha de revisión del material:** agosto de 2026.
> Versiones verificadas ejecutando los comandos en esta máquina: `uv 0.8.17`,
> `python 3.11`, `ruff 0.16.3`, `mypy 2.3.1`, `pre-commit 4.6.2`,
> `nbstripout 0.9.1`, `git-lfs 3.4.1`.
> Si tu `uv --version` dice otra cosa, no pasa nada: los comandos de esta sesión son
> estables desde 0.5. Lo que **no** debes asumir es que un tutorial sin fecha sigue
> siendo correcto.

Esta es la sesión que decide si las otras siete se pueden dar. No enseña MLOps:
enseña la única condición previa para que MLOps signifique algo. Si el entorno de
la persona de al lado no reproduce tu número, no hay experiment `tracking` que
salvar, no hay `pipeline` que orquestar y no hay modelo que promover.

La pregunta de la sesión: **¿otra persona, en otra máquina, obtiene tu mismo
resultado sin que tú estés delante?**

---

## Objetivos

Al terminar la sesión debes poder:

1. Reconstruir el entorno del curso desde cero (`make setup && make smoke`) y
   explicar qué garantiza `pyproject.toml` y qué garantiza `uv.lock`, que no es
   lo mismo.
2. Crear un proyecto propio con `uv`: dependencias declaradas, lockfile
   versionado y `.venv` fuera de git.
3. Explicar por qué un notebook con estado oculto no es reproducible, y qué gana
   un análisis al convertirse en paquete.
4. Armar un `Makefile` básico y decir para qué sirve tener una interfaz única de
   comandos.
5. Diagnosticar un entorno roto con `make smoke` en lugar de con `python -V`.

El taller de hoy ([`taller.md`](taller.md)) pone en práctica los puntos 2, 3 y 4
sobre un repositorio propio, desde cero.

---

## Cómo está organizada la sesión

Arrancamos con el problema, no con las herramientas: el notebook
[`01-del-notebook-al-paquete.ipynb`](notebooks/01-del-notebook-al-paquete.ipynb)
muestra el mismo análisis en tres estados y por qué dos de ellos no son de fiar.
Después viene el entorno reproducible ([`entorno.md`](entorno.md)), luego git y
la calidad automática ([`git.md`](git.md) y [`calidad.md`](calidad.md)), y
cerramos con el taller ([`taller.md`](taller.md)), que se puede terminar en
clase.

Si algo del entorno se atraviesa, [`troubleshooting-so.md`](troubleshooting-so.md)
tiene los errores típicos de macOS y Windows, y el
[`devcontainer`](../../.devcontainer/) es el plan B para seguir la clase mientras
se arregla la máquina.

---

## 1. El dolor: el mismo análisis, tres veces

Se abre [`notebooks/01-del-notebook-al-paquete.ipynb`](notebooks/01-del-notebook-al-paquete.ipynb)
y se recorre en vivo. El notebook contiene tres estados del **mismo** cálculo sobre
el caso guía (duración media de un viaje de taxi verde en 2023-01):

| Estado | Cómo se ejecuta | Qué falla |
|---|---|---|
| **Caótico** | celdas fuera de orden, `!pip install` en la celda 12, constantes reescritas a mano en cada celda | el resultado depende del orden en que le diste a Shift+Enter. Nadie puede reproducirlo, ni tú mañana |
| **Script** | `python analisis.py` | reproducible dentro de esa carpeta. Pero no se puede importar, no se puede testear por partes y las constantes siguen duplicadas |
| **Paquete** | `from taxi.data import loaders` | importable, testeable, versionado, instalado desde un `lockfile`. El mismo número, en cualquier máquina |

**El número tiene que salir igual en los tres.** Ese es el punto: la
reproducibilidad no es una propiedad del resultado, es una propiedad del proceso.
Un notebook caótico que da el número correcto por casualidad y un paquete que da
el mismo número son cosas distintas, aunque la salida de pantalla sea idéntica.

Tres preguntas que se hacen en voz alta antes de abrir cualquier herramienta:

1. **Orden de ejecución.** En un notebook, ¿cuál es el estado del kernel? Se corre
   `Kernel → Restart & Run All` sobre el estado caótico y se rompe. Preguntar
   cuántos de los notebooks que tienen en el disco pasarían esa prueba.
2. **`!pip install` en la celda 12.** ¿En qué entorno instaló? ¿Qué versión? ¿Queda
   registrado en algún archivo? (No. Y la próxima persona instala otra.)
3. **`attachments` y `outputs`.** El notebook original de este curso pesaba 175 KB,
   de los cuales ~82 KB eran una imagen en base64 pegada en una celda de markdown,
   y sus `outputs` contenían rutas absolutas del disco de quien lo ejecutó. Eso es
   lo que el `hook` de `nbstripout` corrige, y se ve en el bloque B.

> **Nota sobre el notebook anterior.** `01-panorama-mlops.ipynb` fue **eliminado**
> en este rediseño. Tres razones, en orden de peso: (a) **no ejecutaba** —su cuarta
> celda hacía `from generate_data import UserGenerator` y ese módulo no existe en
> ninguna parte del repositorio; (b) su `target` se asignaba al azar, así que
> producía un ROC-AUC ~0.5 presentado como resultado de un modelo, exactamente el
> anti-patrón que corrige el
> [ADR 001](../../docs/adr/001-caso-guia-y-particiones.md); (c) traía los 82 KB de
> `attachments` y los `outputs` con rutas absolutas mencionados arriba. Su contenido
> **valioso** no se perdió: la explicación de `data leakage` y el uso de `Pipeline` /
> `ColumnTransformer` para prevenirlo se movieron a su lugar natural, la
> [sesión 2](../s02-datos/), y la progresión notebook → script → paquete es el
> notebook nuevo de esta sesión.

---

## 2. Bloque A — El entorno (40-95 min)

Documento: **[`entorno.md`](entorno.md)**.

Lo que se construye: el entorno del curso, desde cero, con `uv`. Lo que se
**entiende**:

- `pyproject.toml` declara *intención* (rangos de versión). `uv.lock` declara
  *hecho* (versiones y hashes exactos, resueltos una vez). Los dos se commitean, y
  cada uno responde una pregunta distinta.
- La diferencia entre `uv add`, `uv pip install` y `uv sync`, demostrada con el
  experimento de [`entorno.md`](entorno.md) sección 3: instalas dos paquetes de dos
  maneras, borras `.venv`, sincronizas, y uno de los dos ya no está.
- Por qué `uv run` es preferible a activar el entorno: en un `cron`, en un `flow`
  de Prefect o en un contenedor **nadie activa nada**.

Alternativas que se discuten con honestidad, no para descartarlas: Poetry (que
sigue vivo y mantenido), `pip-tools`, y conda/mamba, que sigue ganando donde `uv`
no llega —dependencias que no son Python: CUDA, GDAL, compiladores.

## 3. Bloque B — Git, LFS y calidad automática (110-165 min)

Documentos: **[`git.md`](git.md)** y **[`calidad.md`](calidad.md)**.

`git.md` cubre el flujo diario, `conventional commits` (que el `hook`
`commit-msg` de este repositorio verifica de verdad) y **Git LFS al principio, no
al final**. Ese orden es una corrección deliberada: en el material anterior LFS era
el documento nº 10 de 13, y el resultado medible fue que los 12 diagramas de la
sesión 4 aparecían como archivos de texto de tres líneas para cualquiera que
clonara sin LFS. Un binario mal versionado no se arregla después; se reescribe el
historial.

`calidad.md` cubre `ruff` (lint **y** formato), `mypy`, `pre-commit`, `nbstripout`
y el CI. La regla que ordena todo el documento: **el `hook` local y el CI corren lo
mismo**. Si divergen, el `hook` deja de ser útil, la gente lo desactiva y el CI se
convierte en el sitio donde uno se enfrenta a un error que podría haber visto en
tres segundos.

---

## 4. Material de la sesión

```
sesiones/s01-reproducibilidad/
├── README.md                 este archivo
├── entorno.md                Bloque A: uv, pyproject vs uv.lock, alternativas
├── git.md                    Bloque B: flujo diario, conventional commits, LFS
├── calidad.md                Bloque B: ruff, mypy, pre-commit, nbstripout, CI
├── troubleshooting-so.md     macOS vs Windows (consulta, no lectura lineal)
├── taller.md                 el taller: un repositorio propio desde cero
├── notebooks/
│   ├── 01-del-notebook-al-paquete.ipynb   el dolor: tres estados del mismo analisis
│   └── _generar_notebooks.py              fuente del notebook (se edita aqui)
├── templates/                para copiar a tu propio proyecto
│   ├── .gitignore-python
│   ├── pre-commit-config.yaml
│   ├── pyproject.uv.toml
│   └── pyproject.poetry.toml
├── scripts/                  setup guiado, si el manual falla
│   ├── setup_uv_mac.sh
│   ├── setup_uv_windows.ps1
│   ├── setup_poetry_mac.sh
│   └── setup_poetry_windows.ps1
└── _soluciones/              NO abrir antes del taller

Se usa de la raíz del repositorio:
Makefile                      la interfaz única: make setup, make smoke, make check
scripts/smoke_test.py         el diagnóstico del entorno
.pre-commit-config.yaml       los hooks reales del curso
.github/workflows/ci.yml      el CI real del curso
.devcontainer/                el plan B: entorno listo en 3 minutos
```

Los cuatro documentos de contenido (`entorno`, `git`, `calidad`,
`troubleshooting-so`) sustituyen a los **quince** archivos del material anterior
(`01-git-github`, `01.1-conventional-commits`, `02-python-envs`,
`02.1-uv-conda-venv`, `03-dependency-management`, `04-tooling`,
`05-data-and-secrets`, `06-github-actions`, `07-os-notes`, `08-pre-commit`,
`09-cicd-guide`, `10-git-lfs`, `Resumen.md`, `ejercicio-setup.md` y las 437 líneas
de `referencia-uv/README.md`). No fue una poda estética: los quince se contradecían
entre sí en el comando de activación de Windows, en qué formatter usar y en qué CI
copiar, y el estudiante no tenía forma de saber cuál de las tres versiones era la
vigente.

---

## 5. Quick Start

Si solo lees una sección de esta carpeta, que sea esta.

### macOS / Linux

```bash
# 1) Prerrequisitos: git, uv
brew install git uv          # o el instalador oficial: curl -LsSf https://astral.sh/uv/install.sh | sh

# 2) Clonar tu fork
git clone git@github.com:<tu-usuario>/<tu-fork>.git
cd <tu-fork>

# 3) Git LFS ANTES de nada: los diagramas del curso son binarios en LFS
brew install git-lfs && git lfs install && git lfs pull

# 4) Todo lo demás
make setup
make smoke
```

### Windows (PowerShell)

```powershell
# 1) PRIMER PASO, ANTES DE CUALQUIER SCRIPT.
#    La ExecutionPolicy por defecto en Windows es Restricted y bloquea todo .ps1,
#    incluido Activate.ps1 y los scripts de setup. Sin esto, el paso 5 falla con
#    UnauthorizedAccess y la primera hora de clase se va en diagnosticarlo.
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 2) Prerrequisitos
winget install --id Git.Git -e --source winget
winget install --id GitHub.GitLFS -e --source winget
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Cierra y vuelve a abrir PowerShell para que el PATH se actualice.

# 3) Python 3.11 — con uv, no con pyenv-win
uv python install 3.11

# 4) Clonar y traer los binarios
git clone git@github.com:<tu-usuario>/<tu-fork>.git
cd <tu-fork>
git lfs install
git lfs pull

# 5) Todo lo demás. OJO: `make` no viene en Windows.
uv sync --group dev
uv run pre-commit install --install-hooks
uv run pre-commit install --hook-type commit-msg
uv run python scripts/smoke_test.py
```

Detalles, variantes y los cuatro errores que más aparecen en Windows:
[`troubleshooting-so.md`](troubleshooting-so.md).

**Si el setup falla y llevas más de 10 minutos:** no bloquees la clase. Abre el
[`devcontainer`](../../.devcontainer/) —GitHub Codespaces o Docker local— y sigue
la sesión desde ahí. Arreglas tu máquina en la pausa. El objetivo de hoy no es
pelearse con el `PATH`.

---

## 6. Autoverificación

Respóndelas sin mirar arriba. Entre paréntesis, dónde está la respuesta.

1. Borras `.venv` y corres `uv sync`. Un compañero instaló `seaborn` con
   `uv pip install seaborn` y otro con `uv add seaborn`. ¿Cuál de los dos entornos
   vuelve a tener `seaborn`? ¿Por qué? ([`entorno.md`](entorno.md) sección 3)
2. Tu CI usa `uv sync --locked` y falla con un error de `lockfile` desactualizado,
   pero en tu máquina `uv sync` funciona. ¿Qué pasó y cuál es el arreglo correcto?
   (Pista: el arreglo **no** es quitar `--locked`.) ([`entorno.md`](entorno.md) sección 4)
3. Commiteaste un `.png` de 4 MB sin LFS, y tres commits después lo agregaste a
   `.gitattributes`. ¿Qué le pasa a quien clona el repositorio hoy? ¿Se arregla con
   `git lfs pull`? ([`git.md`](git.md) sección 5)
4. Tu equipo tiene `ruff format` en `pre-commit` y un compañero tiene el
   "Black Formatter" de VS Code con `formatOnSave`. Describe el diff del próximo PR
   y por qué el CI va a estar rojo para los dos. ([`calidad.md`](calidad.md) sección 2)
5. `make smoke` te da `FAIL` en "Archivos LFS traídos" pero `OK` en todo lo demás.
   ¿Puedes seguir la sesión 1? ¿Puedes seguir la sesión 4? ¿Por qué es un `FAIL` y
   no un `WARN`? ([`calidad.md`](calidad.md) sección 6 y
   [`scripts/smoke_test.py`](../../scripts/smoke_test.py))

---

## 7. Alternativas y trade-offs

Ninguna de las decisiones de esta sesión es la única posible. Lo que se pide en el
taller no es copiar el stack del curso, es **declarar** el propio y saber qué
costó.

**Criterio de evaluación:** instalable sin cuenta ni licencia; mantenimiento activo
(release en los últimos 12 meses); funciona en macOS, Linux y Windows; `lockfile`
reproducible entre plataformas.
**Fecha de evaluación: 19 de agosto de 2026.** La columna "última release" se
consultó ese día en el índice de PyPI. Cada fila enlaza a su documentación oficial.

| Herramienta | Última release | ¿Cumple el criterio? | Cuándo la elegirías | Documentación |
|---|---|---|---|---|
| **uv** | 0.12.5 (14-ago-2026) | Sí | por defecto: reemplaza `pip`, `venv`, `pyenv` y `pipx`, y el `lockfile` es multiplataforma | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| **Poetry** | 2.4.1 (9-may-2026) | Sí. **No es legado**: la línea 2.x está activa y mantenida | si ya lo tienes en producción, si publicas paquetes a PyPI, o si tu equipo prefiere su UX. Cambiar por cambiar cuesta más de lo que rinde | [python-poetry.org/docs](https://python-poetry.org/docs/) |
| **pip-tools** | 7.6.1 (12-ago-2026) | Sí | si estás obligado a `requirements.txt` (imagen base heredada, plataforma que solo entiende `pip`). `pip-compile` te da el `lock` sin cambiar de flujo | [pip-tools.readthedocs.io](https://pip-tools.readthedocs.io/) |
| **venv + pip** | parte de la stdlib de Python | Sí, pero sin `lock` real | scripts de un archivo, o entornos donde no puedes instalar nada. `pip freeze` **no** es un `lockfile`: no trae hashes y es específico de la plataforma | [docs.python.org/3/library/venv.html](https://docs.python.org/3/library/venv.html) |
| **conda / mamba** | se distribuye por conda-forge, no por PyPI; verifica con `conda --version` en tu máquina | Sí | **donde `uv` no llega**: dependencias que no son Python. CUDA y `cudatoolkit`, GDAL/PROJ, compiladores de Fortran, R en el mismo entorno. Es su ventaja real y no ha desaparecido | [docs.conda.io](https://docs.conda.io/), [conda-forge.org](https://conda-forge.org/) |

El razonamiento completo, con lo que cada una cuesta, está en
[`entorno.md`](entorno.md) sección 6.

---

## 8. Qué NO usar

| No usar | Por qué | En su lugar |
|---|---|---|
| `uv update <pkg>` | **el subcomando no existe.** `uv update pandas` responde `error: unrecognized subcommand 'update'` (verificado con `uv 0.8.17`, agosto de 2026). Aparecía dos veces en el material anterior del curso, incluida su tabla resumen | `uv lock --upgrade-package pandas` y después `uv sync` |
| `\.venv\Scripts\Activate.ps1` (sin el punto inicial) | la ruta empieza en la **raíz del disco**, no en el directorio actual. `07-os-notes.md` del material anterior lo escribía así y era el primer error de la sesión en Windows | `.\.venv\Scripts\Activate.ps1` |
| `pyenv-win` vía `Invoke-WebRequest` + reinicio de terminal como ruta por defecto en Windows | es el paso más frágil de todo el setup: descarga un `.ps1` de GitHub, lo ejecuta contra la `ExecutionPolicy`, edita el `PATH` del usuario y exige cerrar la terminal. Cada uno de esos cuatro pasos falla en algún alumno | `uv python install 3.11`. `pyenv-win` queda como alternativa documentada en [`troubleshooting-so.md`](troubleshooting-so.md) sección 5 |
| `chmod +x setup.sh && ./setup.sh` en Windows | `chmod` no existe en PowerShell y el bit de ejecución no es un concepto de NTFS. Solo funciona dentro de WSL o de Git Bash | el `.ps1` equivalente, o WSL declarado explícitamente ([`troubleshooting-so.md`](troubleshooting-so.md) sección 4) |
| Black **y** `ruff format` en el mismo repositorio | la doc de Ruff dice que su formatter "is not intended to be used interchangeably with Black on an ongoing basis, as the formatter *does* differ from Black in a few conscious ways". Dos formatters alternándose producen PRs de cientos de líneas de reformateo y un CI rojo para todo el mundo | uno solo. En este curso, `ruff format` ([`calidad.md`](calidad.md) sección 2) |
| `flake8` + `isort` + `black` como trío **nuevo** | tres herramientas, tres configuraciones que hay que mantener de acuerdo, tres ejecuciones. `ruff` cubre las tres familias de reglas. Nada obliga a migrar un proyecto que ya lo tenga y funcione | `ruff check` + `ruff format` |
| `pip freeze > requirements.txt` como estrategia de reproducibilidad | congela también las dependencias transitivas sin distinguirlas de las tuyas, no lleva hashes y es específico de la plataforma en la que se ejecutó | `uv.lock` (o `pip-compile --generate-hashes`) |
| `git commit --no-verify` como hábito | es la señal de que los `hooks` tardan demasiado o comprueban algo distinto del CI. El síntoma es real; la solución no es saltárselos | arreglar el `hook`: que sea rápido y que corra exactamente lo del CI |
| Commitear `.env`, `data/raw/*.parquet` o `model.pkl` | secretos en el historial (que siguen ahí después de borrar el archivo) y un repositorio que crece sin límite. En el repo anterior había tres artefactos binarios commiteados | `.env.example` + LFS para los binarios que **sí** se versionan + `make data` para descargar el resto |
| Notebooks commiteados con `outputs` | ruido en el diff, filtran rutas absolutas y tokens del entorno de quien ejecutó, y engordan el repositorio (175 KB por un notebook de 33 celdas) | `nbstripout` como `hook` ([`calidad.md`](calidad.md) sección 4) |
| `python -V; uv --version` como verificación de entorno | no prueba nada de lo que realmente falla: punteros LFS sin traer, puertos ocupados, dependencias declaradas pero no instaladas, contratos que no validan | `make smoke` |

---

## 9. Tarea y puente a S02

**Para antes de la próxima clase:** si el taller quedó a medias, terminarlo (es
corto y suma al bonus). Y algo más importante: ir pensando en el `dataset` del
proyecto del curso — en [`proyecto/README.md`](../../proyecto/README.md) está el
enunciado completo y una lista de datasets ya verificados.

**Puente:** hoy conseguimos que el entorno sea reproducible. Eso significa que el
**código** produce siempre el mismo resultado *dado el mismo dato*. La sesión que
viene ataca la otra mitad, que es la que rompe los sistemas de ML de verdad: qué
pasa cuando el dato cambia y nadie se da cuenta. Adelanto del dolor de S02:
cambiaremos **una sola cosa** en el parquet —`trip_distance` de millas a
kilómetros— y el `pipeline` no fallará. Entrenará, registrará una métrica creíble y
servirá predicciones. Todo verde, todo mal.

---

Relacionado: [ADR 001 — caso guía y particiones](../../docs/adr/001-caso-guia-y-particiones.md) ·
[`Makefile`](../../Makefile) · [`scripts/smoke_test.py`](../../scripts/smoke_test.py) ·
[`.devcontainer/`](../../.devcontainer/) · [`proyecto/README.md`](../../proyecto/README.md)
