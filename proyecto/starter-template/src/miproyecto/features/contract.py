"""Contrato de features — la UNICA definicion de features del proyecto.

Problema que resuelve: en un proyecto sin este modulo, el notebook, el flow de
entrenamiento y la API acaban con tres listas de features distintas. El sintoma
tipico es un `KeyError` en el mejor caso, y en el peor una feature que se
codifica como categorica en entrenamiento y como numerica en serving.

La distincion importante, y la razon por la que este archivo esta separado del
contrato de datos: hay que separar explicitamente las columnas que **llegan** en
el dato crudo de las que el pipeline **deriva**. Confundirlas es lo que produce
train/serving skew.

TODO(estudiante) 08: reemplaza los nombres genericos por los de tu dataset.
Manten la separacion crudas / derivadas.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

# =============================================================================
# Columnas que LLEGAN en el dato crudo
# =============================================================================
#: Eje temporal. Es la columna sobre la que se hace el split y el analisis de
#: drift. Si tu dataset no tiene una, tienes que justificarlo por escrito en
#: docs/dataset-card.md (ver los requisitos duros en proyecto/README.md).
COL_TIEMPO: Final[str] = "ts"

#: Categoricas crudas. IDs y codigos van aqui aunque sean numeros: la region 7
#: no es "mayor" que la region 6.
CRUDAS_CATEGORICAS: Final[list[str]] = ["categoria", "region", "canal"]

#: Numericas crudas. Documenta las UNIDADES en el nombre o en dataset-card.md.
#: Un cambio silencioso de unidades (millas -> km, USD -> COP) no lanza
#: excepciones: solo degrada la metrica.
CRUDAS_NUMERICAS: Final[list[str]] = ["cantidad", "precio_unitario", "descuento"]

COLUMNAS_CRUDAS_REQUERIDAS: Final[list[str]] = [
    COL_TIEMPO,
    *CRUDAS_CATEGORICAS,
    *CRUDAS_NUMERICAS,
]

# =============================================================================
# Columnas DERIVADAS por el pipeline
# =============================================================================
#: Combinacion de dos categoricas. Captura la interaccion como una unidad: el
#: par (canal web, region norte) puede comportarse distinto de lo que sugieren
#: las dos categorias por separado.
COL_SEGMENTO: Final[str] = "segmento"
DERIVADAS_CATEGORICAS: Final[list[str]] = [COL_SEGMENTO]

#: Features de calendario. La demanda de un martes a las 9am no se parece a la
#: de un domingo a las 3am, y el modelo no puede inferirlo de un timestamp.
COL_HORA: Final[str] = "hora"
COL_DIA_SEMANA: Final[str] = "dia_semana"
COL_MES: Final[str] = "mes"
DERIVADAS_NUMERICAS: Final[list[str]] = [COL_HORA, COL_DIA_SEMANA, COL_MES]

# =============================================================================
# Features que consume el modelo
# =============================================================================
FEATURES_CATEGORICAS: Final[list[str]] = [*DERIVADAS_CATEGORICAS, *CRUDAS_CATEGORICAS]
FEATURES_NUMERICAS: Final[list[str]] = [*CRUDAS_NUMERICAS, *DERIVADAS_NUMERICAS]
FEATURES: Final[list[str]] = [*FEATURES_CATEGORICAS, *FEATURES_NUMERICAS]

# =============================================================================
# Target
# =============================================================================
#: TODO(estudiante) 09: define tu target y, si es derivado, deriva lo en
#: data/loaders.py, no aqui. El contrato de features no debe conocer el target:
#: mezclar ambos es la forma mas facil de filtrar informacion del objetivo
#: dentro de una feature (leakage).
TARGET: Final[str] = "objetivo"

#: Columna por la que se calculan metricas por subgrupo en el gate de promocion.
#: Tiene que ser una categorica con pocos valores y sentido de negocio.
COL_SUBGRUPO: Final[str] = "region"


def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    """Deriva las features a partir del dataframe crudo.

    Es **idempotente**: llamarla dos veces sobre el mismo dataframe da el mismo
    resultado. Eso importa porque el orquestador puede cachear el resultado y
    porque los tests la llaman varias veces.

    Args:
        df: dataframe con al menos ``COLUMNAS_CRUDAS_REQUERIDAS``.

    Returns:
        Copia del dataframe con las columnas derivadas agregadas.

    Raises:
        KeyError: si falta alguna columna cruda requerida. Falla temprano y dice
            exactamente que falta, en lugar de propagar un error opaco veinte
            lineas despues.
    """
    faltantes = [c for c in COLUMNAS_CRUDAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        raise KeyError(
            f"Faltan columnas crudas requeridas: {faltantes}. "
            f"Columnas presentes: {sorted(df.columns.tolist())}"
        )

    out = df.copy()

    # Las categoricas se castean a string SOLO al construir features, nunca
    # sobre el dataframe crudo completo: castear el crudo convierte tambien las
    # numericas y el vectorizador acaba one-hot-encodeando un precio.
    for col in CRUDAS_CATEGORICAS:
        out[col] = out[col].astype("string").fillna("desconocido").astype(str)

    out[COL_SEGMENTO] = out["canal"] + "_" + out["region"]

    tiempo = pd.to_datetime(out[COL_TIEMPO])
    out[COL_HORA] = tiempo.dt.hour.astype("int16")
    out[COL_DIA_SEMANA] = tiempo.dt.dayofweek.astype("int16")
    out[COL_MES] = tiempo.dt.month.astype("int16")

    return out


def a_diccionarios(df: pd.DataFrame) -> list[dict]:
    """Convierte el dataframe al formato que espera ``DictVectorizer``.

    Se usa ``DictVectorizer`` y no ``OneHotEncoder`` a proposito: cuando una
    categorica tiene muchos valores y algunos aparecen SOLO en produccion,
    ``DictVectorizer`` ignora las claves que no vio en ``fit``, que es
    exactamente el comportamiento deseado. El precio es tener que convertir a
    diccionarios, y ese precio se hace explicito aqui en lugar de esconderlo.

    Alternativa valida: ``OneHotEncoder(handle_unknown="infrequent_if_exist")``
    dentro de un ``ColumnTransformer``. Elige una y documentala en el ADR.
    """
    faltantes = [c for c in FEATURES if c not in df.columns]
    if faltantes:
        raise KeyError(
            f"Faltan features derivadas: {faltantes}. "
            f"Llama a construir_features(df) antes de a_diccionarios(df)."
        )
    return df[FEATURES].to_dict(orient="records")
