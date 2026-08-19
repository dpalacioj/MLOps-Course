"""Configuracion unica del proyecto.

Este modulo es la UNICA fuente de verdad para particiones de datos, nombres de
experimento, nombres de modelo registrado, semillas y umbrales operativos.

Por que existe: la forma mas comun de perder la reproducibilidad es tener la
misma constante escrita en cuatro lugares que dejan de coincidir. Si el notebook
entrena con 2023-01, el flow con `datetime.now()` y la API con un archivo
copiado a mano, no hay manera de decir que modelo esta sirviendo ni con que
datos se midio.

Regla: si un valor aparece dos veces en el proyecto, sube aqui.

TODO(estudiante) 03: adapta TODO este modulo a tu dataset. Los nombres de
columna, las particiones y los rangos que hay aqui son placeholders genericos y
deliberadamente aburridos; tienen que dejar de serlo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# =============================================================================
# Rutas
# =============================================================================
# PROJECT_ROOT se deriva de la ubicacion de este archivo, nunca de os.getcwd()
# ni de una ruta absoluta escrita a mano. Una ruta absoluta de tu maquina en el
# repositorio garantiza que el proyecto no corre en la maquina de nadie mas
# (y el peer review lo va a notar de inmediato).
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DATA_DIR: Final[Path] = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR: Final[Path] = DATA_DIR / "raw"
PROCESSED_DIR: Final[Path] = DATA_DIR / "processed"
REPORTS_DIR: Final[Path] = Path(os.getenv("REPORTS_DIR", PROJECT_ROOT / "reports"))


# =============================================================================
# Particiones — FIJAS. No usar datetime.now().
# =============================================================================
@dataclass(frozen=True)
class Particion:
    """Una particion inmutable del dataset, identificada por etiqueta.

    Se modela como objeto y no como string suelto para que la URL, el nombre de
    archivo y la etiqueta se deriven de un solo lugar. Si manana cambias el
    proveedor, cambias `url` y nada mas.
    """

    etiqueta: str

    @property
    def nombre_archivo(self) -> str:
        return f"{PREFIJO_ARCHIVO}_{self.etiqueta}{SUFIJO_ARCHIVO}"

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.nombre_archivo}"

    def __str__(self) -> str:
        return self.etiqueta


# TODO(estudiante) 04: apunta esto a tu fuente real y verifica que la URL
# responde 200 sin autenticacion. Si tu dataset exige login, el peer review no
# puede reproducirlo: cambia de dataset o incluye un script de descarga que el
# revisor pueda correr con sus propias credenciales.
BASE_URL: Final[str] = os.getenv("MIPROYECTO_BASE_URL", "https://example.invalid/datos")
PREFIJO_ARCHIVO: Final[str] = "datos"
SUFIJO_ARCHIVO: Final[str] = ".parquet"

#: Particiones de entrenamiento. Las mas antiguas.
PARTICIONES_TRAIN: Final[tuple[Particion, ...]] = (
    Particion("2023-01"),
    Particion("2023-02"),
    Particion("2023-03"),
)
#: Validacion — la particion inmediatamente siguiente al entrenamiento. Aqui se
#: eligen hiperparametros.
PARTICION_VALID: Final[Particion] = Particion("2023-04")
#: Holdout fijo. Es el juez del gate de promocion: NUNCA se usa para seleccionar
#: hiperparametros. Si lo usas para tunear, el gate deja de medir generalizacion
#: y pasa a medir cuanto te sobreajustaste al juez.
PARTICION_TEST: Final[Particion] = Particion("2023-05")
#: "Produccion simulada" para el modulo de monitoreo. Elige particiones donde
#: esperes drift REAL (estacionalidad, cambio de politica, cambio de mix de
#: clientes). No inventes drift con numpy: la discusion interesante es
#: "esto es drift o es estacionalidad esperada?", y el ruido sintetico no la da.
PARTICIONES_PRODUCCION: Final[tuple[Particion, ...]] = (
    Particion("2023-09"),
    Particion("2024-01"),
)

TODAS_LAS_PARTICIONES: Final[tuple[Particion, ...]] = (
    *PARTICIONES_TRAIN,
    PARTICION_VALID,
    PARTICION_TEST,
    *PARTICIONES_PRODUCCION,
)


# =============================================================================
# Muestreo y determinismo
# =============================================================================
#: Filas por particion tras el muestreo. Un entrenamiento que tarda 3 segundos
#: se itera; uno que tarda 20 minutos se ejecuta una vez y se cree lo que diga.
FILAS_POR_PARTICION: Final[int] = 50_000
#: Semilla global. Se pasa EXPLICITAMENTE a cada componente en lugar de confiar
#: en el estado global de numpy: `np.random.seed()` en el import es una fuente
#: clasica de no determinismo cuando cambia el orden de los imports.
SEMILLA: Final[int] = 42


# =============================================================================
# MLflow
# =============================================================================
#: Puerto 5001, no 5000: en macOS el 5000 lo ocupa AirPlay Receiver.
MLFLOW_PORT: Final[int] = 5001
MLFLOW_TRACKING_URI: Final[str] = os.getenv(
    "MLFLOW_TRACKING_URI", f"http://127.0.0.1:{MLFLOW_PORT}"
)

#: Convencion de nombres de experimento: <hito>-<proposito>. Un nombre por
#: proposito, no uno por dia.
EXPERIMENTOS: Final[dict[str, str]] = {
    "baseline": "h1-baseline",
    "comparacion": "h2-comparacion-modelos",
    "hpo": "h2-hpo",
    "pipeline": "h2-pipeline-orquestado",
    "gate": "h3-gate-de-promocion",
}

# TODO(estudiante) 05: un nombre por problema. Si tu proyecto resuelve dos
# problemas (p. ej. regresion y clasificacion), declara dos nombres aqui y no
# los mezcles en el mismo modelo registrado.
MODELO_REGISTRADO: Final[str] = "miproyecto-modelo"

#: Alias de produccion. Reemplazan a los stages, deprecados en MLflow desde
#: 2.9.0. Un alias es una referencia mutable a "la version que sirve";
#: el rollback es moverlo de vuelta, y eso es una escritura de metadatos.
ALIAS_PRODUCCION: Final[str] = "champion"
ALIAS_CANDIDATO: Final[str] = "candidate"
#: Tag que el gate escribe ANTES de mover el alias, para que quede registrado
#: por que se promovio.
TAG_VALIDACION: Final[str] = "validation_status"


def uri_modelo(nombre: str = MODELO_REGISTRADO, alias: str = ALIAS_PRODUCCION) -> str:
    """URI del modelo por alias. Es la unica forma correcta de referirlo.

    Copiar el directorio del artefacto entre carpetas rompe toda la trazabilidad
    que el tracking construye.

    >>> uri_modelo()
    'models:/miproyecto-modelo@champion'
    """
    return f"models:/{nombre}@{alias}"


# =============================================================================
# Umbrales operativos — cada uno con su justificacion escrita
# =============================================================================
#: Mejora relativa minima que un candidato debe superar al champion para
#: promoverse. 0.0 significa "empatar alcanza", lo que produce churn de modelos
#: por puro ruido de muestreo. 0.01 = "mejorar al menos 1%".
#: TODO(estudiante) 06: justifica TU numero en docs/politica-de-reentrenamiento.md.
MEJORA_MINIMA_RELATIVA: Final[float] = 0.01

#: Degradacion maxima tolerada en cualquier subgrupo, aunque la metrica global
#: mejore. Un modelo que mejora en promedio empeorando a un segmento entero es
#: un problema de equidad, no una mejora.
DEGRADACION_MAXIMA_SUBGRUPO: Final[float] = 0.10

#: Fraccion de columnas con drift que dispara la alerta de monitoreo.
#: TODO(estudiante) 07: este numero tiene que estar justificado. "0.30 porque
#: venia en el template" no es una justificacion.
UMBRAL_DRIFT_COLUMNAS: Final[float] = 0.30

#: Nivel de significancia de los tests de drift por columna. Ojo: con n grande
#: TODO sale significativo. El umbral de p-valor NO reemplaza mirar el tamano
#: del efecto; ver monitoring/check_drift.py.
ALFA_DRIFT: Final[float] = 0.05


def asegurar_directorios() -> None:
    """Crea los directorios de trabajo si no existen."""
    for directorio in (RAW_DIR, PROCESSED_DIR, REPORTS_DIR):
        directorio.mkdir(parents=True, exist_ok=True)
