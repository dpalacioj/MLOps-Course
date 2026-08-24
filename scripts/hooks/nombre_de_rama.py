#!/usr/bin/env python
"""Hook de pre-push: valida la convencion de nombres de rama.

Reemplaza a `.githooks/pre-push`. El motivo del cambio no es cosmetico: git
permite **un solo** lugar donde buscar hooks (`core.hooksPath`), y el repositorio
tenia dos sistemas compitiendo por ese puesto. `make setup` apuntaba
`core.hooksPath` a `.githooks/` y despues intentaba instalar pre-commit, que se
niega con:

    [ERROR] Cowardly refusing to install hooks with `core.hooksPath` set.

Resultado: quedaban activos los dos scripts de `.githooks/` y **no** se
instalaban ruff, gitleaks, nbstripout ni los hooks propios del curso. Y
`make setup` terminaba sin avisar de nada.

La solucion es un solo sistema. La validacion del mensaje de commit ya la hacia
`conventional-pre-commit`, asi que `.githooks/commit-msg` era redundante. Lo
unico que faltaba cubrir era esto: el nombre de la rama.

Convencion:  <tipo>/<descripcion-en-kebab-case>
Ejemplos validos:   feat/add-monitoring-module   fix/mlflow-tracking-bug
Ejemplos invalidos: mi-rama-nueva   feature/Add_Thing   feat/dos/segmentos
"""

from __future__ import annotations

import re
import subprocess
import sys

TIPOS = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
    "hotfix",
    "release",
)

#: Un solo segmento despues del tipo, en kebab-case y sin mayusculas.
PATRON = re.compile(rf"^({'|'.join(TIPOS)})/[a-z0-9][a-z0-9-]*$")

#: Ramas que no siguen la convencion porque no son ramas de trabajo.
EXENTAS = {"main", "master", "develop", "HEAD"}


def rama_actual() -> str | None:
    """Nombre de la rama, o None si el HEAD esta desprendido."""
    try:
        resultado = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return resultado.stdout.strip() or None


def main() -> int:
    rama = rama_actual()

    # HEAD desprendido (por ejemplo durante un rebase). No hay nada que validar
    # y bloquear aqui solo estorbaria.
    if rama is None or rama in EXENTAS:
        return 0

    if PATRON.match(rama):
        return 0

    print()
    print("=" * 62)
    print("  PUSH RECHAZADO — nombre de rama invalido")
    print("=" * 62)
    print()
    print(f'  Tu rama: "{rama}"')
    print()
    print("  Formato esperado: <tipo>/<descripcion-en-kebab-case>")
    print()
    print("  Ejemplos validos:")
    print("    feat/add-monitoring-module")
    print("    fix/mlflow-tracking-bug")
    print("    docs/course-overview")
    print()
    print("  Tipos permitidos:")
    print("    " + ", ".join(TIPOS))
    print()
    print("  Para renombrar la rama en la que estas:")
    print("    git branch -m feat/mi-descripcion")
    print()
    print("=" * 62)
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
