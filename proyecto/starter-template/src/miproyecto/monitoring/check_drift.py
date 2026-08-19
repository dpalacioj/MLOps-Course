"""Deteccion de drift como check ejecutable, no como PDF que nadie abre.

Que se puede medir y que no
---------------------------
=========================  ==================================================
Fenomeno                   Observable sin labels?
=========================  ==================================================
data drift                 Si. Cambia P(X)
prediction drift           Si. Cambia P(y_hat)
concept drift              No directamente. Cambia P(y|X)
degradacion de performance Solo cuando llegan los labels (*label lag*)
=========================  ==================================================

Por eso el monitoreo de un sistema de ML no es "medir accuracy en produccion":
la mayor parte del tiempo NO tienes el label. Lo que si tienes es la
distribucion de entrada y la de salida.

La trampa de los p-valores
--------------------------
Con n grande, TODO sale significativo. Con 500 000 filas, un cambio de la media
en un 0.1% da p < 1e-10 y no le importa a nadie. Por eso este modulo reporta
p-valor **y** tamano del efecto, y la decision usa la **fraccion de columnas con
drift** contra un umbral que el estudiante justifica, no un `p < 0.05` suelto.

Por que scipy y no solo Evidently
---------------------------------
La politica se implementa con ``scipy.stats`` en funciones puras: se testea sin
red, sin HTML y sin depender de la API de una libreria que cambia. Evidently se
usa para el **reporte** (que es donde aporta: presets, HTML navegable,
comparacion visual). Separar politica de presentacion es lo que permite que el
check corra en CI en dos segundos.

Uso:

    python -m miproyecto.monitoring.check_drift        # exit 1 si hay drift

TODO(estudiante) 19: elige y justifica tu umbral en
docs/politica-de-reentrenamiento.md. "0.30 porque venia en el template" no es
una justificacion.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from miproyecto.config import (
    ALFA_DRIFT,
    REPORTS_DIR,
    UMBRAL_DRIFT_COLUMNAS,
)
from miproyecto.features import contract as fc

logger = logging.getLogger(__name__)

EXITO_SIN_DRIFT = 0
EXITO_CON_DRIFT = 1
ERROR_INFRA = 2

#: Tamano de efecto minimo para considerar el drift accionable, medido como
#: estadistico KS (distancia maxima entre las dos acumuladas, 0 a 1). Un KS de
#: 0.05 es un cambio que casi nunca justifica reentrenar; uno de 0.30 si.
EFECTO_MINIMO_KS: float = 0.10


@dataclass
class ResultadoColumna:
    """Drift de una columna: el test, el p-valor y el tamano del efecto."""

    columna: str
    test: str
    p_valor: float
    efecto: float
    hay_drift: bool


@dataclass
class ResultadoDrift:
    """Veredicto global, con el detalle por columna para poder auditarlo."""

    columnas: list[ResultadoColumna] = field(default_factory=list)
    umbral: float = UMBRAL_DRIFT_COLUMNAS

    @property
    def fraccion_con_drift(self) -> float:
        if not self.columnas:
            return 0.0
        return sum(c.hay_drift for c in self.columnas) / len(self.columnas)

    @property
    def hay_drift(self) -> bool:
        return self.fraccion_con_drift > self.umbral

    @property
    def columnas_con_drift(self) -> list[str]:
        return [c.columna for c in self.columnas if c.hay_drift]

    def a_markdown(self) -> str:
        """Tabla para pegar en el PR o en un artifact del orquestador."""
        lineas = [
            "| columna | test | p-valor | efecto | drift |",
            "|---|---|---:|---:|---|",
        ]
        for c in sorted(self.columnas, key=lambda x: -x.efecto):
            lineas.append(
                f"| {c.columna} | {c.test} | {c.p_valor:.2e} | {c.efecto:.3f} | "
                f"{'SI' if c.hay_drift else 'no'} |"
            )
        lineas.append("")
        lineas.append(
            f"**{self.fraccion_con_drift:.0%}** de las columnas con drift "
            f"(umbral: {self.umbral:.0%}) -> "
            f"{'ACCIONAR' if self.hay_drift else 'sin accion'}"
        )
        return "\n".join(lineas)


def drift_numerico(
    referencia: pd.Series, produccion: pd.Series, *, alfa: float = ALFA_DRIFT
) -> ResultadoColumna:
    """Kolmogorov-Smirnov de dos muestras sobre una columna numerica.

    KS mide la distancia maxima entre las dos funciones de distribucion
    acumuladas. El estadistico ES el tamano del efecto (0 = identicas,
    1 = disjuntas), lo que lo hace comodo: no hay que calcular el efecto aparte.
    """
    a = pd.to_numeric(referencia, errors="coerce").dropna().to_numpy()
    b = pd.to_numeric(produccion, errors="coerce").dropna().to_numpy()
    if len(a) < 2 or len(b) < 2:
        return ResultadoColumna(str(referencia.name), "ks", 1.0, 0.0, False)
    resultado = stats.ks_2samp(a, b)
    efecto = float(resultado.statistic)
    return ResultadoColumna(
        columna=str(referencia.name),
        test="ks",
        p_valor=float(resultado.pvalue),
        efecto=efecto,
        # Las DOS condiciones: significativo Y con efecto que importa.
        hay_drift=bool(resultado.pvalue < alfa and efecto >= EFECTO_MINIMO_KS),
    )


def drift_categorico(
    referencia: pd.Series, produccion: pd.Series, *, alfa: float = ALFA_DRIFT
) -> ResultadoColumna:
    """Chi-cuadrado sobre la tabla de frecuencias, con V de Cramer como efecto.

    Las categorias que aparecen en una sola de las dos muestras se conservan con
    frecuencia 0: una categoria NUEVA en produccion es justo el tipo de cambio
    que hay que detectar, y descartarla lo esconderia.
    """
    nombre = str(referencia.name)
    ref = referencia.astype(str).value_counts()
    pro = produccion.astype(str).value_counts()
    categorias = sorted(set(ref.index) | set(pro.index))
    tabla = np.array(
        [[ref.get(c, 0) for c in categorias], [pro.get(c, 0) for c in categorias]],
        dtype=float,
    )
    # Se descartan las columnas todo-cero (imposibles) para que chi2 no divida
    # por cero.
    tabla = tabla[:, tabla.sum(axis=0) > 0]
    if tabla.shape[1] < 2 or tabla.sum() == 0:
        return ResultadoColumna(nombre, "chi2", 1.0, 0.0, False)

    chi2, p, _, _ = stats.chi2_contingency(tabla)
    n = tabla.sum()
    # V de Cramer: normaliza chi2 a [0, 1] y NO crece con n, que es exactamente
    # lo que le falta al p-valor.
    v_cramer = float(np.sqrt(chi2 / (n * (min(tabla.shape) - 1))))
    return ResultadoColumna(
        columna=nombre,
        test="chi2",
        p_valor=float(p),
        efecto=v_cramer,
        hay_drift=bool(p < alfa and v_cramer >= EFECTO_MINIMO_KS),
    )


def evaluar_drift(
    referencia: pd.DataFrame,
    produccion: pd.DataFrame,
    *,
    numericas: list[str] | None = None,
    categoricas: list[str] | None = None,
    umbral: float = UMBRAL_DRIFT_COLUMNAS,
    alfa: float = ALFA_DRIFT,
) -> ResultadoDrift:
    """Compara referencia vs produccion columna por columna. Funcion pura."""
    numericas = numericas if numericas is not None else fc.FEATURES_NUMERICAS
    categoricas = categoricas if categoricas is not None else fc.FEATURES_CATEGORICAS

    resultado = ResultadoDrift(umbral=umbral)
    for col in numericas:
        if col in referencia.columns and col in produccion.columns:
            resultado.columnas.append(drift_numerico(referencia[col], produccion[col], alfa=alfa))
    for col in categoricas:
        if col in referencia.columns and col in produccion.columns:
            resultado.columnas.append(drift_categorico(referencia[col], produccion[col], alfa=alfa))
    return resultado


def reporte_html(
    referencia: pd.DataFrame,
    produccion: pd.DataFrame,
    *,
    nombre: str = "drift-report.html",
) -> str:
    """Genera el reporte navegable con Evidently 0.7.x y devuelve su ruta.

    Se aisla aqui, fuera de la politica, para que la API de una libreria de
    presentacion no pueda romper el check de CI.

    Ojo con el orden de los argumentos: ``report.run(current, reference)``.
    Invertirlos no lanza error, solo produce un reporte que dice lo contrario de
    lo que crees.
    """
    from evidently import DataDefinition, Dataset, Report
    from evidently.presets import DataDriftPreset, DataSummaryPreset

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    destino = REPORTS_DIR / nombre

    esquema = DataDefinition(
        numerical_columns=[c for c in fc.FEATURES_NUMERICAS if c in referencia.columns],
        categorical_columns=[c for c in fc.FEATURES_CATEGORICAS if c in referencia.columns],
    )
    ref = Dataset.from_pandas(referencia, data_definition=esquema)
    cur = Dataset.from_pandas(produccion, data_definition=esquema)

    reporte = Report([DataDriftPreset(), DataSummaryPreset()])
    evaluacion = reporte.run(cur, ref)
    evaluacion.save_html(str(destino))
    logger.info("reporte de drift en %s", destino)
    return str(destino)


def main() -> int:
    """Check de CI: exit 1 si el drift supera el umbral.

    TODO(estudiante) 20: carga tus particiones de referencia y de produccion
    (config.PARTICIONES_TRAIN vs config.PARTICIONES_PRODUCCION), llama a
    ``evaluar_drift``, genera el HTML con ``reporte_html`` y sube ambos como
    artifact del CI. El reporte es la evidencia; el exit code es el check.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger.error("El check de drift todavia no esta conectado a tus datos (TODO 20).")
    return ERROR_INFRA


if __name__ == "__main__":
    sys.exit(main())
