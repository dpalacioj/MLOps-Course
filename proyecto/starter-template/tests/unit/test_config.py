"""Tests de coherencia de la configuracion.

Estos tests parecen triviales y no lo son: cada uno corresponde a un bug real y
silencioso que solo se descubre cuando ya contaminaste una metrica.
"""

from __future__ import annotations

from miproyecto import config
from miproyecto.models import train


def test_particiones_no_se_solapan() -> None:
    """Ninguna particion puede estar en dos conjuntos a la vez.

    Si el holdout aparece tambien en entrenamiento, la metrica del gate es una
    metrica de entrenamiento disfrazada y el gate aprueba cualquier cosa.
    """
    train_set = {p.etiqueta for p in config.PARTICIONES_TRAIN}
    produccion = {p.etiqueta for p in config.PARTICIONES_PRODUCCION}
    valid = config.PARTICION_VALID.etiqueta
    test = config.PARTICION_TEST.etiqueta

    assert valid not in train_set
    assert test not in train_set
    assert valid != test
    assert not (train_set & produccion)
    assert test not in produccion


def test_particiones_en_orden_temporal() -> None:
    """train < valid < test. Entrenar con el futuro y validar con el pasado es
    leakage, y con etiquetas ordenables se detecta de forma barata."""
    assert max(p.etiqueta for p in config.PARTICIONES_TRAIN) < config.PARTICION_VALID.etiqueta
    assert config.PARTICION_VALID.etiqueta < config.PARTICION_TEST.etiqueta


def test_uri_del_modelo_usa_alias_no_stage() -> None:
    """El curso usa aliases; los stages estan deprecados desde MLflow 2.9."""
    uri = config.uri_modelo()
    assert uri.startswith("models:/")
    assert "@" in uri
    assert "/Production" not in uri


def test_umbrales_en_rango_razonable() -> None:
    """Un umbral de drift de 0 alerta siempre; uno de 1 nunca alerta."""
    assert 0.0 < config.UMBRAL_DRIFT_COLUMNAS < 1.0
    assert 0.0 < config.ALFA_DRIFT < 0.5
    assert config.MEJORA_MINIMA_RELATIVA > 0.0, (
        "con mejora minima 0, empatar promueve y el modelo rota por puro ruido"
    )


def test_early_stopping_tiene_margen() -> None:
    """``n_iter_no_change`` debe ser menor que ``max_iter``.

    Si no, el early stopping no puede dispararse nunca: la constante existe, se
    ve profesional y no hace absolutamente nada.
    """
    assert train.PARAMS["n_iter_no_change"] < train.PARAMS["max_iter"]


def test_la_semilla_se_propaga_al_modelo() -> None:
    """Una semilla declarada que el estimador no recibe no reproduce nada."""
    assert train.PARAMS["random_state"] == config.SEMILLA
