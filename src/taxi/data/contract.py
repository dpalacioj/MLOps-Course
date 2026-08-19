"""Contratos de datos ejecutables (Sesion 2).

Un contrato de datos es un esquema **versionado junto al codigo** que describe
como se ve un dato valido. Se valida en la frontera del pipeline: donde el dato
entra, no donde se usa.

Por que hace falta: los errores de datos casi nunca lanzan excepciones,
degradan metricas. Si `trip_distance` pasa de millas a kilometros, el pipeline
entrena sin quejarse, registra un RMSE plausible y sirve predicciones malas.
Todo verde, todo mal. El contrato convierte ese fallo silencioso en un fallo
ruidoso, que es infinitamente mas barato de arreglar.

Alternativas y trade-offs:

- **Pandera** (lo que usamos): in-process, tipado, se integra con pytest y con
  el pipeline. Costo de entrada bajo.
- **Great Expectations Core 1.x**: mas potente para data warehouse y reporting,
  con Data Docs. Mucho mas pesado. Ojo: su API cambio por completo respecto a
  0.18, asi que la mayoria de los tutoriales en la web estan obsoletos.
- **Pydantic**: correcto para I/O de una API (un registro a la vez), no para
  DataFrames.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series

from taxi.config import (
    DURACION_MAX_MIN,
    DURACION_MIN_MIN,
)
from taxi.features import contract as fc


class ViajesCrudos(pa.DataFrameModel):
    """Contrato del parquet crudo de la NYC TLC.

    ``strict = False`` a proposito: el parquet trae ~20 columnas y solo nos
    importan estas. Un contrato que exija ausencia de columnas extra se rompe
    cada vez que la TLC agrega un campo, y eso entrena al equipo a ignorarlo.
    """

    lpep_pickup_datetime: Series[pd.Timestamp] = pa.Field(nullable=False)
    lpep_dropoff_datetime: Series[pd.Timestamp] = pa.Field(nullable=False)
    PULocationID: Series[int] = pa.Field(ge=1, le=265, nullable=False)
    DOLocationID: Series[int] = pa.Field(ge=1, le=265, nullable=False)
    # 0 a 100 millas. Un viaje en taxi verde de mas de 100 millas es un error de
    # captura, no un viaje. El limite superior es lo que atrapa el cambio de
    # unidades: en km, los viajes largos se saldrian del rango.
    trip_distance: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False)

    class Config:
        strict = False
        coerce = True

    @pa.dataframe_check(name="dropoff_posterior_a_pickup")
    def dropoff_posterior_a_pickup(cls, df: pd.DataFrame) -> Series[bool]:
        """Un viaje no puede terminar antes de empezar."""
        return df["lpep_dropoff_datetime"] >= df["lpep_pickup_datetime"]

    @pa.dataframe_check(name="volumen_minimo")
    def volumen_minimo(cls, df: pd.DataFrame) -> bool:
        """Alerta si el volumen cae drasticamente.

        Una particion con 50 filas normalmente significa que la descarga se
        corto, no que hubo 50 viajes en un mes. Este check no protege el modelo,
        protege contra silenciar un fallo de ingesta.
        """
        return len(df) >= 1_000


class ViajesProcesados(pa.DataFrameModel):
    """Contrato del dataset listo para entrenar.

    Aqui ``strict`` sigue en False porque el dataframe arrastra columnas del
    crudo, pero los rangos son mas duros: si algo llega hasta este punto fuera
    de rango, el bug esta en nuestro pipeline y no en el proveedor.
    """

    PU_DO: Series[str] = pa.Field(nullable=False, str_matches=r"^\d+_\d+$")
    PULocationID: Series[str] = pa.Field(nullable=False)
    DOLocationID: Series[str] = pa.Field(nullable=False)
    trip_distance: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False)
    hora_pickup: Series[int] = pa.Field(ge=0, le=23, nullable=False)
    dia_semana_pickup: Series[int] = pa.Field(ge=0, le=6, nullable=False)
    duration: Series[float] = pa.Field(ge=DURACION_MIN_MIN, le=DURACION_MAX_MIN, nullable=False)
    viaje_largo: Series[int] = pa.Field(isin=[0, 1], nullable=False)

    class Config:
        strict = False
        coerce = True

    @pa.dataframe_check(name="target_no_constante")
    def target_no_constante(cls, df: pd.DataFrame) -> bool:
        """El target binario debe tener las dos clases.

        Si `viaje_largo` es todo 0, cualquier clasificador da 100% de accuracy y
        el estudiante aprende una leccion equivocada. Esto es exactamente el
        problema que tenia el generador sintetico anterior, donde el target era
        `random.choices([0, 1])`: ruido puro presentado como problema de ML.
        """
        return df["viaje_largo"].nunique() == 2


def validar_crudos(df: pd.DataFrame, *, lazy: bool = True) -> pd.DataFrame:
    """Valida el dataframe crudo contra el contrato.

    Args:
        df: dataframe recien leido del parquet.
        lazy: si es True, acumula todos los errores antes de fallar. En clase
            conviene True: ves los cinco problemas de una vez en lugar de
            arreglar uno, re-correr y descubrir el siguiente.

    Raises:
        pandera.errors.SchemaError o SchemaErrors: con el detalle de que fallo.
    """
    return ViajesCrudos.validate(df, lazy=lazy)


def validar_procesados(df: pd.DataFrame, *, lazy: bool = True) -> pd.DataFrame:
    """Valida el dataframe procesado contra el contrato."""
    return ViajesProcesados.validate(df, lazy=lazy)


def resumen_contrato() -> dict[str, list[str]]:
    """Devuelve el contrato como diccionario, para documentarlo o loguearlo.

    Se llama desde ``scripts/model_card.py``: la model card debe declarar contra
    que esquema de datos se entreno el modelo.
    """
    return {
        "crudas_requeridas": fc.COLUMNAS_CRUDAS_REQUERIDAS,
        "features_categoricas": fc.FEATURES_CATEGORICAS,
        "features_numericas": fc.FEATURES_NUMERICAS,
        "targets": [fc.TARGET_REGRESION, fc.TARGET_CLASIFICACION],
    }
