"""Contrato de datos ejecutable.

Un contrato de datos es un esquema **versionado junto al codigo** que describe
como se ve un dato valido, y que se valida en la FRONTERA del pipeline: donde el
dato entra, no donde se usa.

Por que hace falta: los errores de datos casi nunca lanzan excepciones,
degradan metricas. Si una columna cambia de unidades, o llega una categoria
nueva, o el proveedor empieza a mandar nulos donde antes no habia, el pipeline
entrena sin quejarse, registra una metrica plausible y sirve predicciones malas.
Todo verde, todo mal. El contrato convierte ese fallo silencioso en un fallo
ruidoso, que es incomparablemente mas barato de arreglar.

Que va en el contrato y que va en el test:

- el **contrato** describe como es un dato valido;
- el **test** verifica que el pipeline se comporta como debe ante un dato
  invalido (ver ``tests/data/test_contrato.py``, que usa un fixture roto a
  proposito).

Alternativas y trade-offs:

- **Pandera** (lo que usa este template): in-process, tipado, se integra con
  pytest y con el pipeline. Costo de entrada bajo.
- **Great Expectations Core 1.x**: mas potente para data warehouse y reporting,
  con Data Docs. Mucho mas pesado. Ojo: su API cambio por completo respecto a
  0.18, asi que la mayoria de los tutoriales de la web estan obsoletos.
- **Pydantic**: correcto para I/O de una API (un registro a la vez), no para
  DataFrames. En este proyecto se usa en ``api/schemas.py``, que es otra
  frontera.

TODO(estudiante) 10: este contrato tiene 6 reglas. Necesitas al menos 6 reglas
NO TRIVIALES sobre TU dataset. "la columna existe" no cuenta como regla; los
rangos de negocio, las relaciones entre columnas y los volumenes minimos si.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series

from miproyecto.features import contract as fc

# =============================================================================
# Limites de negocio. Aqui, no repartidos por el codigo.
# =============================================================================
#: Volumen minimo por particion. Una particion con 12 filas casi siempre
#: significa que la descarga se corto, no que hubo 12 eventos ese mes. Este
#: check no protege el modelo: protege contra silenciar un fallo de ingesta.
VOLUMEN_MINIMO: Final[int] = 100
CANTIDAD_MIN: Final[float] = 0.0
CANTIDAD_MAX: Final[float] = 10_000.0
PRECIO_MIN: Final[float] = 0.0
PRECIO_MAX: Final[float] = 1_000_000.0


class RegistrosCrudos(pa.DataFrameModel):
    """Contrato del dato tal como llega del proveedor.

    ``strict = False`` a proposito: la fuente trae columnas que no usamos, y un
    contrato que exija ausencia de columnas extra se rompe cada vez que el
    proveedor agrega un campo. Eso entrena al equipo a ignorar el contrato, que
    es el peor resultado posible.

    ``coerce = True`` convierte tipos compatibles (un entero leido como float,
    una fecha leida como string). Lo que NO hace es inventar datos: si el valor
    no es convertible, falla.
    """

    ts: Series[pd.Timestamp] = pa.Field(nullable=False)
    categoria: Series[str] = pa.Field(nullable=True)
    region: Series[str] = pa.Field(nullable=True)
    canal: Series[str] = pa.Field(nullable=True)
    # Los nulos SI se permiten donde son reales, y se documenta la estrategia de
    # imputacion en el pipeline. Prohibir nulos que el proveedor manda de verdad
    # convierte el contrato en un generador de falsos positivos.
    cantidad: Series[float] = pa.Field(ge=CANTIDAD_MIN, le=CANTIDAD_MAX, nullable=True)
    precio_unitario: Series[float] = pa.Field(ge=PRECIO_MIN, le=PRECIO_MAX, nullable=True)
    descuento: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=True)

    class Config:
        strict = False
        coerce = True

    @pa.dataframe_check(name="volumen_minimo")
    def volumen_minimo(cls, df: pd.DataFrame) -> bool:
        """Alerta si el volumen cae drasticamente."""
        return len(df) >= VOLUMEN_MINIMO

    @pa.dataframe_check(name="eje_temporal_sin_futuro")
    def eje_temporal_sin_futuro(cls, df: pd.DataFrame) -> Series[bool]:
        """Ningun evento puede tener fecha futura.

        Un timestamp en el futuro suele ser un bug de unidades (milisegundos
        leidos como segundos) o de zona horaria. Si entra al entrenamiento, el
        split temporal queda mal y la metrica reportada es optimista sin que
        nada falle.
        """
        return df["ts"] <= pd.Timestamp.now()

    @pa.dataframe_check(name="descuento_coherente_con_precio")
    def descuento_coherente_con_precio(cls, df: pd.DataFrame) -> Series[bool]:
        """Relacion entre columnas: no puede haber descuento sin precio.

        Este es el tipo de regla que un contrato aporta y un `dtype` no: la
        validez no esta en una columna, esta en la combinacion.
        """
        return ~(df["descuento"].fillna(0) > 0) | df["precio_unitario"].notna()


class RegistrosProcesados(pa.DataFrameModel):
    """Contrato del dataset listo para entrenar.

    Los rangos son mas duros que en el crudo: si algo llega hasta aqui fuera de
    rango, el bug esta en NUESTRO pipeline y no en el proveedor. Distinguir esas
    dos situaciones es la razon de tener dos contratos y no uno.
    """

    segmento: Series[str] = pa.Field(nullable=False)
    categoria: Series[str] = pa.Field(nullable=False)
    region: Series[str] = pa.Field(nullable=False)
    canal: Series[str] = pa.Field(nullable=False)
    cantidad: Series[float] = pa.Field(ge=CANTIDAD_MIN, le=CANTIDAD_MAX, nullable=False)
    precio_unitario: Series[float] = pa.Field(ge=PRECIO_MIN, le=PRECIO_MAX, nullable=False)
    descuento: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=False)
    hora: Series[int] = pa.Field(ge=0, le=23, nullable=False)
    dia_semana: Series[int] = pa.Field(ge=0, le=6, nullable=False)
    mes: Series[int] = pa.Field(ge=1, le=12, nullable=False)
    objetivo: Series[float] = pa.Field(nullable=False)

    class Config:
        strict = False
        coerce = True

    @pa.dataframe_check(name="target_no_constante")
    def target_no_constante(cls, df: pd.DataFrame) -> bool:
        """El target tiene que variar.

        Si el target es constante, cualquier modelo parece perfecto y el
        estudiante aprende la leccion equivocada. Es el check que atrapa un
        filtro demasiado agresivo aguas arriba.
        """
        return df["objetivo"].nunique() > 1


def validar_crudos(df: pd.DataFrame, *, lazy: bool = True) -> pd.DataFrame:
    """Valida el dataframe crudo contra el contrato.

    Args:
        df: dataframe recien leido de la fuente.
        lazy: si es True, acumula TODOS los errores antes de fallar. Conviene
            True mientras desarrollas: ves los cinco problemas de una vez en
            lugar de arreglar uno, re-correr y descubrir el siguiente.

    Raises:
        pandera.errors.SchemaError | SchemaErrors: con el detalle de que fallo.
    """
    return RegistrosCrudos.validate(df, lazy=lazy)


def validar_procesados(df: pd.DataFrame, *, lazy: bool = True) -> pd.DataFrame:
    """Valida el dataframe procesado contra el contrato."""
    return RegistrosProcesados.validate(df, lazy=lazy)


def resumen_contrato() -> dict[str, list[str]]:
    """Devuelve el contrato como diccionario, para documentarlo o loguearlo.

    Lo consume el generador de la model card: la model card debe declarar contra
    que esquema de datos se entreno el modelo, o no sirve para auditar nada.
    """
    return {
        "crudas_requeridas": fc.COLUMNAS_CRUDAS_REQUERIDAS,
        "features_categoricas": fc.FEATURES_CATEGORICAS,
        "features_numericas": fc.FEATURES_NUMERICAS,
        "target": [fc.TARGET],
    }
