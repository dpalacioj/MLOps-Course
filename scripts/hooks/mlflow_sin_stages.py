#!/usr/bin/env python
"""Hook: bloquea el uso de stages deprecados de MLflow.

El repositorio se contradecia a si mismo. El modulo 02 ensenaba aliases como la
practica correcta, y los modulos 03 y 04 promovian modelos con:

    client.transition_model_version_stage(name, version, stage="Production")

Verificado contra mlflow 3.15.1: el metodo existe pero esta marcado como
deprecado desde 2.9.0, y la documentacion oficial dice que los stages "will be
removed in a future major release". El reemplazo son **aliases** (referencia
mutable a la version que sirve) mas **tags** (metadatos, p. ej.
validation_status=passed).

Este hook existe para que el codigo no vuelva a divergir de lo que se ensena.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROHIBIDOS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"transition_model_version_stage"),
        "stages deprecados -> usa client.set_registered_model_alias(nombre, 'champion', version)",
    ),
    (
        re.compile(r"get_latest_versions\s*\("),
        "deprecado -> usa client.get_model_version_by_alias(nombre, 'champion')",
    ),
    (
        re.compile(r"models:/[\w\-.]+/(Production|Staging|Archived|None)\b"),
        "referencia por stage -> usa models:/<nombre>@champion",
    ),
    (
        re.compile(r"archive_existing_versions"),
        "propio de la API de stages -> con aliases no hace falta archivar",
    ),
    (
        re.compile(r"log_model\((?:[^)]*?)artifact_path\s*="),
        "artifact_path esta deprecado en los flavors de mlflow 3 -> usa name=",
    ),
    (
        re.compile(r"mean_squared_error\((?:[^)]*?)squared\s*=\s*False"),
        "el parametro squared ya no existe en sklearn -> usa root_mean_squared_error",
    ),
]


def lineas_de(ruta: Path) -> list[tuple[int, str]]:
    """Devuelve (numero, linea). En notebooks, solo las celdas de codigo."""
    if ruta.suffix != ".ipynb":
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        return list(enumerate(texto.splitlines(), start=1))

    try:
        nb = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    resultado: list[tuple[int, str]] = []
    for indice, celda in enumerate(nb.get("cells", [])):
        if celda.get("cell_type") != "code":
            continue
        for linea in celda.get("source", []):
            resultado.append((indice, linea.rstrip("\n")))
    return resultado


def main(argv: list[str]) -> int:
    hallazgos: list[str] = []
    for nombre in argv:
        ruta = Path(nombre)
        if not ruta.is_file():
            continue
        for numero, linea in lineas_de(ruta):
            if linea.lstrip().startswith("#"):
                continue
            for patron, consejo in PROHIBIDOS:
                if patron.search(linea):
                    ubicacion = (
                        f"{ruta} (celda {numero})"
                        if ruta.suffix == ".ipynb"
                        else f"{ruta}:{numero}"
                    )
                    hallazgos.append(
                        f"{ubicacion}\n      {linea.strip()[:100]}\n      -> {consejo}"
                    )

    if not hallazgos:
        return 0

    print("\nAPIs deprecadas detectadas:\n")
    for hallazgo in hallazgos:
        print(f"  {hallazgo}\n")
    print(
        "El curso ensena aliases + tags. Si necesitas mostrar la API vieja como\n"
        "contraejemplo, ponla en una celda markdown o agrega el archivo a\n"
        "`exclude` del hook en .pre-commit-config.yaml.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
