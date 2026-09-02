#!/usr/bin/env python
"""Smoke test del entorno.

Ejecutalo como PRIMER paso:

    uv run python scripts/smoke_test.py

Por que existe: `python -V` no prueba nada de lo que realmente falla. Lo que falla
es una dependencia declarada y no instalada, un puerto ocupado, un `uv.lock`
ausente, un paquete que no se puede importar porque falta el `src/` layout, o un
contrato de datos que ya no valida sus propios fixtures.

Este script diagnostica todo eso en segundos y devuelve exit code != 0 si algo
esta mal, asi que sirve tambien como paso de CI.

**Esto es lo que va a correr quien te haga peer review.** Si tu `make smoke` no
funciona, tu nota de reproducibilidad ya esta decidida antes de que nadie mire tu
modelo.

TODO(estudiante) 26: agrega verificaciones propias de tu proyecto. Buenas
candidatas: que el dataset este descargado y su hash coincida, que MLflow
responda, que exista un modelo con alias @champion.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata as md
import importlib.util
import os
import platform
import socket
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

VERDE = "\033[92m"
ROJO = "\033[91m"
AMARILLO = "\033[93m"
GRIS = "\033[90m"
FIN = "\033[0m"

if os.name == "nt" and not os.getenv("WT_SESSION"):
    VERDE = ROJO = AMARILLO = GRIS = FIN = ""

# (modulo importable, nombre de distribucion)
PAQUETES: list[tuple[str, str]] = [
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("sklearn", "scikit-learn"),
    ("scipy", "scipy"),
    ("pyarrow", "pyarrow"),
    ("pandera", "pandera"),
    ("mlflow", "mlflow"),
    ("fastapi", "fastapi"),
    ("pydantic", "pydantic"),
]

PUERTOS = [
    (5001, "MLflow tracking server"),
    (8000, "API de inferencia"),
]

resultados: list[tuple[str, str, str]] = []


def ok(titulo: str, detalle: str = "") -> None:
    resultados.append(("OK", titulo, detalle))


def falla(titulo: str, detalle: str) -> None:
    resultados.append(("FAIL", titulo, detalle))


def aviso(titulo: str, detalle: str) -> None:
    resultados.append(("WARN", titulo, detalle))


# =============================================================================
# Verificaciones
# =============================================================================
def verificar_python() -> None:
    v = sys.version_info
    detalle = f"{v.major}.{v.minor}.{v.micro} ({platform.system()} {platform.machine()})"
    if (v.major, v.minor) >= (3, 11):
        ok("Python >= 3.11", detalle)
    else:
        falla("Python >= 3.11", f"tienes {detalle}. Corre: uv python install 3.11")


def verificar_venv() -> None:
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        ok("Entorno virtual activo", sys.prefix)
    else:
        aviso(
            "Entorno virtual activo",
            "estas usando el Python del sistema. Usa `uv run ...` o activa .venv",
        )


def verificar_lockfile() -> None:
    """Sin uv.lock no hay reproducibilidad y el CI (`--locked`) falla.

    Es el primer archivo que hay que commitear, y el que mas se olvida.
    """
    lock = RAIZ / "uv.lock"
    if lock.exists():
        ok("uv.lock presente", f"{lock.stat().st_size // 1024} KB")
    else:
        falla(
            "uv.lock presente",
            "no existe. Corre `uv sync --group dev` y COMMITEA uv.lock: "
            "sin el, `uv sync --locked` del CI falla y nadie reproduce tu resultado.",
        )


def verificar_paquetes() -> None:
    faltantes: list[str] = []
    for modulo, dist in PAQUETES:
        try:
            importlib.import_module(modulo)
            try:
                version = md.version(dist)
            except md.PackageNotFoundError:
                version = "?"
            ok(f"import {modulo}", version)
        except ImportError:
            faltantes.append(dist)
            falla(f"import {modulo}", "no instalado")
    if faltantes:
        falla("dependencias completas", f"corre: uv add {' '.join(faltantes)}")


def verificar_paquete_propio() -> None:
    """El paquete del proyecto tiene que ser importable, no solo estar en disco.

    Si esto falla, casi siempre es porque falta `pythonpath = ["src"]` en
    pyproject.toml o porque el paquete no se instalo (`uv sync`).
    """
    # Fallback a src/ con AVISO, no en silencio. Que el script corra tambien con
    # un interprete que no tiene el paquete instalado es comodo; ocultar que no
    # esta instalado no lo es, porque entonces `python -m miproyecto...` fallaria
    # en cualquier otra carpeta.
    if importlib.util.find_spec("miproyecto") is None:
        src = RAIZ / "src"
        if src.is_dir():
            sys.path.insert(0, str(src))
            aviso(
                "paquete instalado en el entorno",
                "no lo esta; se importa desde src/ para poder seguir. Corre `uv sync --group dev`.",
            )

    try:
        import miproyecto
        from miproyecto import config
        from miproyecto.data import contract as dc

        ok("import del paquete propio", f"miproyecto {miproyecto.__version__}")
        ok("configuracion cargada", f"{len(config.TODAS_LAS_PARTICIONES)} particiones declaradas")
        ok("contrato de datos cargado", f"{len(dc.resumen_contrato())} secciones")
    except Exception as exc:
        falla("import del paquete propio", f"{type(exc).__name__}: {exc}")


def verificar_fixtures() -> None:
    """El contrato debe aceptar el fixture valido Y rechazar el roto.

    Solo la segunda mitad demuestra que el contrato hace algo.
    """
    try:
        import pandas as pd

        from miproyecto.data import contract as dc

        base = RAIZ / "tests" / "fixtures"
        valido = pd.read_csv(base / "muestra-valida.csv", parse_dates=["ts"])
        dc.validar_crudos(valido)
        ok("contrato acepta el fixture valido", f"{len(valido)} filas")

        roto = pd.read_csv(base / "muestra-rota.csv", parse_dates=["ts"])
        try:
            dc.validar_crudos(roto)
            falla(
                "contrato rechaza el fixture roto",
                "el contrato acepto datos invalidos: no esta protegiendo nada",
            )
        except Exception:
            ok("contrato rechaza el fixture roto", "falla como debe")
    except FileNotFoundError as exc:
        aviso("fixtures de datos", f"no encontrados: {exc}")
    except Exception as exc:
        falla("fixtures de datos", f"{type(exc).__name__}: {exc}")


def verificar_puertos() -> None:
    for puerto, servicio in PUERTOS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            ocupado = s.connect_ex(("127.0.0.1", puerto)) == 0
        if ocupado:
            aviso(f"puerto {puerto} libre", f"ocupado (quizas ya corre {servicio})")
        else:
            ok(f"puerto {puerto} libre", servicio)


def verificar_archivos_clave() -> None:
    """Archivos sin los que el proyecto no es evaluable."""
    obligatorios = [
        "pyproject.toml",
        "Makefile",
        ".pre-commit-config.yaml",
        ".github/workflows/ci.yml",
        ".env.example",
        ".gitignore",
        "README.md",
        "docs/dataset-card.md",
        "docs/politica-de-reentrenamiento.md",
    ]
    for relativo in obligatorios:
        if (RAIZ / relativo).exists():
            ok(f"existe {relativo}")
        else:
            falla(f"existe {relativo}", "falta y la rubrica lo revisa")


def verificar_sin_env_commiteado() -> None:
    """Un .env en el repositorio es una penalizacion directa de la rubrica."""
    if (RAIZ / ".env").exists():
        aviso(
            ".env fuera del repositorio",
            "existe en disco (correcto), verifica con `git ls-files .env` que NO este versionado",
        )
    else:
        ok(".env fuera del repositorio")


# =============================================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test del entorno.")
    parser.add_argument(
        "--rapido",
        action="store_true",
        help="omite las verificaciones de puertos (util en CI)",
    )
    args = parser.parse_args(argv)

    verificar_python()
    verificar_venv()
    verificar_lockfile()
    verificar_paquetes()
    verificar_paquete_propio()
    verificar_fixtures()
    verificar_archivos_clave()
    verificar_sin_env_commiteado()
    if not args.rapido:
        verificar_puertos()

    print()
    for estado, titulo, detalle in resultados:
        color = {"OK": VERDE, "FAIL": ROJO, "WARN": AMARILLO}[estado]
        sufijo = f"  {GRIS}{detalle}{FIN}" if detalle else ""
        print(f"  {color}{estado:<4}{FIN} {titulo}{sufijo}")

    fallas = sum(1 for e, _, _ in resultados if e == "FAIL")
    avisos = sum(1 for e, _, _ in resultados if e == "WARN")
    print()
    if fallas:
        print(f"  {ROJO}{fallas} verificacion(es) fallaron{FIN} · {avisos} aviso(s)")
        return 1
    print(f"  {VERDE}entorno OK{FIN} · {avisos} aviso(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
