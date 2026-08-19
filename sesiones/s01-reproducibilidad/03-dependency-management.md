## Gestión de dependencias con uv y Poetry

Este curso admite tanto uv como Poetry. Recomendamos uv por su velocidad y simplicidad. Usa una sola herramienta por proyecto/carpeta para evitar conflictos.

### Uso de uv (recomendado)

Comandos clave:

```bash
# Inicializa un proyecto (crea pyproject.toml)
uv init

# Añadir/quitar paquetes
uv add pandas
uv remove pandas

# Sincroniza el entorno desde pyproject + lock
uv sync            # respects uv.lock if present

# Añade dependencias de desarrollo
uv add --dev pytest ruff black pre-commit

# Ejecuta comandos en el entorno gestionado
uv run python -V

# Exporta un requirements (si lo necesitas)
uv export -o requirements.txt
```

Ejemplo de `pyproject.toml` (uv):

```toml
[project]
name = "mlops-course"
version = "0.1.0"
description = "MLOps course exercises"
readme = "README.md"
requires-python = ">=3.11,<3.13"
dependencies = [
  "numpy",
]

[dependency-groups]
dev = ["pytest", "ruff", "black", "pre-commit"]
```

Bloqueo: uv gestiona automáticamente un lock file (uv.lock) cuando es necesario. Comitear el lock garantiza reproducibilidad exacta para el equipo y en CI.

### Uso de Poetry

Comandos clave:

```bash
# Inicializa un proyecto
poetry init        # interactive

# Añadir/quitar paquetes
poetry add pandas
poetry remove pandas

# Instala desde poetry.lock (o resuelve si falta)
poetry install --no-root

# Dependencias de desarrollo
poetry add -G dev pytest ruff black pre-commit

# Ejecuta en el entorno
poetry run python -V

# Exporta requirements fijados (para herramientas que lo requieran)
poetry export -f requirements.txt -o requirements.txt --with dev --without-hashes
```

Ejemplo de `pyproject.toml` (Poetry): ver `templates/pyproject.poetry.toml` en esta carpeta.

### Cómo elegir la herramienta

- Prefiere uv por la velocidad y las instalaciones sin configuración, especialmente en CI.
- Prefiere Poetry si quieres funcionalidades como publicación o si te gusta más su UX.

### Lista de verificación de reproducibilidad

- Fija un rango de versión de Python (por ejemplo, `>=3.11,<3.13`).
- Commitea tu lock file (`uv.lock` o `poetry.lock`).
- Usa CI que instale desde el lock y ejecute pruebas (ver `06-github-actions.md`).
- Evita mezclar gestores (no uses uv y Poetry en el mismo proyecto).
