# ADR 000 — Stack técnico del proyecto (ejemplo resuelto)

> **Ejemplo de referencia del punto 9 del [taller](../taller.md).**
> Es el ADR que el repositorio del curso escribiría sobre sí mismo. Sirve para ver
> **la forma** y el nivel de detalle que se espera, no para copiarlo: un ADR copiado
> es un ADR sin decisión, y se nota en la sección de consecuencias.
>
> Este archivo se guarda en `_soluciones/` a propósito. En tu proyecto va en
> `docs/adr/000-stack.md`.

- **Estado:** aceptada
- **Fecha:** 19 de agosto de 2026
- **Decisores:** equipo docente del curso de MLOps
- **Alcance:** todo el repositorio del curso, las 8 sesiones y el `starter-template`
  del proyecto

---

## Contexto

Hay que elegir el stack de un repositorio que va a ser usado, a la vez, por:

- **~30 estudiantes de posgrado** en máquinas propias, mayoritariamente Windows,
  algunas gestionadas por la universidad (sin permisos de administrador);
- **el CI de GitHub Actions**, en Ubuntu y en Windows;
- **contenedores Docker**, para la API de inferencia (S05) y para el `devcontainer`;
- **8 sesiones de 4 horas**, donde cada minuto de setup es un minuto que no se
  dedica a MLOps.

Restricciones reales, en orden de peso:

1. **Sin presupuesto.** Todo tiene que ser gratuito y sin cuenta obligatoria.
2. **La primera hora de la primera sesión no se puede gastar en instalar cosas.** La
   auditoría del material anterior midió entre 10 y 40 minutos perdidos por cada uno
   de cinco problemas distintos de entorno.
3. **Windows es primer ciudadano**, no un apéndice. Cuatro de los fallos de la
   sesión 1 eran específicos de Windows y ninguno se detectaba, porque el CI solo
   corría en Ubuntu.
4. **Un artefacto entrenado en la sesión 3 tiene que servirse en la sesión 5 sin
   sorpresas de versión.** El `Dockerfile` anterior instalaba versiones distintas de
   las del entrenamiento y deserializaba `pickles` de otra versión de la librería.
5. **Las métricas tienen que ser comparables entre sesiones**, o el curso no puede
   enseñar comparación de modelos.

## Decisión

Un solo gestor de entorno y dependencias —**`uv`**— como fuente única de versiones
para todos los entornos, y un `Makefile` como interfaz única de comandos.

| Necesidad | Elegido | Versión verificada |
|---|---|---|
| Intérprete, entorno y dependencias | `uv` | 0.8.17 (`uv.lock` commiteado) |
| Versión de Python | `uv python install` + `.python-version` | 3.11 |
| Lint y formato | `ruff` (uno solo, sin Black) | 0.16.3 |
| Tipos | `mypy`, solo sobre `src/` y `scripts/` | 2.3.1 |
| `Hooks` | `pre-commit`, con los mismos comandos que el CI | 4.6.2 |
| Notebooks limpios | `nbstripout` | 0.9.1 |
| Binarios versionados | Git LFS | 3.4.1 |
| CI | GitHub Actions, 5 `jobs`, ninguno con `continue-on-error` | — |
| Contrato de datos | Pandera | 0.32.1 |
| `Tracking` y `registry` | MLflow, con `aliases` (no `stages`) | 3.15.1 |
| Orquestación | Prefect | 3.4.x |
| `Serving` | FastAPI + uvicorn | 0.115 / 0.42 |
| Monitoreo | Evidently + `scipy` como plan B | 0.7.21 / 1.17 |
| Empaquetado | `hatchling`, `src/` layout | — |

Dos reglas que se derivan de la decisión y que son lo que de verdad se está
decidiendo:

- **Las versiones se resuelven UNA vez, en `uv.lock`**, y local, CI, entrenamiento y
  `serving` instalan de ahí. Ningún `pin` escrito a mano en un `Dockerfile`.
- **El `hook` local y el CI ejecutan lo mismo.** Si divergen, el `hook` se vuelve
  ruido y la gente lo desactiva.

## Alternativas consideradas

**A. Poetry en lugar de `uv`.**
Poetry 2.x está vivo y mantenido (2.4.1, mayo de 2026), adoptó `[project]` de PEP 621
y su `poetry.lock` es tan determinista como `uv.lock`. **Descartada por una razón
concreta y medible:** `uv` gestiona además el **intérprete**
(`uv python install 3.11`), lo que elimina el paso más frágil del setup en Windows
—`pyenv-win` vía `Invoke-WebRequest` + reinicio de terminal—. Con Poetry, ese paso
sigue existiendo. En un equipo profesional que ya usa Poetry, esta decisión sería la
opuesta y estaría igual de justificada.

**B. `conda` / `mamba`.**
Ventaja real: resuelve dependencias que no son Python. **Descartada porque este curso
no las tiene:** ni CUDA, ni GDAL, ni R. Lo que sí tendría son sus costos —entornos
más pesados, entorno fuera de la carpeta del proyecto, y `conda env export` que no es
un `lockfile` (incluye `builds` específicos de plataforma; para un `lock` real hay que
añadir `conda-lock`)—. **Si el proyecto necesitara GPU con una versión concreta de
`cudatoolkit`, esta decisión se revisaría.**

