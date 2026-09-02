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

#: Distancia por encima de la cual un viaje en taxi verde deja de ser plausible.
MAX_MILLAS_PLAUSIBLE: float = 100.0
#: Fraccion maxima de viajes que puede superar ese limite antes de considerar que
#: el problema es sistematico y no ruido de captura. Calibrado con datos reales:
#: ver el check ``outliers_de_distancia_son_marginales``.
MAX_FRACCION_OUTLIERS: float = 0.003


class ViajesCrudos(pa.DataFrameModel):
    """Contrato del parquet crudo de la NYC TLC.

    ``strict = False`` a proposito: el parquet trae ~20 columnas y solo nos
    importan estas. Un contrato que exija ausencia de columnas extra se rompe
    cada vez que la TLC agrega un campo, y eso entrena al equipo a ignorarlo.

    **Los tres niveles de un check, y por que hacen falta los tres.** Esta clase
    es el ejemplo del curso, asi que la distincion esta hecha a proposito:

    1. **Por fila** (``pa.Field``): tipo, nulos, rangos que ninguna fila valida
       puede violar. Atrapan registros corruptos. Cota ANCHA, porque los datos
       reales traen basura individual y rechazar la particion entera por 34
       filas de 68.211 seria un contrato que el equipo aprende a desactivar.
    2. **Por distribucion** (``dataframe_check``): la FRACCION de filas fuera de
       rango, el volumen total. Atrapan problemas sistematicos, como un cambio
       de unidades, que ninguna fila individual delata.
    3. **Entre columnas**: la velocidad implicita. Atrapan incoherencias que
       aparecen cuando cada columna, por separado, sigue pareciendo razonable.

    **Limite honesto de todo esto.** Un cambio de escala moderado —millas a
    kilometros es un factor de 1,6— esta en el borde de lo que un contrato
    estatico puede detectar sobre un solo lote: la mediana pasa de 1,85 a 2,98 y
    ambas son plausibles para un taxi. Lo que si lo detecta con fiabilidad es
    comparar la distribucion contra una referencia historica, y eso es
    exactamente monitoreo de drift (sesion 7). No son herramientas que compitan:
    el contrato falla rapido en la frontera, el drift vigila la deriva. Un curso
    que solo ensena una de las dos deja el hueco por el que se cuelan los
    incidentes reales.
    """

    lpep_pickup_datetime: Series[pd.Timestamp] = pa.Field(nullable=False)
    lpep_dropoff_datetime: Series[pd.Timestamp] = pa.Field(nullable=False)
    PULocationID: Series[int] = pa.Field(ge=1, le=265, nullable=False)
    DOLocationID: Series[int] = pa.Field(ge=1, le=265, nullable=False)
    # Cota por FILA deliberadamente ancha. Ver la nota sobre niveles de checks en
    # el docstring de la clase: los datos reales de la TLC traen registros
    # corruptos individuales (en 2023-01 hay 34 viajes de mas de 1.000 millas y
    # uno de 120.098) y rechazar la particion entera por eso seria un contrato
    # inutilizable. Lo unico que se exige aqui es que el valor sea un numero no
    # negativo y no absurdo por ordenes de magnitud.
    trip_distance: Series[float] = pa.Field(ge=0.0, lt=1e6, nullable=False)

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

    @pa.dataframe_check(name="outliers_de_distancia_son_marginales")
    def outliers_de_distancia_son_marginales(cls, df: pd.DataFrame) -> bool:
        """La FRACCION de viajes fuera de rango debe ser marginal.

        Este es el check que atrapa un cambio de unidades, y es de nivel
        distribucion, no de fila. La diferencia importa:

        - Unos pocos registros de 120.000 millas son ruido de captura. Los
          filtramos y seguimos.
        - Que el 1% de los viajes pase de 100 millas significa que la columna
          entera cambio de significado.

        Medido sobre datos reales de la TLC (2023-01): 0,054% de los viajes
        supera las 100 millas. El umbral de 0,3% deja margen de 5x para
        variacion normal entre meses y sigue atrapando una inflacion sistematica.
        """
        if df.empty:
            return True
        fraccion = float((df["trip_distance"] > MAX_MILLAS_PLAUSIBLE).mean())
        return fraccion <= MAX_FRACCION_OUTLIERS

    @pa.dataframe_check(name="velocidad_implicita_plausible")
    def velocidad_implicita_plausible(cls, df: pd.DataFrame) -> bool:
        """La velocidad media implicita debe ser propia de un taxi urbano.

        Es un check de coherencia entre dos columnas: distancia y duracion. Si
        una de las dos cambia de unidad o de escala, la relacion entre ambas se
        rompe aunque cada columna por separado siga pareciendo razonable.

        En Manhattan la mediana ronda las 10-15 mph. Se acepta 2-45 mph, que es
        ancho a proposito: la senal aqui es "algo se rompio", no "el trafico
        estuvo raro".
        """
        minutos = (df["lpep_dropoff_datetime"] - df["lpep_pickup_datetime"]).dt.total_seconds() / 60
        validos = (minutos > 0) & (df["trip_distance"] > 0)
        if validos.sum() < 100:
            return True
        mph = df.loc[validos, "trip_distance"] / (minutos[validos] / 60)
        return bool(2.0 <= float(mph.median()) <= 45.0)


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
