"""Tests del gate de promocion.

La razon de ser de estos tests: el gate es la pieza que decide que llega a
produccion. Si solo se prueba "en vivo", se prueba una vez y despues se confia.
Como la politica esta en funciones puras, se puede probar el caso que importa de
verdad —que RECHACE— sin levantar MLflow.
"""

from __future__ import annotations

import pytest

from miproyecto.models import promote


def test_sin_champion_se_promueve_como_linea_base() -> None:
    decision = promote.decidir({"rmse": 10.0}, None)
    assert decision.promover
    assert "linea base" in decision.motivo


def test_rechaza_candidato_peor() -> None:
    decision = promote.decidir({"rmse": 12.0}, {"rmse": 10.0})
    assert not decision.promover
    assert decision.delta_relativo is not None and decision.delta_relativo > 0


def test_rechaza_mejora_dentro_del_ruido() -> None:
    """Mejorar un 0.2% con un margen exigido del 1% no alcanza.

    Este es el test que evita el churn de modelos: sin margen minimo, cada
    reentrenamiento produce un "ganador" que solo refleja el muestreo.
    """
    decision = promote.decidir({"rmse": 9.98}, {"rmse": 10.0}, mejora_minima=0.01)
    assert not decision.promover
    assert "ruido" in decision.motivo


def test_acepta_mejora_significativa() -> None:
    decision = promote.decidir({"rmse": 8.5}, {"rmse": 10.0}, mejora_minima=0.01)
    assert decision.promover


def test_rechaza_si_degrada_un_subgrupo() -> None:
    """Mejora global, degradacion local: se rechaza.

    Es el caso que la metrica global esconde y el que produce los incidentes de
    equidad mas caros.
    """
    decision = promote.decidir(
        {"rmse": 8.0},
        {"rmse": 10.0},
        subgrupos_candidato={"rmse_norte": 7.0, "rmse_sur": 20.0},
        subgrupos_champion={"rmse_norte": 9.0, "rmse_sur": 11.0},
        umbral_subgrupo=0.10,
    )
    assert not decision.promover
    assert decision.subgrupos_degradados == ["rmse_sur"]


def test_no_promueve_si_los_datos_no_son_validos() -> None:
    """Una metrica medida sobre datos invalidos no significa nada."""
    decision = promote.decidir({"rmse": 1.0}, {"rmse": 10.0}, datos_validos=False)
    assert not decision.promover
    assert "tests de datos" in decision.motivo


def test_subgrupo_nuevo_no_cuenta_como_degradacion() -> None:
    """Una categoria que aparece por primera vez no tiene con que compararse."""
    degradados = promote.subgrupos_degradados(
        {"rmse_norte": 9.0, "rmse_nuevo": 99.0},
        {"rmse_norte": 9.0},
    )
    assert degradados == []


def test_delta_relativo_sin_linea_base_falla_explicito() -> None:
    with pytest.raises(ZeroDivisionError):
        promote.delta_relativo(1.0, 0.0)