**C. `venv` + `pip` + `requirements.txt`.**
Ventaja: cero herramientas nuevas, es lo que todo el mundo conoce. **Descartada
porque `pip freeze` no es un `lockfile`**: no lleva hashes, no distingue directas de
transitivas y es específico de la plataforma que lo generó. Con Windows y Ubuntu en
la matriz del CI, eso se rompe el primer día.

**D. `pip-tools`.**
`pip-compile --generate-hashes` sí produce un `lock` de verdad. **Descartada porque
no gestiona intérpretes ni entornos**, así que habría que combinarla con `pyenv` y
`venv`: tres herramientas donde `uv` es una. Sigue siendo la respuesta correcta si te
obligan a `requirements.txt`.

**E. Ruff **y** Black.**
**Descartada por la documentación de la propia herramienta:** el formatter de Ruff
"is not intended to be used interchangeably with Black on an ongoing basis". Dos
formatters alternándose producen PR de cientos de líneas de reformateo y un CI rojo
para todo el equipo.

**F. Mantener `flake8` + `isort` + `black`.**
Funciona y hay millones de proyectos así. **Descartada para un repositorio nuevo**
por costo de mantenimiento: tres configuraciones que hay que mantener de acuerdo
entre sí. No se recomendaría migrar un proyecto existente que ya lo tenga estable.

## Consecuencias

**Positivas**

- El entorno se reconstruye con dos comandos (`make setup && make smoke`), y el CI
  demuestra en cada PR que eso funciona en una máquina limpia, en dos sistemas
  operativos.
- Una sola resolución de versiones para todos los entornos. El artefacto de la
  sesión 3 se sirve en la sesión 5 con las mismas versiones con las que se validó.
- El `smoke test` diagnostica en segundos los cinco problemas que costaban entre 10 y
  40 minutos cada uno.
- `make check` en local es exactamente lo que el CI verifica, así que "pasa en mi
  máquina" y "pasa en CI" significan lo mismo.

**Negativas, y qué se hace con ellas**

- **`uv` es una herramienta joven** (2024) y su superficie de comandos aún cambia
  entre versiones menores. *Mitigación:* el `Dockerfile` pinnea `UV_VERSION`, el
  material declara la versión con la que se verificó, y los comandos que se enseñan
  son los estables (`add`, `sync`, `run`, `lock`).
- **Se le pide al estudiante aprender una herramienta que quizá no use en su
  empresa**, donde puede haber Poetry o `pip`. *Mitigación:* la sesión 1 enseña
  explícitamente las alternativas con sus `trade-offs`, y el taller acepta cualquiera
  de ellas siempre que haya `lockfile` commiteado. Lo que se evalúa es la propiedad
  —reproducibilidad— no la marca.
- **Un solo caso guía (NYC Green Taxi) puede resultar monótono** en ocho sesiones.
  *Mitigación:* el proyecto final es de dominio libre. Ver
  [ADR 001](../../../docs/adr/001-caso-guia-y-particiones.md).
- **`make` no existe en Windows.** *Mitigación:* el `devcontainer` como plan B, y el
  [Quick Start](../README.md#5-quick-start) lista los comandos equivalentes uno por
  uno. Es una fricción real que no desaparece, solo se rodea.
- **`mypy` cubre solo `src/` y `scripts/`.** Hay código sin tipar en `tests/` y en el
  material de las sesiones. *Se asume a propósito:* tipar el 100 % de un repositorio
  de ML con `pandas` y `mlflow` sin `stubs` completos consume un esfuerzo que no
  compra un error atrapado.
- **Git LFS tiene cuota** (1 GB de almacenamiento y 1 GB/mes de ancho de banda en el
  plan gratuito de GitHub, a agosto de 2026). *Mitigación:* solo van a LFS los `.png`
  de los diagramas; los `datasets` se descargan con `make data` y se verifican por
  SHA-256.

## Cuándo revisar esta decisión

- Si el curso necesita GPU: se revisa **B** (conda para el entorno base).
- Si `uv` introduce un cambio incompatible en `sync` o en el formato del `lock`: se
  revisa el `pin` de `UV_VERSION` y la tabla de versiones de este ADR.
- Al inicio de cada cohorte: se re-verifican las versiones de la tabla y las fechas
  de las tablas comparativas del material. Una tabla de herramientas sin fecha de
  evaluación es desinformación con retardo.

## Referencias

- [`pyproject.toml`](../../../pyproject.toml) · [`Makefile`](../../../Makefile) ·
  [`uv.lock`](../../../uv.lock)
- [`.pre-commit-config.yaml`](../../../.pre-commit-config.yaml) ·
  [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml)
- [ADR 001 — caso guía y particiones](../../../docs/adr/001-caso-guia-y-particiones.md)
- [ADR 002 — aliases en vez de stages](../../../docs/adr/002-aliases-en-vez-de-stages.md)
- [docs.astral.sh/uv](https://docs.astral.sh/uv/) ·
  [python-poetry.org/docs](https://python-poetry.org/docs/) ·
  [docs.astral.sh/ruff/formatter](https://docs.astral.sh/ruff/formatter/)
