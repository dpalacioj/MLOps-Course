"""Metricas y logica de decision del gate de promocion.

Problema que resuelve
---------------------
Un numero agregado —"RMSE 4.8"— no alcanza para decidir si un modelo puede
reemplazar al que esta sirviendo trafico. Dos fallas se esconden detras del
promedio:

1. **Regresion silenciosa**: el RMSE global baja porque el modelo mejora en el
   segmento mayoritario (viajes cortos en hora valle) mientras se degrada en un
   segmento minoritario (viajes al aeropuerto de madrugada). El promedio dice
   "mejor", el usuario del segmento afectado dice "peor".
2. **Inequidad**: el mismo mecanismo, cuando el segmento afectado corresponde a
   un grupo de personas y no a un rango de kilometros, es un problema de
   equidad. La tecnica de deteccion es identica; lo que cambia es la
   consecuencia.

Por eso este modulo calcula metricas **globales y por subgrupo**, y expone la
decision del gate como funciones puras que reciben metricas y devuelven un
veredicto. Las funciones puras son las que se testean: no hace falta levantar
MLflow para verificar que "el champion es mejor" implica "no promover".

`scripts/promote.py` es solo la capa de presentacion (tabla, exit code, flags)
sobre lo que hay aqui.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

from taxi.config import MEJORA_MINIMA_RELATIVA
from taxi.features import contract as fc

logger = logging.getLogger(__name__)


# =============================================================================
# Definicion de subgrupos
# =============================================================================
# Los cortes son de negocio, no estadisticos: responden a "en que situaciones
# distintas se usa este modelo". Definirlos aqui, en un solo lugar, evita que
# el entrenamiento y el gate midan subgrupos diferentes y las cifras no se
# puedan comparar (ese desacuerdo era endemico en el repo anterior).

#: Franjas horarias por hora de pickup. Limites inclusivos en ambos extremos.
FRANJAS_HORARIAS: Final[dict[str, tuple[int, int]]] = {
    "madrugada": (0, 5),
    "manana": (6, 11),
    "tarde": (12, 17),
    "noche": (18, 23),
}

#: Rangos de distancia en MILLAS (la unidad del dataset de la TLC).
#: El limite superior es exclusivo, salvo el ultimo, que es abierto.
RANGOS_DISTANCIA: Final[tuple[tuple[str, float, float], ...]] = (
    ("corta", 0.0, 1.0),
    ("media", 1.0, 3.0),
    ("larga", 3.0, 10.0),
    ("muy_larga", 10.0, float("inf")),
)

#: Un subgrupo con pocas filas produce un RMSE dominado por el ruido de
#: muestreo. Compararlo entre dos modelos genera falsos positivos de
#: degradacion y entrena al equipo a ignorar el gate. Por debajo de este
#: tamano el subgrupo se reporta pero no se usa para decidir.
MIN_FILAS_SUBGRUPO: Final[int] = 50

#: Degradacion relativa maxima tolerada en un subgrupo. Es mas laxo que la
#: mejora global exigida porque un subgrupo tiene menos datos y por lo tanto
#: mas varianza: pedir lo mismo bloquearia promociones legitimas.
UMBRAL_DEGRADACION_SUBGRUPO: Final[float] = 0.05


# =============================================================================
# Metricas
# =============================================================================
def metricas_regresion(
    y_true: Sequence[float] | np.ndarray | pd.Series,
    y_pred: Sequence[float] | np.ndarray | pd.Series,
    *,
    prefijo: str = "",
) -> dict[str, float]:
    """Calcula rmse, mae y r2.

    Se usa ``root_mean_squared_error`` y no el viejo truco de pedirle a
    ``mean_squared_error`` la raiz con su parametro ``squared``: ese parametro fue
    eliminado de scikit-learn, asi que el codigo que lo usa ya no corre.
    Verificado contra scikit-learn 1.9.0.

    Args:
        y_true: valores observados.
        y_pred: valores predichos.
        prefijo: se antepone al nombre de cada metrica, p. ej. ``"valid_"``.
            Sirve para loguear train y valid en el mismo run sin colisiones.

    Returns:
        Diccionario ``{nombre: valor}`` listo para ``mlflow.log_metrics``.
    """
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    return {
        f"{prefijo}rmse": float(root_mean_squared_error(y_true_arr, y_pred_arr)),
        f"{prefijo}mae": float(mean_absolute_error(y_true_arr, y_pred_arr)),
        f"{prefijo}r2": float(r2_score(y_true_arr, y_pred_arr)),
    }


def franja_horaria(horas: pd.Series) -> pd.Series:
    """Mapea la hora de pickup a su franja.

    Args:
        horas: serie de enteros en 0..23 (columna ``hora_pickup``).

    Returns:
        Serie de strings con el nombre de la franja.
    """
    etiquetas = pd.Series("desconocida", index=horas.index, dtype="object")
    for nombre, (desde, hasta) in FRANJAS_HORARIAS.items():
        etiquetas[horas.between(desde, hasta)] = nombre
    return etiquetas


def rango_distancia(distancias: pd.Series) -> pd.Series:
    """Mapea la distancia en millas a su rango de negocio."""
    etiquetas = pd.Series("desconocida", index=distancias.index, dtype="object")
    for nombre, desde, hasta in RANGOS_DISTANCIA:
        etiquetas[(distancias >= desde) & (distancias < hasta)] = nombre
    return etiquetas


def metricas_por_subgrupo(
    df: pd.DataFrame,
    y_true: Sequence[float] | np.ndarray | pd.Series,
    y_pred: Sequence[float] | np.ndarray | pd.Series,
    *,
    min_filas: int = MIN_FILAS_SUBGRUPO,
) -> dict[str, float]:
    """RMSE por franja horaria y por rango de distancia.

    Los subgrupos con menos de ``min_filas`` observaciones se omiten: su RMSE es
    demasiado ruidoso para comparar dos modelos.

    Args:
        df: dataframe con las columnas ``hora_pickup`` y ``trip_distance``,
            alineado posicionalmente con ``y_true`` y ``y_pred``.
        y_true: valores observados.
        y_pred: valores predichos.
        min_filas: tamano minimo del subgrupo para reportarlo.

    Returns:
        Diccionario ``{"rmse_hora_manana": 4.7, "rmse_dist_corta": 2.1, ...}``.
        Los nombres son validos como nombres de metrica en MLflow.
    """
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    if len(y_true_arr) != len(df) or len(y_pred_arr) != len(df):
        raise ValueError(
            "df, y_true y y_pred deben tener la misma longitud: "
            f"{len(df)}, {len(y_true_arr)}, {len(y_pred_arr)}"
        )

    ejes: dict[str, pd.Series] = {
        "hora": franja_horaria(df[fc.COL_HORA].reset_index(drop=True)),
        "dist": rango_distancia(df[fc.CRUDAS_NUMERICAS[0]].reset_index(drop=True)),
    }

    salida: dict[str, float] = {}
    for eje, etiquetas in ejes.items():
        valores = etiquetas.to_numpy()
        for nombre in pd.unique(valores):
            mascara = valores == nombre
            n = int(mascara.sum())
            if n < min_filas:
                logger.debug("subgrupo %s_%s omitido: %d filas < %d", eje, nombre, n, min_filas)
                continue
            salida[f"rmse_{eje}_{nombre}"] = float(
                root_mean_squared_error(y_true_arr[mascara], y_pred_arr[mascara])
            )
            salida[f"n_{eje}_{nombre}"] = float(n)
    return salida


def evaluar_modelo(
    modelo: Any,
    df: pd.DataFrame,
    *,
    prefijo: str = "",
) -> tuple[dict[str, float], dict[str, float]]:
    """Evalua un modelo (pipeline o pyfunc) sobre un dataframe procesado.

    Acepta cualquier objeto con ``predict`` que consuma la lista de
    diccionarios de ``taxi.features.contract.a_diccionarios``. Eso incluye el
    ``Pipeline`` de sklearn recien entrenado y el modelo pyfunc cargado del
    registry, de modo que el gate mide champion y candidato con exactamente el
    mismo codigo.

    Returns:
        Tupla ``(metricas_globales, metricas_por_subgrupo)``.
    """
    entradas = fc.a_diccionarios(df)
    y_true = df[fc.TARGET_REGRESION].to_numpy(dtype=float)
    y_pred = np.asarray(modelo.predict(entradas), dtype=float).reshape(-1)
    return (
        metricas_regresion(y_true, y_pred, prefijo=prefijo),
        metricas_por_subgrupo(df, y_true, y_pred),
    )


# =============================================================================
# Gate de promocion — decision como funcion pura
# =============================================================================
@dataclass(frozen=True)
class ResultadoCriterio:
    """Veredicto de un criterio individual del gate.

    ``evaluado=False`` significa que el gate corto antes de llegar a este
    criterio. Se distingue de ``aprobado=False`` a proposito: "no lo revise" y
    "lo revise y fallo" son diagnosticos distintos para quien lee el log del CI.
    """

    nombre: str
    aprobado: bool
    detalle: str
    evaluado: bool = True

    @property
    def estado(self) -> str:
        if not self.evaluado:
            return "NO EVALUADO"
        return "PASA" if self.aprobado else "FALLA"


@dataclass(frozen=True)
class DecisionGate:
    """Resultado completo del gate.

    Es un objeto y no un booleano porque el "por que" es la parte util: si el
    gate rechaza y no explica cual criterio fallo con que numeros, el equipo
    aprende a saltarselo.
    """

    promover: bool
    es_primer_modelo: bool
    criterios: tuple[ResultadoCriterio, ...] = field(default_factory=tuple)

    @property
    def motivo(self) -> str:
        """Frase corta apta para el log del CI o para un tag."""
        if self.promover:
            if self.es_primer_modelo:
                return "primer modelo: no hay champion con el que comparar"
            return "todos los criterios pasan"
        fallidos = [c.nombre for c in self.criterios if c.evaluado and not c.aprobado]
        return "criterios no superados: " + ", ".join(fallidos) if fallidos else "rechazado"

    @property
    def estado_validacion(self) -> str:
        """Valor para el tag ``validation_status`` del model registry."""
        return "passed" if self.promover else "failed"


def criterio_contrato_datos(df: pd.DataFrame) -> ResultadoCriterio:
    """Criterio 1: el holdout cumple el contrato de datos.

    Se valida el dato **antes** de mirar cualquier metrica. Un RMSE calculado
    sobre datos que violan el contrato no significa nada, y promover en base a
    el es peor que no promover: el gate habria dado una garantia falsa.

    La validacion se hace con los mismos contratos de Pandera que usa la
    ingesta, no con una copia: si el contrato cambia, el gate cambia con el.
    """
    # Import local: `taxi.data.contract` importa pandera, que tarda ~1 s en
    # cargar. Los tests de las demas funciones de este modulo no lo necesitan.
    from taxi.data import contract as dc

    try:
        dc.validar_procesados(df)
    except Exception as exc:
        primera_linea = str(exc).strip().splitlines()[0][:200]
        return ResultadoCriterio(
            nombre="contrato_de_datos",
            aprobado=False,
            detalle=f"el holdout viola el contrato ({type(exc).__name__}): {primera_linea}",
        )
    return ResultadoCriterio(
        nombre="contrato_de_datos",
        aprobado=True,
        detalle=f"{len(df)} filas del holdout cumplen ViajesProcesados",
    )


def criterio_mejora_global(
    rmse_candidato: float,
    rmse_champion: float | None,
    *,
    mejora_minima: float = MEJORA_MINIMA_RELATIVA,
) -> ResultadoCriterio:
    """Criterio 2: el candidato mejora al champion en el holdout fijo.

    La condicion es ``rmse_candidato <= rmse_champion * (1 - mejora_minima)``.
    Exigir un margen y no un simple "menor que" evita el churn de modelos:
    con ruido de muestreo, dos modelos equivalentes se alternan indefinidamente
    en produccion, y cada rotacion cuesta un despliegue y rompe la
    comparabilidad de las metricas de negocio.

    Args:
        rmse_candidato: RMSE del candidato en el holdout.
        rmse_champion: RMSE del champion en el mismo holdout, o ``None`` si
            todavia no hay champion.
        mejora_minima: margen relativo exigido (0.01 = 1%).
    """
    if rmse_champion is None:
        return ResultadoCriterio(
            nombre="mejora_global",
            aprobado=True,
            detalle=(
                f"no hay champion: este es el PRIMER modelo del registry. "
                f"rmse_candidato={rmse_candidato:.4f} queda como linea base."
            ),
        )

    objetivo = rmse_champion * (1.0 - mejora_minima)
    aprobado = rmse_candidato <= objetivo
    # Convencion de signo unica en todo el gate: el delta es del candidato
    # respecto al champion, y como la metrica es un error, NEGATIVO es mejor.
    # Mezclar las dos convenciones entre criterios es una fuente segura de
    # malentendidos a las 3 de la manana durante un incidente.
    delta_rel = (rmse_candidato - rmse_champion) / rmse_champion if rmse_champion else 0.0
    return ResultadoCriterio(
        nombre="mejora_global",
        aprobado=aprobado,
        detalle=(
            f"rmse candidato={rmse_candidato:.4f} vs champion={rmse_champion:.4f} "
            f"({delta_rel:+.2%}); objetivo <= {objetivo:.4f} "
            f"(mejora minima {mejora_minima:.1%})"
        ),
    )


def criterio_subgrupos(
    subgrupos_candidato: Mapping[str, float],
    subgrupos_champion: Mapping[str, float] | None,
    *,
    umbral: float = UMBRAL_DEGRADACION_SUBGRUPO,
) -> ResultadoCriterio:
    """Criterio 3: ningun subgrupo se degrada mas de ``umbral``.

    Aqui se atrapan las regresiones silenciosas y los problemas de equidad que
    el promedio global esconde. Solo se comparan los subgrupos presentes en
    ambos modelos: uno que aparece solo en el candidato no tiene con que
    compararse.

    Args:
        subgrupos_candidato: salida de ``metricas_por_subgrupo`` del candidato.
        subgrupos_champion: la misma estructura para el champion, o ``None``.
        umbral: degradacion relativa maxima tolerada (0.05 = 5%).
    """
    if subgrupos_champion is None:
        return ResultadoCriterio(
            nombre="sin_regresion_por_subgrupo",
            aprobado=True,
            detalle="no hay champion: no hay linea base por subgrupo",
        )

    comunes = sorted(
        k
        for k in subgrupos_candidato
        if k.startswith("rmse_") and k in subgrupos_champion and subgrupos_champion[k]
    )
    if not comunes:
        return ResultadoCriterio(
            nombre="sin_regresion_por_subgrupo",
            aprobado=False,
            detalle=(
                "no hay subgrupos comparables entre candidato y champion. "
                "No se puede afirmar que no hubo regresion, y el gate no "
                "aprueba lo que no puede verificar."
            ),
        )

    degradados: list[str] = []
    peor_nombre = ""
    peor_delta = float("-inf")
    for clave in comunes:
        base = subgrupos_champion[clave]
        nuevo = subgrupos_candidato[clave]
        delta = (nuevo - base) / base  # >0 = el candidato empeora
        if delta > peor_delta:
            peor_delta, peor_nombre = delta, clave
        if delta > umbral:
            degradados.append(f"{clave} {base:.4f}->{nuevo:.4f} ({delta:+.2%})")

    if degradados:
        return ResultadoCriterio(
            nombre="sin_regresion_por_subgrupo",
            aprobado=False,
            detalle=(
                f"{len(degradados)} de {len(comunes)} subgrupos se degradan mas de "
                f"{umbral:.1%}: " + "; ".join(degradados)
            ),
        )
    return ResultadoCriterio(
        nombre="sin_regresion_por_subgrupo",
        aprobado=True,
        detalle=(
            f"{len(comunes)} subgrupos comparados, ninguno se degrada mas de "
            f"{umbral:.1%}; el peor es {peor_nombre} ({peor_delta:+.2%})"
        ),
    )


def decidir_promocion(
    holdout: pd.DataFrame,
    metricas_candidato: Mapping[str, float],
    subgrupos_candidato: Mapping[str, float],
    metricas_champion: Mapping[str, float] | None = None,
    subgrupos_champion: Mapping[str, float] | None = None,
    *,
    mejora_minima: float = MEJORA_MINIMA_RELATIVA,
    umbral_subgrupo: float = UMBRAL_DEGRADACION_SUBGRUPO,
) -> DecisionGate:
    """Aplica los tres criterios en orden y devuelve el veredicto.

    El orden no es decorativo: es de mas fundamental a mas fino. Si el dato
    esta mal, las metricas no se miran (corto circuito), porque reportar una
    comparacion de RMSE sobre datos invalidos invita a discutir el numero
    equivocado.

    Funcion pura: no toca MLflow, no escribe tags, no mueve aliases. Eso vive
    en ``scripts/promote.py``. Separarlo es lo que permite testear la politica
    de promocion sin infraestructura.

    Args:
        holdout: dataframe del holdout fijo (``PARTICION_TEST``), ya procesado.
        metricas_candidato: metricas globales del candidato en el holdout.
        subgrupos_candidato: metricas por subgrupo del candidato.
        metricas_champion: idem para el champion; ``None`` si no existe.
        subgrupos_champion: idem para el champion; ``None`` si no existe.
        mejora_minima: margen relativo exigido en el RMSE global.
        umbral_subgrupo: degradacion relativa maxima tolerada por subgrupo.
    """
    es_primero = metricas_champion is None
    criterios: list[ResultadoCriterio] = [criterio_contrato_datos(holdout)]

    if not criterios[0].aprobado:
        criterios.append(
            ResultadoCriterio(
                nombre="mejora_global",
                aprobado=False,
                detalle="no evaluado: el contrato de datos fallo",
                evaluado=False,
            )
        )
        criterios.append(
            ResultadoCriterio(
                nombre="sin_regresion_por_subgrupo",
                aprobado=False,
                detalle="no evaluado: el contrato de datos fallo",
                evaluado=False,
            )
        )
    else:
        criterios.append(
            criterio_mejora_global(
                rmse_candidato=float(metricas_candidato["rmse"]),
                rmse_champion=None if es_primero else float(metricas_champion["rmse"]),  # type: ignore[index]
                mejora_minima=mejora_minima,
            )
        )
        criterios.append(
            criterio_subgrupos(
                subgrupos_candidato,
                None if es_primero else subgrupos_champion,
                umbral=umbral_subgrupo,
            )
        )

    for criterio in criterios:
        logger.info("[gate] %-28s %-11s %s", criterio.nombre, criterio.estado, criterio.detalle)

    promover = all(c.aprobado for c in criterios)
    return DecisionGate(
        promover=promover,
        es_primer_modelo=es_primero and promover,
        criterios=tuple(criterios),
    )
