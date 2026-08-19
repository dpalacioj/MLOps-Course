"""El contrato de datos acepta lo valido y rechaza cada fixture roto.

Estos tests son la red de seguridad del contrato en si mismo. Un contrato que
nunca se prueba contra datos malos se degrada hasta aceptar cualquier cosa: basta
que alguien relaje un rango para desbloquear un pipeline y nadie lo note. Aqui
cada relajacion rompe un test con nombre explicito.
"""

from __future__ import annotations

import pandas as pd
import pandera.errors as pae
import pytest

from taxi.data import contract as dc
from taxi.features import contract as fc

#: Pandera lanza SchemaError (fallo unico) o SchemaErrors (validacion lazy).
#: No comparten jerarquia, asi que hay que atrapar los dos.
ERRORES_CONTRATO = (pae.SchemaError, pae.SchemaErrors)


def test_contrato_acepta_el_crudo_valido(df_crudo_valido: pd.DataFrame) -> None:
    validado = dc.validar_crudos(df_crudo_valido)
    assert len(validado) == len(df_crudo_valido)
    # strict=False: las columnas extra del parquet real deben sobrevivir.
    assert "total_amount" in validado.columns


@pytest.mark.parametrize(
    ("fixture", "motivo"),
    [
        ("df_crudo_en_kilometros", "trip_distance en km en lugar de millas"),
        ("df_crudo_zona_invalida", "zona fuera del rango 1-265 de la TLC"),
        ("df_crudo_con_nulos", "nulos en una columna obligatoria"),
    ],
)
def test_contrato_rechaza_los_fixtures_rotos(
    request: pytest.FixtureRequest, fixture: str, motivo: str
) -> None:
    """Cada fixture roto debe hacer fallar la validacion del crudo."""
    df = request.getfixturevalue(fixture)
    with pytest.raises(ERRORES_CONTRATO):
        dc.validar_crudos(df)


def test_el_cambio_de_unidades_es_detectable_por_el_rango(
    df_crudo_valido: pd.DataFrame, df_crudo_en_kilometros: pd.DataFrame
) -> None:
    """Documenta POR QUE el fixture de km falla, no solo que falla.

    El contrato no compara unidades (no puede: el numero no las lleva). Lo que
    detecta es que los viajes largos legitimos, al convertirse a km, se salen del
    limite de 100. Si el dataset no tuviera cola larga, este contrato NO
    atraparia el cambio de unidades, y conviene que eso quede escrito.
    """
    assert df_crudo_valido["trip_distance"].max() <= 100.0
    assert df_crudo_en_kilometros["trip_distance"].max() > 100.0


def test_contrato_rechaza_dropoff_anterior_al_pickup(df_crudo_valido: pd.DataFrame) -> None:
    df = df_crudo_valido.copy()
    df.loc[df.index[:2], fc.COL_DROPOFF] = df.loc[df.index[:2], fc.COL_PICKUP] - pd.Timedelta(
        minutes=5
    )
    with pytest.raises(ERRORES_CONTRATO):
        dc.validar_crudos(df)


def test_contrato_rechaza_volumen_insuficiente(df_crudo_valido: pd.DataFrame) -> None:
    """Una particion con 50 filas es una descarga cortada, no un mes de viajes."""
    with pytest.raises(ERRORES_CONTRATO):
        dc.validar_crudos(df_crudo_valido.head(50))


def test_contrato_de_procesados_acepta_el_dataset_listo(
    df_procesado_valido: pd.DataFrame,
) -> None:
    validado = dc.validar_procesados(df_procesado_valido)
    assert set(fc.FEATURES).issubset(validado.columns)
    assert validado[fc.TARGET_CLASIFICACION].nunique() == 2


def test_contrato_de_procesados_rechaza_target_constante(
    df_procesado_valido: pd.DataFrame,
) -> None:
    """Si viaje_largo es todo 0, cualquier clasificador da 100% de accuracy.

    Era el problema del generador sintetico anterior: el target era
    `random.choices([0, 1])`, es decir ruido puro presentado como problema de ML.
    """
    df = df_procesado_valido.copy()
    df[fc.TARGET_CLASIFICACION] = 0
    with pytest.raises(ERRORES_CONTRATO):
        dc.validar_procesados(df)


def test_resumen_contrato_declara_todas_las_features() -> None:
    """La model card se construye con esto: si miente, la card miente."""
    resumen = dc.resumen_contrato()
    declaradas = set(resumen["features_categoricas"]) | set(resumen["features_numericas"])
    assert declaradas == set(fc.FEATURES)
    assert resumen["targets"] == [fc.TARGET_REGRESION, fc.TARGET_CLASIFICACION]
