"""Tests de las metricas globales y por subgrupo."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from taxi.features import contract as fc
from taxi.models import evaluate


def test_metricas_de_una_prediccion_perfecta() -> None:
    y = np.array([1.0, 2.0, 3.0, 4.0])
    metricas = evaluate.metricas_regresion(y, y)
    assert metricas["rmse"] == pytest.approx(0.0)
    assert metricas["mae"] == pytest.approx(0.0)
    assert metricas["r2"] == pytest.approx(1.0)


def test_rmse_es_la_raiz_del_error_cuadratico_medio() -> None:
    """Verifica el valor a mano.

    Existe porque `mean_squared_error(squared=False)` ya no funciona en
    scikit-learn: si alguien "arregla" el import y por error deja el MSE sin
    raiz, todas las comparaciones del gate cambian de escala en silencio.
    """
    y_true = np.array([0.0, 0.0, 0.0, 0.0])
    y_pred = np.array([3.0, -3.0, 3.0, -3.0])
    assert evaluate.metricas_regresion(y_true, y_pred)["rmse"] == pytest.approx(3.0)
    assert evaluate.metricas_regresion(y_true, y_pred)["mae"] == pytest.approx(3.0)


def test_el_prefijo_evita_colisiones_de_nombres() -> None:
    """train y valid se loguean en el mismo run: sin prefijo se pisan."""
    y = np.array([1.0, 2.0, 3.0])
    metricas = evaluate.metricas_regresion(y, y * 1.1, prefijo="valid_")
    assert set(metricas) == {"valid_rmse", "valid_mae", "valid_r2"}


@pytest.mark.parametrize(
    ("hora", "franja"),
    [(0, "madrugada"), (5, "madrugada"), (6, "manana"), (12, "tarde"), (23, "noche")],
)
def test_franjas_horarias_cubren_los_bordes(hora: int, franja: str) -> None:
    serie = pd.Series([hora])
    assert evaluate.franja_horaria(serie).iloc[0] == franja


def test_las_franjas_cubren_las_24_horas() -> None:
    """Sin esto, una hora sin franja caeria en 'desconocida' y el gate no la miraria."""
    etiquetas = evaluate.franja_horaria(pd.Series(range(24)))
    assert "desconocida" not in set(etiquetas)


@pytest.mark.parametrize(
    ("distancia", "rango"),
    [(0.0, "corta"), (0.99, "corta"), (1.0, "media"), (3.0, "larga"), (25.0, "muy_larga")],
)
def test_rangos_de_distancia_cubren_los_bordes(distancia: float, rango: str) -> None:
    assert evaluate.rango_distancia(pd.Series([distancia])).iloc[0] == rango


def test_metricas_por_subgrupo_reporta_los_ocho_subgrupos(
    df_procesado_valido: pd.DataFrame,
) -> None:
    y_true = df_procesado_valido[fc.TARGET_REGRESION].to_numpy(dtype=float)
    subgrupos = evaluate.metricas_por_subgrupo(df_procesado_valido, y_true, y_true * 1.1)

    for franja in evaluate.FRANJAS_HORARIAS:
        assert f"rmse_hora_{franja}" in subgrupos
        assert subgrupos[f"n_hora_{franja}"] >= evaluate.MIN_FILAS_SUBGRUPO
    for nombre, _, _ in evaluate.RANGOS_DISTANCIA:
        assert f"rmse_dist_{nombre}" in subgrupos


def test_metricas_por_subgrupo_omite_los_subgrupos_pequenos(
    df_procesado_valido: pd.DataFrame,
) -> None:
    """Un RMSE de 5 filas esta dominado por el ruido y generaria falsos positivos."""
    pocos = df_procesado_valido.head(20)
    y_true = pocos[fc.TARGET_REGRESION].to_numpy(dtype=float)
    subgrupos = evaluate.metricas_por_subgrupo(pocos, y_true, y_true, min_filas=50)
    assert subgrupos == {}


def test_metricas_por_subgrupo_exige_longitudes_alineadas(
    df_procesado_valido: pd.DataFrame,
) -> None:
    """Un desalineamiento silencioso produciria metricas por subgrupo falsas."""
    y_true = df_procesado_valido[fc.TARGET_REGRESION].to_numpy(dtype=float)
    with pytest.raises(ValueError, match="misma longitud"):
        evaluate.metricas_por_subgrupo(df_procesado_valido, y_true[:-5], y_true[:-5])


def test_una_degradacion_local_no_mueve_el_rmse_global(
    df_procesado_valido: pd.DataFrame,
) -> None:
    """La razon de existir de las metricas por subgrupo, demostrada con numeros.

    Se degrada fuerte la prediccion de un solo subgrupo. El RMSE global apenas se
    mueve; el RMSE del subgrupo se dispara. Si el gate solo mirara el global, esta
    regresion pasaria.
    """
    df = df_procesado_valido
    y_true = df[fc.TARGET_REGRESION].to_numpy(dtype=float)
    y_bueno = y_true + 1.0

    madrugada = evaluate.franja_horaria(df[fc.COL_HORA].reset_index(drop=True)).to_numpy()
    y_malo = y_bueno.copy()
    y_malo[madrugada == "madrugada"] += 8.0

    global_bueno = evaluate.metricas_regresion(y_true, y_bueno)["rmse"]
    global_malo = evaluate.metricas_regresion(y_true, y_malo)["rmse"]
    sub_bueno = evaluate.metricas_por_subgrupo(df, y_true, y_bueno)["rmse_hora_madrugada"]
    sub_malo = evaluate.metricas_por_subgrupo(df, y_true, y_malo)["rmse_hora_madrugada"]

    assert sub_malo / sub_bueno > global_malo / global_bueno


def test_evaluar_modelo_acepta_cualquier_predictor(df_procesado_valido: pd.DataFrame) -> None:
    """El gate mide champion y candidato con el mismo codigo.

    Por eso ``evaluar_modelo`` solo exige un ``predict`` que consuma la lista de
    diccionarios del contrato: sirve para el Pipeline recien entrenado y para el
    pyfunc cargado del registry.
    """

    class Constante:
        def predict(self, entradas: list[dict]) -> np.ndarray:
            return np.full(len(entradas), 15.0)

    globales, subgrupos = evaluate.evaluar_modelo(Constante(), df_procesado_valido)
    assert globales["rmse"] > 0
    assert subgrupos
