"""Tests del contrato de datos.

El test que importa NO es "el contrato acepta el dato bueno" (eso lo verifica el
pipeline cada vez que corre). El que importa es **"el contrato rechaza el dato
roto"**, porque es el unico que demuestra que el contrato hace algo.

Regla practica para tu proyecto: por cada regla del contrato, un fixture que la
viola. Si borras una regla y ningun test se pone rojo, esa regla no existia.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pandera.errors import SchemaError, SchemaErrors

from miproyecto.data import contract as dc
from miproyecto.data import loaders
from miproyecto.features import contract as fc


def _leer(ruta: Path) -> pd.DataFrame:
    return pd.read_csv(ruta, parse_dates=["ts"])


def test_el_contrato_acepta_el_fixture_valido(ruta_fixture_valido: Path) -> None:
    df = dc.validar_crudos(_leer(ruta_fixture_valido))
    assert len(df) >= dc.VOLUMEN_MINIMO


def test_el_contrato_rechaza_el_fixture_roto(ruta_fixture_roto: Path) -> None:
    """El fixture roto viola cuatro reglas a la vez, a proposito.

    Con ``lazy=True`` se acumulan todos los errores: ves los cuatro problemas de
    una vez en lugar de arreglar uno, re-correr y descubrir el siguiente.
    """
    with pytest.raises((SchemaError, SchemaErrors)) as info:
        dc.validar_crudos(_leer(ruta_fixture_roto))
    mensaje = str(info.value)
    assert "descuento" in mensaje or "precio_unitario" in mensaje


def test_rechaza_volumen_sospechosamente_bajo(ruta_fixture_valido: Path) -> None:
    """Una particion con 5 filas casi nunca es un mes flojo: es una descarga
    cortada. El check no protege el modelo, protege contra silenciar un fallo de
    ingesta."""
    df = _leer(ruta_fixture_valido).head(5)
    with pytest.raises((SchemaError, SchemaErrors)):
        dc.validar_crudos(df)


def test_rechaza_timestamp_futuro(ruta_fixture_valido: Path) -> None:
    df = _leer(ruta_fixture_valido)
    df.loc[df.index[0], "ts"] = pd.Timestamp.now() + pd.Timedelta(days=365)
    with pytest.raises((SchemaError, SchemaErrors)):
        dc.validar_crudos(df)


def test_el_contrato_procesado_pasa_despues_del_pipeline(
    ruta_fixture_valido: Path,
) -> None:
    """Camino completo: crudo -> validar -> limpiar -> features -> validar."""
    df = dc.validar_crudos(_leer(ruta_fixture_valido))
    df = fc.construir_features(loaders.limpiar(df))
    assert len(dc.validar_procesados(df)) == len(df)


def test_split_temporal_exige_datos_ordenados(ruta_fixture_valido: Path) -> None:
    """``train_test_split(shuffle=True)`` sobre datos temporales es un bug.

    Aqui se hace imposible por construccion: si el dataframe no viene ordenado,
    la funcion falla en lugar de producir una metrica optimista.
    """
    df = _leer(ruta_fixture_valido)
    desordenado = df.sample(frac=1.0, random_state=1)
    with pytest.raises(ValueError, match="ordenado"):
        loaders.split_temporal(desordenado)

    train, test = loaders.split_temporal(df.sort_values("ts").reset_index(drop=True))
    assert train["ts"].max() <= test["ts"].min()


def test_el_resumen_del_contrato_expone_las_features() -> None:
    """La model card se genera desde esto: si esta vacio, la model card miente."""
    resumen = dc.resumen_contrato()
    assert resumen["features_categoricas"]
    assert resumen["features_numericas"]
    assert resumen["target"] == [fc.TARGET]
