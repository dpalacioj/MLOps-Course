# Solución de referencia — Taller S01

El repositorio terminado queda así:

```
taller-mlops/
├── .gitignore
├── Makefile
├── pyproject.toml
├── uv.lock
├── src/
│   └── taller/
│       ├── __init__.py
│       └── limpieza.py
└── tests/
    └── test_limpieza.py
```

## Los archivos completos

### `pyproject.toml`

```toml
[project]
name = "taller"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.0",
    "scikit-learn>=1.5",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "ruff>=0.8",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/taller"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

### `.gitignore`

```
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
```

(El del taller pedía solo `.venv/`; estas tres líneas extra evitan que los
caches de Python y de las herramientas ensucien el `git status`.)

### `src/taller/limpieza.py`

```python
import pandas as pd


def filtrar_duracion(df: pd.DataFrame, minimo: float = 1.0, maximo: float = 60.0) -> pd.DataFrame:
    """Deja solo los viajes con duracion en [minimo, maximo] minutos."""
    return df[(df["duration"] >= minimo) & (df["duration"] <= maximo)].reset_index(drop=True)
```

### `tests/test_limpieza.py`

```python
import pandas as pd

from taller.limpieza import filtrar_duracion


def test_filtra_fuera_de_rango():
    df = pd.DataFrame({"duration": [0.5, 10.0, 30.0, 90.0]})
    resultado = filtrar_duracion(df)
    assert list(resultado["duration"]) == [10.0, 30.0]


def test_no_modifica_el_original():
    df = pd.DataFrame({"duration": [0.5, 10.0]})
    filtrar_duracion(df)
    assert len(df) == 2
```

### `Makefile`

```make
setup:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .
```

## Verificación

Desde un clon limpio:

```bash
uv sync && uv run pytest
# 2 passed
```

## Notas para quien corrige (o para el compañero que revisa)

- Lo primero es la prueba de fuego: clonar y correr `uv sync && uv run pytest`
  **sin leer nada más**. Si eso falla, el resto no importa todavía.
- El error más común es `.venv/` commiteado (pesa cientos de MB) o `uv.lock`
  ignorado. Los dos son la misma confusión: qué se versiona y qué se regenera.
- El segundo más común es el `Makefile` con espacios en lugar de tabs. El mensaje
  `missing separator` no ayuda a nadie que no lo haya visto antes.
- Si el paquete no importa (`ModuleNotFoundError: taller`), casi siempre falta el
  bloque `[tool.hatch.build.targets.wheel]` o el `uv sync` posterior.

## Los retos opcionales, resueltos

**Pre-commit mínimo** — `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.3
    hooks:
      - id: ruff-check
      - id: ruff-format
```

y `uv run pre-commit install`.

**CI mínimo** — `.github/workflows/ci.yml`:

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run pytest
```
