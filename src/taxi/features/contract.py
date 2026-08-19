"""Contrato de features — la UNICA definicion de features del curso.

Antes del rediseno el mismo problema tenia tres conjuntos de features
incompatibles:

- `02-Experiment-Tracking`: PULocationID, DOLocationID, trip_distance
- `03-Orchestration/Prefect`: PU_DO, trip_distance
- `03-Orchestration/Mage`:   PULocationID, DOLocationID (sin trip_distance)

Peor: `loaders.py` casteaba `CATEGORICAL_FEATURES = ['PU_DO', 'trip_distance']`
a string sobre el parquet **crudo**, donde `PU_DO` todavia no existe. Eso
producia `KeyError: "['PU_DO'] not in index"` y el pipeline estrella del curso
no arrancaba. Y si se "arreglaba" mal, `trip_distance` quedaba como string y el
DictVectorizer la one-hot-encodeaba en lugar de tratarla como numerica.

La leccion que se ensena con esto: separar explicitamente las columnas que
**llegan** en el dato crudo de las que el pipeline **deriva**.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

# =============================================================================
# Columnas que LLEGAN en el parquet crudo de la TLC
# =============================================================================
COL_PICKUP: Final[str] = "lpep_pickup_datetime"
COL_DROPOFF: Final[str] = "lpep_dropoff_datetime"

#: Zonas de origen y destino. Son IDs numericos, pero semanticamente son
#: categorias: la zona 42 no es "mayor" que la 41.
CRUDAS_CATEGORICAS: Final[list[str]] = ["PULocationID", "DOLocationID"]
#: Distancia del viaje. Viene en MILLAS (no en km — el generador de datos
#: sinteticos del repo anterior documentaba km y alimentaba un modelo entrenado
#: en millas).
CRUDAS_NUMERICAS: Final[list[str]] = ["trip_distance"]

COLUMNAS_CRUDAS_REQUERIDAS: Final[list[str]] = [
    COL_PICKUP,
    COL_DROPOFF,
    *CRUDAS_CATEGORICAS,
    *CRUDAS_NUMERICAS,
]

# =============================================================================
# Columnas DERIVADAS por el pipeline
# =============================================================================
#: Combinacion origen-destino. Captura la ruta como una unidad: el par
#: (Harlem -> JFK) tiene un comportamiento propio que las dos zonas por
#: separado no expresan.
COL_RUTA: Final[str] = "PU_DO"
DERIVADAS_CATEGORICAS: Final[list[str]] = [COL_RUTA]

#: Hora del dia y dia de la semana. El trafico de NYC a las 8am de un martes no
#: se parece al de las 3am de un domingo.
COL_HORA: Final[str] = "hora_pickup"
COL_DIA_SEMANA: Final[str] = "dia_semana_pickup"
DERIVADAS_NUMERICAS: Final[list[str]] = [COL_HORA, COL_DIA_SEMANA]

# =============================================================================
# Features que consume el modelo
# =============================================================================
FEATURES_CATEGORICAS: Final[list[str]] = [*DERIVADAS_CATEGORICAS, *CRUDAS_CATEGORICAS]
FEATURES_NUMERICAS: Final[list[str]] = [*CRUDAS_NUMERICAS, *DERIVADAS_NUMERICAS]
FEATURES: Final[list[str]] = [*FEATURES_CATEGORICAS, *FEATURES_NUMERICAS]

# =============================================================================
# Targets
# =============================================================================
TARGET_REGRESION: Final[str] = "duration"
TARGET_CLASIFICACION: Final[str] = "viaje_largo"


def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    """Deriva las features del dataframe crudo.

    Idempotente: llamarla dos veces sobre el mismo dataframe da el mismo
    resultado. Eso importa porque el flow de Prefect la cachea.

    Args:
        df: dataframe con al menos las columnas de ``COLUMNAS_CRUDAS_REQUERIDAS``.

    Returns:
        Copia del dataframe con las columnas derivadas agregadas.

    Raises:
        KeyError: si falta alguna columna cruda requerida. Falla temprano y con
            un mensaje que dice exactamente que falta, en lugar de propagar un
            error opaco veinte lineas despues.
    """
    faltantes = [c for c in COLUMNAS_CRUDAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        raise KeyError(
            f"Faltan columnas crudas requeridas: {faltantes}. "
            f"Columnas presentes: {sorted(df.columns.tolist())}"
        )

    out = df.copy()

    # Las zonas se tratan como categorias, pero SOLO al construir features.
    # Nunca se castea el parquet crudo completo (ese era el bug original).
    for col in CRUDAS_CATEGORICAS:
        out[col] = out[col].astype("Int64").astype(str)

    out[COL_RUTA] = out["PULocationID"] + "_" + out["DOLocationID"]

    pickup = pd.to_datetime(out[COL_PICKUP])
    out[COL_HORA] = pickup.dt.hour.astype("int16")
    out[COL_DIA_SEMANA] = pickup.dt.dayofweek.astype("int16")

    return out


def a_diccionarios(df: pd.DataFrame) -> list[dict]:
    """Convierte el dataframe al formato que espera ``DictVectorizer``.

    Se usa ``DictVectorizer`` y no ``OneHotEncoder`` por una razon didactica: el
    par origen-destino tiene miles de valores posibles y varios aparecen solo en
    produccion. ``DictVectorizer`` ignora las claves que no vio en ``fit``, lo
    que es exactamente el comportamiento deseado. El precio es que hay que
    convertir a diccionarios, y ese precio se hace explicito aqui.
    """
    faltantes = [c for c in FEATURES if c not in df.columns]
    if faltantes:
        raise KeyError(
            f"Faltan features derivadas: {faltantes}. "
            f"Llama a construir_features(df) antes de a_diccionarios(df)."
        )
    return df[FEATURES].to_dict(orient="records")
