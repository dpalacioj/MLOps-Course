"""Tests del modulo de monitoreo. Sin red, sin MLflow, sin datos de la TLC.

Que se verifica y por que
-------------------------
El test que mas se olvida en un detector de drift es el **control negativo**: que
no reporte drift cuando las dos muestras vienen de la misma distribucion. Sin el,
un detector que devuelve `True` siempre pasa todos los demas tests. Aqui hay tres
controles negativos explicitos (numerico, categorico y a nivel de dataset).

El segundo test que importa es el de la **trampa del p-valor**: con n grande y una
diferencia irrelevante, el criterio por p-valor grita drift y el criterio por
tamano de efecto no. Es la leccion central del modulo convertida en assert, de
modo que si alguien "simplifica" el codigo volviendo a `p < 0.05` el test falla y
explica por que.

Los dataframes son sinteticos a proposito. Las particiones reales estan detras de
descargas de la TLC, y un test unitario que necesita red no se corre.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from taxi.features import contract as fc
from taxi.monitoring import check_drift as cd
from taxi.monitoring import estadistico as est
from taxi.monitoring import reporte

SEMILLA = 20260819


# =============================================================================
# Datos sinteticos
# =============================================================================
def sintetico(
    n: int = 4000,
    *,
    semilla: int,
    escala_distancia: float = 3.0,
    media_duracion: float = 15.0,
    zonas: tuple[str, ...] = ("41", "42", "43", "74", "75"),
) -> pd.DataFrame:
    """Dataframe con las columnas del contrato del curso.

    Se usan los nombres reales de `taxi.features.contract` y no nombres inventados
    para que el test falle si el contrato cambia: un detector que vigila columnas
    que ya no existen no vigila nada.
    """
    rng = np.random.default_rng(semilla)
    df = pd.DataFrame(
        {
            "trip_distance": rng.exponential(escala_distancia, n),
            "hora_pickup": rng.integers(0, 24, n).astype("int16"),
            "dia_semana_pickup": rng.integers(0, 7, n).astype("int16"),
            "PULocationID": rng.choice(list(zonas), n),
            "DOLocationID": rng.choice(list(zonas), n),
            fc.TARGET_REGRESION: rng.normal(media_duracion, 5.0, n).clip(1, 60),
        }
    )
    df[fc.COL_RUTA] = df["PULocationID"] + "_" + df["DOLocationID"]
    return df


@pytest.fixture
def referencia() -> pd.DataFrame:
    return sintetico(semilla=SEMILLA)


@pytest.fixture
def actual_sin_drift() -> pd.DataFrame:
    """Misma distribucion, otra realizacion. El control negativo."""
    return sintetico(semilla=SEMILLA + 1)


@pytest.fixture
def actual_con_drift() -> pd.DataFrame:
    """Distancias mas largas, duraciones mas largas y zonas nuevas."""
    return sintetico(
        semilla=SEMILLA + 2,
        escala_distancia=5.0,
        media_duracion=22.0,
        zonas=("41", "42", "200", "201", "202"),
    )


# =============================================================================
# 1-2. Los tests detectan el drift que hay
# =============================================================================
def test_ks_detecta_drift_numerico(
    referencia: pd.DataFrame, actual_con_drift: pd.DataFrame
) -> None:
    resultado = est.evaluar_numerica(
        referencia["trip_distance"],
        actual_con_drift["trip_distance"],
        columna="trip_distance",
    )
    assert resultado.drift is True
    assert resultado.metodo == "ks_2samp"
    assert resultado.p_valor is not None and resultado.p_valor < est.ALFA
    assert resultado.tamano_efecto is not None
    assert resultado.tamano_efecto >= est.umbral_de("trip_distance", est.TIPO_NUMERICA)
    # El estadistico del KS ES el tamano de efecto; que coincidan no es casual.
    assert resultado.estadistico == pytest.approx(resultado.tamano_efecto)


def test_chi2_detecta_drift_categorico(
    referencia: pd.DataFrame, actual_con_drift: pd.DataFrame
) -> None:
    resultado = est.evaluar_categorica(
        referencia["PULocationID"],
        actual_con_drift["PULocationID"],
        columna="PULocationID",
    )
    assert resultado.drift is True
    assert resultado.metodo == "chi2_contingency"
    assert resultado.nombre_efecto == "cramer_v"
    # Las zonas 200, 201 y 202 no existen en la referencia.
    assert resultado.categorias_nuevas == 3
    assert "categorias nuevas" in resultado.motivo


# =============================================================================
# 3. Control negativo: el test que mas gente olvida
# =============================================================================
def test_control_negativo_sin_drift_en_ninguna_columna(
    referencia: pd.DataFrame, actual_sin_drift: pd.DataFrame
) -> None:
    """Dos muestras de la misma distribucion no deben producir NINGUNA alerta.

    Si este test falla, el detector tiene un falso positivo sistematico y en
    produccion generaria alert fatigue: el equipo aprende a ignorar la alerta y
    el dia del drift real nadie mira.
    """
    resultado = est.detectar_drift(
        referencia,
        actual_sin_drift,
        columnas_numericas=[*fc.FEATURES_NUMERICAS, fc.TARGET_REGRESION],
        columnas_categoricas=fc.FEATURES_CATEGORICAS,
    )
    columnas_marcadas = [c.columna for c in resultado.con_drift]
    assert columnas_marcadas == [], f"falsos positivos: {columnas_marcadas}"
    assert resultado.fraccion_con_drift == 0.0
    assert resultado.hay_drift is False
    assert resultado.avisos == ()


# =============================================================================
# 4. La trampa del p-valor con n grande
# =============================================================================
def test_p_valor_solo_es_criterio_malo_con_n_grande() -> None:
    """Con n=60.000 y una diferencia trivial, el p-valor grita y el efecto no.

    Este es el assert que documenta por que el modulo no usa `p < 0.05`.
    """
    rng = np.random.default_rng(7)
    n = 60_000
    ref = pd.Series(rng.normal(0.0, 1.0, n))
    act = pd.Series(rng.normal(0.05, 1.0, n))  # media desplazada 5% de una sigma

    por_efecto = est.evaluar_numerica(ref, act, columna="x", criterio="efecto")
    por_p = est.evaluar_numerica(ref, act, columna="x", criterio="p_valor")

    assert por_p.p_valor is not None and por_p.p_valor < est.ALFA
    assert por_p.drift is True, "el criterio por p-valor deberia declarar drift"
    assert por_efecto.drift is False, "el criterio por tamano de efecto no deberia"
    assert por_efecto.tamano_efecto is not None
    assert por_efecto.tamano_efecto < est.UMBRAL_KS
    assert "no por su magnitud" in por_efecto.motivo


# =============================================================================
# 5. PSI crece con la magnitud del cambio
# =============================================================================
def test_psi_crece_con_la_magnitud_del_cambio() -> None:
    """El PSI tiene que ordenar los cambios, no solo detectarlos.

    Se compara la referencia contra desplazamientos crecientes de la media y se
    exige monotonia. Es lo que permite usar el PSI como serie temporal de
    vigilancia en lugar de como semaforo.
    """
    rng = np.random.default_rng(11)
    n = 20_000
    ref = pd.Series(rng.normal(0.0, 1.0, n))
    valores = [est.psi(ref, pd.Series(rng.normal(d, 1.0, n))) for d in (0.0, 0.25, 0.5, 1.0, 2.0)]

    assert valores == sorted(valores), f"PSI no monotono: {valores}"
    assert valores[0] < est.PSI_MODERADO, "PSI de la referencia contra si misma deberia ser ~0"
    assert valores[-1] > est.PSI_ALTO


def test_jensen_shannon_acotada_y_cero_en_identicas(referencia: pd.DataFrame) -> None:
    """La distancia de Jensen-Shannon vive en [0, 1]; el PSI no tiene techo."""
    serie = referencia["trip_distance"]
    assert est.distancia_jensen_shannon(serie, serie) == pytest.approx(0.0, abs=1e-9)
    otra = sintetico(semilla=99, escala_distancia=20.0)["trip_distance"]
    distancia = est.distancia_jensen_shannon(serie, otra)
    assert 0.0 < distancia <= 1.0


def test_v_de_cramer_no_depende_del_tamano_de_muestra() -> None:
    """El chi-cuadrado crece con n; la V de Cramer no. Por eso es el tamano de efecto."""
    tabla = np.array([[60.0, 40.0], [40.0, 60.0]])
    chi2_pequeno = 8.0
    v_pequeno = est.v_de_cramer(tabla, chi2_pequeno)
    # Se multiplica la tabla y el chi-cuadrado por 10: misma proporcion, mas datos.
    v_grande = est.v_de_cramer(tabla * 10.0, chi2_pequeno * 10.0)
    assert v_pequeno == pytest.approx(v_grande)


# =============================================================================
# 6. Agregacion: fraccion de columnas con drift
# =============================================================================
def _resultado_falso(marcas: list[bool], umbral: float) -> est.ResultadoDrift:
    columnas = tuple(
        est.ResultadoColumna(
            columna=f"c{i}",
            tipo=est.TIPO_NUMERICA,
            metodo="ks_2samp",
            drift=marca,
            motivo="fixture",
        )
        for i, marca in enumerate(marcas)
    )
    return est.ResultadoDrift(
        motor="estadistico", criterio="efecto", columnas=columnas, umbral_columnas=umbral
    )


@pytest.mark.parametrize(
    ("marcas", "umbral", "fraccion", "alerta"),
    [
        ([False] * 4, 0.30, 0.00, False),
        ([True, False, False, False], 0.30, 0.25, False),  # 25% <= 30%: sin alerta
        ([True, True, False, False], 0.30, 0.50, True),
        ([True] * 4, 0.30, 1.00, True),
        ([True, False, False], 0.30, pytest.approx(1 / 3), True),  # justo por encima
        ([], 0.30, 0.00, False),  # sin columnas: no divide por cero
    ],
)
def test_fraccion_de_columnas_con_drift(
    marcas: list[bool], umbral: float, fraccion: Any, alerta: bool
) -> None:
    resultado = _resultado_falso(marcas, umbral)
    assert resultado.fraccion_con_drift == fraccion
    assert resultado.hay_drift is alerta


# =============================================================================
# 7. Exit code: el contrato con el CI
# =============================================================================
def test_exit_code_depende_del_umbral(
    tmp_path: Path, referencia: pd.DataFrame, actual_con_drift: pd.DataFrame
) -> None:
    """Mismos datos, dos umbrales, dos exit codes. Es lo que hace fallar el CI."""
    datos = {"referencia": referencia, "actual": actual_con_drift}
    comun: dict[str, Any] = {
        "datos": datos,
        "salida": tmp_path,
        "usar_evidently": False,
        "mlflow_tracking": False,
    }

    estricto = cd.ejecutar_check(umbral=0.30, **comun)
    permisivo = cd.ejecutar_check(umbral=0.99, **comun)

    assert estricto.drift.fraccion_con_drift > 0.30
    assert estricto.codigo_salida == cd.EXIT_DRIFT
    assert permisivo.codigo_salida == cd.EXIT_OK
    assert permisivo.drift.fraccion_con_drift == estricto.drift.fraccion_con_drift


def test_exit_code_sin_columnas_evaluables_no_es_ok(tmp_path: Path) -> None:
    """No poder medir no es lo mismo que estar bien: exit code 2, no 0."""
    vacio = pd.DataFrame({"columna_que_no_esta_en_el_contrato": [1.0, 2.0, 3.0]})
    resultado = cd.ejecutar_check(
        datos={"referencia": vacio, "actual": vacio},
        salida=tmp_path,
        usar_evidently=False,
        mlflow_tracking=False,
    )
    assert resultado.drift.columnas == ()
    assert resultado.codigo_salida == cd.EXIT_NO_EVALUABLE


def test_check_sin_drift_pasa(
    tmp_path: Path, referencia: pd.DataFrame, actual_sin_drift: pd.DataFrame
) -> None:
    """Control negativo a nivel de check completo, incluidos los artefactos."""
    resultado = cd.ejecutar_check(
        datos={"referencia": referencia, "actual": actual_sin_drift},
        salida=tmp_path,
        usar_evidently=False,
        mlflow_tracking=False,
    )
    assert resultado.codigo_salida == cd.EXIT_OK
    assert resultado.ruta_json is not None and resultado.ruta_json.exists()
    contenido = json.loads(resultado.ruta_json.read_text(encoding="utf-8"))
    assert contenido["hay_drift"] is False
    assert contenido["metadatos"]["codigo_salida"] == cd.EXIT_OK


def test_evidently_sin_columnas_del_contrato_falla_con_mensaje_util() -> None:
    """El motivo de la degradacion tiene que nombrar el problema real.

    Sin la guarda, Evidently calcula la fraccion de columnas con drift sobre cero
    columnas y lanza `ZeroDivisionError`. El check degradaria igual, pero el
    estudiante veria "ZeroDivisionError" en lugar de "falta la columna X del
    contrato", que es lo que tiene que arreglar.
    """
    ajeno = pd.DataFrame({"columna_ajena": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="ninguna columna del contrato"):
        cd.reporte_evidently(ajeno, ajeno, salida=Path("no_se_escribe.html"), umbral_columnas=0.3)


def test_check_degrada_a_scipy_y_lo_dice(
    tmp_path: Path, referencia: pd.DataFrame, actual_con_drift: pd.DataFrame
) -> None:
    """Sin Evidently el check sigue midiendo: se pierde el HTML, no la senal.

    Se usa el flag `usar_evidently=False`, que recorre el mismo camino que toma el
    check cuando la libreria no esta instalada o cuando su API cambio. Es el test
    que respalda la promesa de "degrada con elegancia": si el fallback no diera
    veredicto ni exit code, la degradacion seria una falsa tranquilidad.
    """
    con_evidently_desactivado = cd.ejecutar_check(
        datos={"referencia": referencia, "actual": actual_con_drift},
        salida=tmp_path,
        usar_evidently=False,
        mlflow_tracking=False,
    )
    assert con_evidently_desactivado.drift.motor == "estadistico"
    assert con_evidently_desactivado.ruta_html is None
    assert con_evidently_desactivado.ruta_json is not None
    # Sin Evidently no hay HTML, pero SI hay veredicto y exit code.
    assert con_evidently_desactivado.codigo_salida == cd.EXIT_DRIFT
    texto = cd.formatear(con_evidently_desactivado)
    assert "Motor: estadistico" in texto


# =============================================================================
# 8. Traduccion del dict de Evidently
# =============================================================================
def _dict_evidently(*, con_tests: bool = True) -> dict[str, Any]:
    """Reproduce la forma REAL del dict de Evidently 0.7.21 (verificada)."""
    metricas: list[dict[str, Any]] = [
        {
            "metric_name": "DriftedColumnsCount(drift_share=0.5)",
            "config": {"type": "evidently:metric_v2:DriftedColumnsCount", "drift_share": 0.5},
            "value": {"count": 1.0, "share": 0.5},
        },
        {
            "metric_name": "ValueDrift(column=trip_distance,method=ks,threshold=0.05)",
            "config": {
                "type": "evidently:metric_v2:ValueDrift",
                "column": "trip_distance",
                "method": "ks",
                "threshold": 0.05,
            },
            "value": 0.0001,
        },
        {
            "metric_name": "ValueDrift(column=PU_DO,method=Jensen-Shannon distance,threshold=0.1)",
            "config": {
                "type": "evidently:metric_v2:ValueDrift",
                "column": "PU_DO",
                "method": "Jensen-Shannon distance",
                "threshold": 0.1,
            },
            "value": 0.02,
        },
    ]
    bruto: dict[str, Any] = {"metrics": metricas, "tests": []}
    if con_tests:
        bruto["tests"] = [
            {
                "name": "Value Drift for column trip_distance",
                "metric_config": {
                    "params": {
                        "type": "evidently:metric_v2:ValueDrift",
                        "column": "trip_distance",
                        "method": "ks",
                        "threshold": 0.05,
                    }
                },
                "status": "FAIL",
            },
            {
                "name": "Value Drift for column PU_DO",
                "metric_config": {
                    "params": {
                        "type": "evidently:metric_v2:ValueDrift",
                        "column": "PU_DO",
                        "method": "Jensen-Shannon distance",
                        "threshold": 0.1,
                    }
                },
                "status": "SUCCESS",
            },
        ]
    return bruto


def test_desde_evidently_lee_columnas_y_veredicto() -> None:
    resultado = reporte.desde_evidently(
        _dict_evidently(),
        columnas_numericas=["trip_distance"],
        columnas_categoricas=["PU_DO"],
    )
    assert resultado.motor == "evidently"
    por_columna = {c.columna: c for c in resultado.columnas}
    assert set(por_columna) == {"trip_distance", "PU_DO"}
    assert por_columna["trip_distance"].drift is True
    assert por_columna["PU_DO"].drift is False
    # Con un metodo de p-valor el score va a p_valor; con una distancia, a efecto.
    assert por_columna["trip_distance"].p_valor == pytest.approx(0.0001)
    assert por_columna["trip_distance"].tamano_efecto is None
    assert por_columna["PU_DO"].tamano_efecto == pytest.approx(0.02)
    assert por_columna["PU_DO"].p_valor is None
    assert resultado.fraccion_con_drift == pytest.approx(0.5)


def test_desde_evidently_sin_tests_usa_el_sentido_correcto_de_comparacion() -> None:
    """Sin la seccion `tests`, un p-valor se compara al reves que una distancia.

    p pequeno = drift; distancia pequena = sin drift. Invertirlo es el error mas
    facil al leer el dict a mano, y aqui queda fijado.
    """
    resultado = reporte.desde_evidently(_dict_evidently(con_tests=False))
    por_columna = {c.columna: c for c in resultado.columnas}
    assert por_columna["trip_distance"].drift is True  # p=0.0001 < 0.05
    assert por_columna["PU_DO"].drift is False  # js=0.02 < 0.1


@pytest.mark.parametrize(
    "bruto",
    [
        {},  # dict vacio
        {"metrics": None},  # clave presente con tipo inesperado
        {"metrics": []},  # sin metricas
        {"metrics": [{"config": {"type": "evidently:metric_v2:ValueDrift"}, "value": 0.5}]},
        {"metrics": [{"no_hay_config": True}]},
        {"metrics": [{"config": {"type": "otra:cosa"}, "value": 1}], "tests": None},
    ],
)
def test_desde_evidently_no_rompe_si_falta_una_clave(bruto: dict[str, Any]) -> None:
    """Un cambio de formato de la libreria degrada el reporte; no tumba el pipeline.

    Es el punto del aislamiento: el resto del sistema sigue viendo un
    `ResultadoDrift` valido y el problema aparece como aviso, no como stack trace.
    """
    resultado = reporte.desde_evidently(bruto)
    assert isinstance(resultado, est.ResultadoDrift)
    assert resultado.columnas == ()
    assert resultado.hay_drift is False
    assert resultado.avisos, "un dict incompleto tiene que dejar un aviso visible"


def test_metrica_agregada_de_evidently_se_puede_contrastar() -> None:
    cuenta, fraccion = reporte.columnas_con_drift_segun_evidently(_dict_evidently())
    assert cuenta == 1
    assert fraccion == pytest.approx(0.5)
    assert reporte.columnas_con_drift_segun_evidently({}) == (None, None)


# =============================================================================
# 9. Reporte y serializacion
# =============================================================================
def test_json_es_serializable_y_trae_lo_que_el_ci_necesita(
    tmp_path: Path, referencia: pd.DataFrame, actual_con_drift: pd.DataFrame
) -> None:
    resultado = est.detectar_drift(
        referencia,
        actual_con_drift,
        columnas_numericas=fc.FEATURES_NUMERICAS,
        columnas_categoricas=fc.FEATURES_CATEGORICAS,
    )
    destino = reporte.a_json(resultado, tmp_path / "drift.json")
    contenido = json.loads(destino.read_text(encoding="utf-8"))

    for clave in ("hay_drift", "fraccion_con_drift", "columnas_con_drift", "detalle", "motor"):
        assert clave in contenido
    assert isinstance(contenido["hay_drift"], bool)
    # Nada de numpy ni de NaN: json.dumps ya paso, pero se verifica el tipo real.
    assert isinstance(contenido["fraccion_con_drift"], float)


def test_metricas_para_tracking_solo_devuelve_floats() -> None:
    """MLflow rechaza metricas no numericas; los None se filtran antes."""
    columnas = (
        est.ResultadoColumna(
            columna="trip_distance",
            tipo=est.TIPO_NUMERICA,
            metodo="ks_2samp",
            drift=True,
            motivo="fixture",
            tamano_efecto=0.2,
            p_valor=0.001,
            psi=None,  # una metrica ausente no debe aparecer en el dict
            jensen_shannon=0.3,
        ),
    )
    resultado = est.ResultadoDrift(
        motor="estadistico", criterio="efecto", columnas=columnas, umbral_columnas=0.3
    )
    metricas = reporte.metricas_para_tracking(resultado)
    assert all(isinstance(v, float) for v in metricas.values())
    assert "drift_trip_distance_psi" not in metricas
    assert metricas["drift_trip_distance_detectado"] == 1.0
    assert metricas["drift_alerta"] == 1.0


def test_resumen_explica_las_significativas_no_relevantes() -> None:
    """La salida de consola tiene que ensenar, no solo informar."""
    rng = np.random.default_rng(3)
    n = 60_000
    ref = pd.DataFrame({"trip_distance": rng.normal(0.0, 1.0, n)})
    act = pd.DataFrame({"trip_distance": rng.normal(0.05, 1.0, n)})
    resultado = est.detectar_drift(
        ref, act, columnas_numericas=["trip_distance"], columnas_categoricas=[]
    )
    texto = reporte.resumen(resultado)
    assert "Significativas pero NO relevantes" in texto
    assert "VEREDICTO: sin alerta" in texto


# =============================================================================
# 10. Robustez del motor estadistico
# =============================================================================
def test_columna_ausente_se_reporta_como_aviso_no_como_drift(referencia: pd.DataFrame) -> None:
    """Una columna que desaparece es un problema de contrato (S02), no de drift.

    Mezclarlos esconde el mas grave de los dos: el modelo esta recibiendo un
    esquema distinto del que espera.
    """
    sin_columna = referencia.drop(columns=["trip_distance"])
    resultado = est.detectar_drift(
        referencia,
        sin_columna,
        columnas_numericas=["trip_distance", "hora_pickup"],
        columnas_categoricas=[],
    )
    assert [c.columna for c in resultado.columnas] == ["hora_pickup"]
    assert any("trip_distance" in aviso for aviso in resultado.avisos)


def test_bordes_por_cuantiles_abre_los_extremos() -> None:
    """Un valor mas extremo que todo lo visto en entrenamiento debe caer dentro.

    Con bordes cerrados desapareceria del histograma, y es justo la observacion
    que mas informacion aporta sobre el drift.
    """
    bordes = est.bordes_por_cuantiles(pd.Series(np.arange(100.0)))
    assert bordes[0] == -np.inf
    assert bordes[-1] == np.inf
    _, p_act = est._proporciones_numericas(pd.Series(np.arange(100.0)), pd.Series([1e9, 1e9, 1e9]))
    assert p_act[-1] == pytest.approx(1.0)


def test_criterio_invalido_falla_temprano(referencia: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="criterio invalido"):
        est.detectar_drift(
            referencia,
            referencia,
            columnas_numericas=["trip_distance"],
            columnas_categoricas=[],
            criterio="magia",  # type: ignore[arg-type]
        )


def test_muestra_vacia_no_es_drift() -> None:
    resultado = est.evaluar_numerica(
        pd.Series([1.0, 2.0, 3.0]), pd.Series([], dtype="float64"), columna="x"
    )
    assert resultado.drift is False
    assert "no evaluable" in resultado.motivo


def test_particion_desde_etiqueta_valida_el_formato() -> None:
    assert cd.particion_desde_etiqueta("2024-01").etiqueta == "2024-01"
    with pytest.raises(ValueError, match="Etiqueta de particion invalida"):
        cd.particion_desde_etiqueta("enero-2024")
    with pytest.raises(ValueError, match="Mes fuera de rango"):
        cd.particion_desde_etiqueta("2024-13")


def test_nombre_del_reporte_dice_que_compara() -> None:
    """Un nombre fijo se sobreescribe en cada corrida y borra el historico."""
    nombre = cd.nombre_reporte(cd.PARTICIONES_TRAIN, cd.PARTICIONES_PRODUCCION)
    assert nombre == "drift_2023-01_2023-02_2023-03__vs__2023-07_2024-01"


# =============================================================================
# 11. Integracion real con Evidently 0.7 (sin red, pero lenta)
# =============================================================================
@pytest.mark.slow
def test_evidently_genera_html_y_coincide_con_el_motor_estadistico(
    tmp_path: Path, referencia: pd.DataFrame, actual_con_drift: pd.DataFrame
) -> None:
    """Prueba de humo contra la API instalada de Evidently.

    Verifica tres cosas a la vez: que el HTML se genera, que la traduccion del
    dict produce columnas, y que los dos motores llegan al mismo veredicto de
    dataset sobre los mismos datos. Lo tercero es lo que da confianza para usar el
    plan B: si los motores discreparan, el fallback seria una falsa tranquilidad.
    """
    pytest.importorskip("evidently")
    con_evidently = cd.ejecutar_check(
        datos={"referencia": referencia, "actual": actual_con_drift},
        salida=tmp_path,
        usar_evidently=True,
        mlflow_tracking=False,
    )
    con_scipy = cd.ejecutar_check(
        datos={"referencia": referencia, "actual": actual_con_drift},
        salida=tmp_path,
        usar_evidently=False,
        mlflow_tracking=False,
    )

    assert con_evidently.degradado is False, con_evidently.motivo_degradacion
    assert con_evidently.ruta_html is not None and con_evidently.ruta_html.exists()
    assert con_evidently.ruta_html.stat().st_size > 10_000
    assert con_evidently.drift.motor == "evidently"
    assert len(con_evidently.drift.columnas) == len(con_scipy.drift.columnas)
    assert con_evidently.drift.hay_drift == con_scipy.drift.hay_drift is True
    assert con_evidently.codigo_salida == con_scipy.codigo_salida == cd.EXIT_DRIFT
