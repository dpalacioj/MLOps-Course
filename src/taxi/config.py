"""Configuracion unica del caso guia del curso.

Este modulo es la **unica fuente de verdad** para particiones de datos, nombres
de experimento, nombres de modelo registrado y rutas. Antes del rediseno la
misma informacion estaba duplicada (y en desacuerdo) en cuatro lugares:
`02-Experiment-Tracking` usaba datos de 2023, `03-Orchestration` calculaba el
periodo con `datetime.now()` y pedia 2025-01 —un parquet que puede no estar
publicado— y Mage usaba features distintas para el mismo problema.

Decision de diseno (ver docs/adr/001-caso-guia-y-particiones.md): las
particiones son **fijas y del pasado**. Un curso no puede depender de que la
NYC TLC haya publicado el mes corriente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# =============================================================================
# Rutas
# =============================================================================
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DATA_DIR: Final[Path] = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR: Final[Path] = DATA_DIR / "raw"
PROCESSED_DIR: Final[Path] = DATA_DIR / "processed"
REPORTS_DIR: Final[Path] = Path(os.getenv("REPORTS_DIR", PROJECT_ROOT / "reports"))


# =============================================================================
# Particiones de datos — FIJAS. No usar datetime.now().
# =============================================================================
@dataclass(frozen=True)
class Particion:
    """Una particion mensual del dataset de la NYC TLC."""

    anio: int
    mes: int

    @property
    def etiqueta(self) -> str:
        return f"{self.anio}-{self.mes:02d}"

    @property
    def nombre_archivo(self) -> str:
        return f"green_tripdata_{self.etiqueta}.parquet"

    @property
    def url(self) -> str:
        return f"{TLC_BASE_URL}/{self.nombre_archivo}"

    def __str__(self) -> str:
        return self.etiqueta


TLC_BASE_URL: Final[str] = "https://d37ci6vzurychx.cloudfront.net/trip-data"

#: Meses de entrenamiento. Tres meses dan volumen suficiente sin volver lento
#: el entrenamiento en clase.
PARTICIONES_TRAIN: Final[tuple[Particion, ...]] = (
    Particion(2023, 1),
    Particion(2023, 2),
    Particion(2023, 3),
)
#: Validacion — el mes inmediatamente siguiente al entrenamiento.
PARTICION_VALID: Final[Particion] = Particion(2023, 4)
#: Holdout fijo. Es el juez del gate de promocion (S06): nunca se usa para
#: seleccionar hiperparametros, solo para decidir si un candidato mejora al
#: champion. Si lo usas para tunear, el gate deja de significar algo.
PARTICION_TEST: Final[Particion] = Particion(2023, 5)
#: "Produccion simulada" para el modulo de monitoreo (S07). Drift REAL:
#: estacionalidad de verano y, a un ano de distancia, cambios de tarifa y de
#: patrones de viaje. No hace falta inventar drift con numpy.
PARTICIONES_PRODUCCION: Final[tuple[Particion, ...]] = (
    Particion(2023, 7),
    Particion(2024, 1),
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
#: Filas por particion tras el muestreo. Green taxi trae ~60-70k viajes/mes;
#: 60k por particion mantiene el entrenamiento en segundos, que es lo que
#: permite iterar en clase.
FILAS_POR_PARTICION: Final[int] = 60_000
#: Semilla global. Se pasa explicitamente a cada componente en lugar de
#: confiar en el estado global de numpy.
SEMILLA: Final[int] = 42


# =============================================================================
# Filtros de negocio del dataset
# =============================================================================
#: Duracion minima y maxima de un viaje valido, en minutos. Fuera de ese rango
#: son errores de captura (viajes de 0 min o de 8 horas), no viajes.
DURACION_MIN_MIN: Final[float] = 1.0
DURACION_MAX_MIN: Final[float] = 60.0
#: Umbral del target binario derivado. Permite ensenar metricas de
#: clasificacion, umbrales y matriz de costos sin traer un segundo dataset.
UMBRAL_VIAJE_LARGO_MIN: Final[float] = 30.0


# =============================================================================
# MLflow — puerto 5001 en TODO el curso
# =============================================================================
# El 5000 lo ocupa AirPlay Receiver en macOS. Antes del rediseno el repo
# mezclaba 5000 y 5001 entre scripts, notebooks y .env.example, y en Windows
# el estudiante acababa con el servidor en un puerto y el .env en el otro.
MLFLOW_PORT: Final[int] = 5001
MLFLOW_TRACKING_URI: Final[str] = os.getenv(
    "MLFLOW_TRACKING_URI", f"http://127.0.0.1:{MLFLOW_PORT}"
)

#: Convencion de nombres de experimento: s0X-proposito.
EXPERIMENTOS: Final[dict[str, str]] = {
    "baseline": "s03-baseline",
    "comparacion": "s03-comparacion-modelos",
    "hpo": "s03-hpo-xgboost",
    "pipeline": "s04-pipeline-orquestado",
    "gate": "s06-gate-de-promocion",
}

#: Un solo nombre por problema. Antes habia cuatro nombres para dos modelos.
MODELO_REGRESION: Final[str] = "nyc-taxi-duration"
MODELO_CLASIFICACION: Final[str] = "nyc-taxi-long-trip"

#: Alias de produccion. Reemplaza los stages, deprecados en MLflow.
ALIAS_PRODUCCION: Final[str] = "champion"
ALIAS_CANDIDATO: Final[str] = "candidate"

#: Tag que el gate de promocion escribe antes de mover el alias.
TAG_VALIDACION: Final[str] = "validation_status"


def uri_modelo(nombre: str = MODELO_REGRESION, alias: str = ALIAS_PRODUCCION) -> str:
    """URI del modelo por alias.

    Es la unica forma correcta de referirse al modelo en produccion. El repo
    anterior copiaba directorios con `shutil.copytree` entre los modulos 03 y
    04, lo que rompia toda la trazabilidad que el modulo 02 ensena a construir.

    >>> uri_modelo()
    'models:/nyc-taxi-duration@champion'
    """
    return f"models:/{nombre}@{alias}"


# =============================================================================
# Umbrales operativos
# =============================================================================
#: Margen relativo que un candidato debe superar al champion para promoverse.
#: 0.0 significa "empatar no alcanza"; 0.01 significa "mejorar al menos 1%".
#: Con ruido de muestreo, exigir una mejora minima evita el churn de modelos.
MEJORA_MINIMA_RELATIVA: Final[float] = 0.01
#: Fraccion de columnas con drift que dispara la alerta en S07.
UMBRAL_DRIFT_COLUMNAS: Final[float] = 0.30


def asegurar_directorios() -> None:
    """Crea los directorios de trabajo si no existen."""
    for directorio in (RAW_DIR, PROCESSED_DIR, REPORTS_DIR):
        directorio.mkdir(parents=True, exist_ok=True)
