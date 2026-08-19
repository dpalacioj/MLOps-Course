"""Rutas de la sesion 8, resueltas relativas al archivo y nunca al cwd.

Problema que resuelve
---------------------
El repo anterior tenia rutas absolutas de la maquina del autor incrustadas en
YAML y notebooks (ver ``scripts/hooks/sin_rutas_absolutas.py``). El sintoma es
siempre el mismo: funciona para quien lo escribio y falla para todos los demas.

Aqui todo se resuelve desde ``__file__``, asi que los scripts de la sesion se
pueden correr desde la raiz del repo, desde la carpeta de la sesion o desde un
runner de CI sin cambiar nada. Los directorios de salida se pueden redirigir
por variable de entorno para no escribir dentro del arbol de fuentes cuando el
proceso corre en un contenedor de solo lectura.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

#: Raiz de la sesion: .../sesiones/s08-llmops
SESION_DIR: Final[Path] = Path(__file__).resolve().parents[2]
#: Raiz del repositorio, para reutilizar REPORTS_DIR del caso guia.
REPO_ROOT: Final[Path] = SESION_DIR.parents[1]

PROMPTS_DIR: Final[Path] = SESION_DIR / "prompts"
RUBRICAS_DIR: Final[Path] = SESION_DIR / "rubricas"
DATOS_DIR: Final[Path] = SESION_DIR / "datos"
CONFIG_DIR: Final[Path] = SESION_DIR / "config"
GATEWAY_DIR: Final[Path] = SESION_DIR / "gateway"

#: Dataset de evals. Es el activo mas valioso de la sesion.
DATASET_EVALS: Final[Path] = DATOS_DIR / "quejas.jsonl"
#: Precios de los modelos. Cambian todos los meses: por eso son configuracion.
PRECIOS_YAML: Final[Path] = CONFIG_DIR / "precios.yaml"

#: Salidas. Se respeta REPORTS_DIR para alinearse con ``taxi.config``.
REPORTS_DIR: Final[Path] = Path(os.getenv("REPORTS_DIR", REPO_ROOT / "reports"))
#: Subcarpeta propia para no mezclar los reportes de LLMOps con los de S07.
REPORTES_LLM_DIR: Final[Path] = REPORTS_DIR / "llmops"


def asegurar_directorios() -> None:
    """Crea los directorios de salida si no existen."""
    REPORTES_LLM_DIR.mkdir(parents=True, exist_ok=True)
