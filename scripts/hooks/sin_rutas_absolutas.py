#!/usr/bin/env python
"""Hook: bloquea rutas absolutas de usuario en el repositorio.

Motivacion concreta. `03-Orchestration/00-intro-prefect/prefect.yaml` tenia:

    set_working_directory: /Users/mdurango/Downloads/proyectos/MLOps_UdM/...

Con eso, `prefect deploy --all` falla en cualquier maquina que no sea la de
quien lo escribio. El mismo patron aparecia en el `MLmodel` de un artefacto
commiteado y en los outputs de tres notebooks.

Es el tipo de error que no rompe nada para el autor y rompe todo para el resto.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATRONES = [
    (re.compile(r"/Users/[A-Za-z0-9._-]+/"), "ruta absoluta de macOS"),
    (re.compile(r"/home/(?!runner/|vscode/|claude/)[A-Za-z0-9._-]+/"), "ruta absoluta de Linux"),
    (re.compile(r"[Cc]:\\+Users\\+[A-Za-z0-9._-]+"), "ruta absoluta de Windows"),
]

#: Rutas donde la ruta absoluta es parte del contenido didactico:
#: documentamos el error en lugar de esconderlo.
PERMITIDOS = (
    "docs/auditoria-2026-04.md",
    "docs/MIGRACION.md",
    "docs/plan-de-mejora/",
    "scripts/hooks/",
    "sesiones/s01-reproducibilidad/07-os-notes.md",
    "sesiones/s01-reproducibilidad/git.md",
    "sesiones/s01-reproducibilidad/troubleshooting-so.md",
    "sesiones/s06-cloud-cicd/_contraejemplo-insegure-aws/",
    "CHANGELOG.md",
    # Los workflows y la documentacion del curso citan la ruta original
    # (/Users/mdurango/...) al explicar el bug que hacia fallar `prefect deploy`
    # en cualquier maquina ajena. Es material didactico: el ejemplo pierde fuerza
    # si se censura la ruta que lo causaba.
    ".github/workflows/",
)


def revisar(ruta: Path) -> list[str]:
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    hallazgos: list[str] = []
    for numero, linea in enumerate(texto.splitlines(), start=1):
        for patron, descripcion in PATRONES:
            if patron.search(linea):
                hallazgos.append(f"{ruta}:{numero}: {descripcion} -> {linea.strip()[:110]}")
    return hallazgos


def main(argv: list[str]) -> int:
    total: list[str] = []
    for nombre in argv:
        ruta = Path(nombre)
        if not ruta.is_file():
            continue
        if any(permitido in ruta.as_posix() for permitido in PERMITIDOS):
            continue
        total.extend(revisar(ruta))

    if not total:
        return 0

    print("\nSe encontraron rutas absolutas de usuario:\n")
    for hallazgo in total:
        print(f"  {hallazgo}")
    print(
        "\nUsa rutas relativas al repositorio o `taxi.config.PROJECT_ROOT`.\n"
        "Si la ruta es parte del material didactico, agrega el archivo a\n"
        "PERMITIDOS en scripts/hooks/sin_rutas_absolutas.py y explica por que.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
