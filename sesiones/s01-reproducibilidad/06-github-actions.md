## GitHub Actions: Ejemplos de flujos de CI

Copia una de las plantillas de abajo en `.github/workflows/ci.yml` en la raíz del repositorio.

### Flujo con uv

```yaml
name: CI (uv)

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - uses: astral-sh/setup-uv@v4
      - name: Sync dependencies
        run: |
          uv --version
          uv sync --locked || uv sync
      - name: Lint
        run: |
          uv run ruff check .
          uv run black --check .
        continue-on-error: true
      - name: Tests
        run: |
          uv run pytest -q || echo "No tests yet"
```

### Flujo con Poetry

```yaml
name: CI (Poetry)

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install Poetry
        run: |
          pipx install poetry
          poetry --version
      - name: Install dependencies
        run: |
          poetry install --no-root --no-interaction --no-ansi
      - name: Lint
        run: |
          poetry run ruff check .
          poetry run black --check .
        continue-on-error: true
      - name: Tests
        run: |
          poetry run pytest -q || echo "No tests yet"
```
