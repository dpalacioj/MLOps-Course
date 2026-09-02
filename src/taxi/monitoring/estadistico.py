"""Deteccion de drift con scipy puro: tests, tamanos de efecto y veredicto.

Problema que resuelve
---------------------
Dos problemas, uno tecnico y uno pedagogico.

**El tecnico.** La forma corta de "resolver" el drift, y la que aparece en casi
cualquier tutorial, es una linea:

    drift = "DRIFT DETECTADO" if p_value < 0.05 else "Sin drift"

Ese criterio es **incorrecto a la escala de un sistema real**. El p-valor de un
test de dos muestras responde "es plausible que estas dos muestras vengan de la
misma distribucion?", y la respuesta depende del tamano de muestra tanto como de
la magnitud del cambio. Con n grande, un cambio irrelevante para el negocio
—la media de `trip_distance` pasa de 3.00 a 3.02 millas— produce p-valores de
1e-12. Un pipeline que alerta con ese criterio alerta **todos los dias**, el
equipo aprende a ignorar la alerta, y el dia que el drift es real nadie mira.
Es alert fatigue provocada por un error estadistico.

La correccion no es subir el alfa: es **separar significancia de magnitud**. Un
test dice si el cambio es distinguible del ruido; un **tamano de efecto** dice si
es lo bastante grande para importar. El veredicto de este modulo exige las dos
cosas, y cuando discrepan lo dice explicitamente en el campo ``motivo``.

**El pedagogico.** Llamar a un preset de una libreria ensena a usar la libreria,
no a entender el problema. Aqui el KS, el chi-cuadrado, el PSI y la divergencia
de Jensen-Shannon se calculan a la vista, con las decisiones de binning y de
suavizado explicitas, que es donde estan los errores reales.

Y hay una razon de ingenieria para que este modulo exista: es el **plan B**. El
check de drift del curso (``taxi.monitoring.check_drift``) prefiere Evidently
por sus reportes, pero degrada a este modulo si la libreria no esta disponible.
Evidently 0.7.21 —la version del curso— se publico en marzo de 2026 y la cadencia
previa era mensual; un pipeline critico no deberia quedar sin senal de drift
porque una dependencia opcional se detuvo. Lo que se pierde al degradar es el
HTML, no la deteccion.

Que NO hace este modulo
-----------------------
No detecta concept drift. Ningun test sobre las features lo puede detectar: el
concept drift es un cambio en P(y|X) y para verlo hacen falta etiquetas. Ver
``sesiones/s07-monitoreo/README.md``.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import jensenshannon

logger = logging.getLogger(__name__)

# =============================================================================
# Umbrales. Explicitos, con nombre y con justificacion.
# =============================================================================
#: Nivel de significancia de los tests. Se conserva porque un p-valor alto SI es
#: informativo ("ni siquiera es distinguible del ruido"), pero nunca decide solo.
ALFA: Final[float] = 0.05

#: Tamano de efecto minimo para declarar drift en una columna numerica. El
#: estadistico del KS es la distancia sup entre las dos CDF empiricas: 0.10
#: significa "las distribuciones acumuladas se separan como maximo 10 puntos
#: porcentuales". Por debajo de eso, el cambio es difumino de muestreo para este
#: caso de uso.
UMBRAL_KS: Final[float] = 0.10

#: Tamano de efecto minimo para columnas categoricas, medido con la V de Cramer
#: (chi-cuadrado normalizado a [0, 1], independiente de n). 0.10 es la frontera
#: convencional de "asociacion debil".
UMBRAL_CRAMER: Final[float] = 0.10

#: Cortes clasicos del PSI en credit scoring, de donde viene la metrica:
#: < 0.10 estable, 0.10-0.25 cambio moderado (vigilar), > 0.25 cambio
#: significativo (actuar). No son leyes: son un punto de partida que hay que
#: recalibrar contra el historico propio.
PSI_MODERADO: Final[float] = 0.10
PSI_ALTO: Final[float] = 0.25

#: Numero de bins para PSI y Jensen-Shannon en columnas numericas. Los bordes se
#: toman por cuantiles de la REFERENCIA, no del conjunto actual: si los bordes
#: cambian con los datos nuevos, el PSI de dos periodos no es comparable y la
#: serie temporal de la metrica deja de significar nada.
BINS: Final[int] = 10

#: Suavizado. Un bin vacio en cualquiera de los dos lados vuelve el PSI infinito
#: (log de 0) y contamina el total. Se sustituye por este epsilon, que es la
#: practica estandar; la alternativa honesta es reportar el bin como vacio y no
#: agregar. Se documenta porque es una decision, no un detalle.
EPSILON: Final[float] = 1e-6

#: Frecuencia esperada minima por celda para que el chi-cuadrado sea valido. Las
#: categorias que no la alcanzan se agrupan en ``OTRAS``.
MIN_FRECUENCIA_ESPERADA: Final[int] = 5

#: Etiqueta de la categoria agregada. Empieza con "_" para no colisionar con un
#: valor real de PU_DO ni de las zonas.
OTRAS: Final[str] = "_otras"

#: Muestra maxima por columna. El KS es O(n log n) y con las particiones del
#: curso completas (varios cientos de miles de filas) el notebook se vuelve
#: incomodo sin que la conclusion cambie. Ademas hace explicito el punto del
#: modulo: si hay que submuestrear para que el p-valor sea interpretable, el
#: p-valor no era el criterio.
MAX_FILAS: Final[int] = 200_000

#: Semilla del submuestreo. Un check de drift que da un resultado distinto en
#: cada corrida no es auditable.
SEMILLA: Final[int] = 42

#: Umbrales por feature del caso guia. El umbral es una decision de negocio, no
#: una constante universal: `trip_distance` alimenta directamente la prediccion
#: de duracion, asi que se vigila mas fino que la hora del dia, cuyo cambio
#: estacional es esperado y el modelo ya lo tiene como feature.
#:
#: Ademas de la decision de negocio, cada umbral esta **calibrado contra la linea
#: base nula**: el efecto que se mide entre dos mitades aleatorias de la propia
#: referencia, donde por construccion NO hay drift (ver `linea_base_nula`). Un
#: umbral por debajo de esa linea base garantiza falsos positivos.
#:
#: Medicion sobre las particiones del curso (2023-01..03, 60k filas por mes,
#: agosto de 2026):
#:
#:     trip_distance      0.006   |  hora_pickup        0.005
#:     dia_semana_pickup  0.003   |  duration           0.005
#:     PULocationID       0.034   |  DOLocationID       0.036
#:     PU_DO              0.122   <-- alto: la V de Cramer tiene sesgo positivo
#:                                    con muchas celdas y conteos bajos
#:
#: De ahi el 0.15 de `PU_DO`: con un umbral de 0.10 el par origen-destino habria
#: quedado por debajo de su propio ruido y el detector habria alertado sobre dos
#: mitades del mismo mes. Ver docs/adr/003-umbrales-de-drift.md.
UMBRALES_POR_FEATURE: Final[Mapping[str, float]] = {
    "trip_distance": 0.07,
    "hora_pickup": 0.15,
    "dia_semana_pickup": 0.15,
    "PU_DO": 0.15,
    "PULocationID": 0.10,
    "DOLocationID": 0.10,
}

Criterio = Literal["efecto", "p_valor", "psi"]

#: Criterios de veredicto disponibles. "p_valor" existe **para demostrar en
#: clase que esta mal**: se corre el mismo dataset con los tres y se comparan las
#: fracciones de columnas con drift.
CRITERIOS: Final[tuple[str, ...]] = ("efecto", "p_valor", "psi")

TIPO_NUMERICA: Final[str] = "numerica"
TIPO_CATEGORICA: Final[str] = "categorica"


# =============================================================================
# Estructura del resultado
# =============================================================================
@dataclass(frozen=True)
class ResultadoColumna:
    """Veredicto de drift para una columna.

    Es la estructura interna del modulo de monitoreo y la comparten los dos
    motores: la calcula ``estadistico.detectar_drift`` y la reconstruye
    ``reporte.desde_evidently`` a partir del ``dict()`` de Evidently. Los campos
    opcionales son precisamente los que un motor puede no reportar (Evidently
    con metodos de distancia no devuelve p-valor).
    """

    columna: str
    tipo: str
    metodo: str
    drift: bool
    motivo: str
    estadistico: float | None = None
    p_valor: float | None = None
    tamano_efecto: float | None = None
    nombre_efecto: str = ""
    umbral_efecto: float | None = None
    psi: float | None = None
    jensen_shannon: float | None = None
    n_referencia: int | None = None
    n_actual: int | None = None
    categorias_nuevas: int = 0
    aviso: str = ""

    def a_dict(self) -> dict[str, Any]:
        """Forma serializable a JSON. Sin numpy: `json` no sabe serializarlo."""
        return {
            "columna": self.columna,
            "tipo": self.tipo,
            "metodo": self.metodo,
            "drift": bool(self.drift),
            "motivo": self.motivo,
            "estadistico": _float_o_none(self.estadistico),
            "p_valor": _float_o_none(self.p_valor),
            "tamano_efecto": _float_o_none(self.tamano_efecto),
            "nombre_efecto": self.nombre_efecto,
            "umbral_efecto": _float_o_none(self.umbral_efecto),
            "psi": _float_o_none(self.psi),
            "jensen_shannon": _float_o_none(self.jensen_shannon),
            "n_referencia": self.n_referencia,
            "n_actual": self.n_actual,
            "categorias_nuevas": self.categorias_nuevas,
            "aviso": self.aviso,
        }


@dataclass(frozen=True)
class ResultadoDrift:
    """Veredicto agregado: por columna y a nivel de dataset."""

    motor: str
    criterio: str
    columnas: tuple[ResultadoColumna, ...]
    umbral_columnas: float
    avisos: tuple[str, ...] = field(default_factory=tuple)

    @property
    def con_drift(self) -> tuple[ResultadoColumna, ...]:
        return tuple(c for c in self.columnas if c.drift)

    @property
    def fraccion_con_drift(self) -> float:
        """Fraccion de columnas con drift.

        Se agrega asi —y no con "alguna columna cambio"— porque una sola columna
        con drift es ruido normal en cualquier sistema real, mientras que un
        tercio de las columnas moviendose a la vez casi siempre indica un cambio
        upstream (un cambio de esquema, un sensor, una tarifa nueva).
        """
        if not self.columnas:
            return 0.0
        return len(self.con_drift) / len(self.columnas)

    @property
    def hay_drift(self) -> bool:
        """True si la fraccion supera el umbral. Es la condicion que falla el CI."""
        return self.fraccion_con_drift > self.umbral_columnas

    def a_dict(self) -> dict[str, Any]:
        """Forma serializable a JSON, consumible por el CI."""
        return {
            "motor": self.motor,
            "criterio": self.criterio,
            "umbral_columnas": self.umbral_columnas,
            "columnas_totales": len(self.columnas),
            "columnas_con_drift": len(self.con_drift),
            "fraccion_con_drift": round(self.fraccion_con_drift, 6),
            "hay_drift": self.hay_drift,
            "avisos": list(self.avisos),
            "detalle": [c.a_dict() for c in self.columnas],
        }


def _float_o_none(valor: float | None) -> float | None:
    """Convierte a float nativo y neutraliza NaN/inf, que no son JSON validos."""
    if valor is None:
        return None
    numero = float(valor)
    return None if not math.isfinite(numero) else numero


# =============================================================================
# Metricas de distancia entre distribuciones
# =============================================================================
def bordes_por_cuantiles(referencia: Sequence[float] | pd.Series, bins: int = BINS) -> np.ndarray:
    """Bordes de bin por cuantiles de la referencia, con extremos abiertos.

    Por que cuantiles y no ancho fijo: con una distribucion sesgada como
    `trip_distance` (exponencial), el ancho fijo deja el 95% de los datos en el
    primer bin y el PSI pierde toda resolucion donde estan los datos.

    Los extremos se abren a +/-inf para que los valores fuera del rango de la
    referencia caigan en el primer o ultimo bin en lugar de desaparecer. Un valor
    nuevo mas alto que cualquiera visto en entrenamiento es exactamente la senal
    que se quiere capturar, no descartar.
    """
    serie = pd.Series(referencia, dtype="float64").dropna()
    if serie.empty:
        return np.array([-np.inf, np.inf])
    cuantiles = np.linspace(0.0, 1.0, bins + 1)
    bordes = np.unique(np.quantile(serie.to_numpy(), cuantiles))
    if bordes.size < 2:
        # Columna constante en la referencia: un solo bin.
        bordes = np.array([bordes[0] - 1.0, bordes[0] + 1.0])
    bordes[0] = -np.inf
    bordes[-1] = np.inf
    return bordes


def _proporciones_numericas(
    referencia: pd.Series,
    actual: pd.Series,
    bins: int = BINS,
) -> tuple[np.ndarray, np.ndarray]:
    """Proporciones por bin de las dos muestras, sobre los bordes de la referencia."""
    bordes = bordes_por_cuantiles(referencia, bins)
    cuenta_ref, _ = np.histogram(referencia.dropna().to_numpy(), bins=bordes)
    cuenta_act, _ = np.histogram(actual.dropna().to_numpy(), bins=bordes)
    return _normalizar(cuenta_ref), _normalizar(cuenta_act)


def _proporciones_categoricas(
    referencia: pd.Series,
    actual: pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    """Proporciones por categoria sobre la UNION de categorias de ambas muestras."""
    conteo_ref = referencia.astype("string").fillna("_nulo").value_counts()
    conteo_act = actual.astype("string").fillna("_nulo").value_counts()
    categorias = sorted(set(conteo_ref.index) | set(conteo_act.index))
    vector_ref = np.array([float(conteo_ref.get(c, 0)) for c in categorias])
    vector_act = np.array([float(conteo_act.get(c, 0)) for c in categorias])
    return _normalizar(vector_ref), _normalizar(vector_act)


def _normalizar(conteos: np.ndarray) -> np.ndarray:
    """Pasa conteos a proporciones, sustituyendo ceros por EPSILON."""
    total = conteos.sum()
    if total <= 0:
        return np.full(conteos.shape, EPSILON)
    proporciones = conteos.astype("float64") / float(total)
    return np.where(proporciones <= 0.0, EPSILON, proporciones)


def psi_desde_proporciones(p_ref: np.ndarray, p_act: np.ndarray) -> float:
    """PSI a partir de dos vectores de proporciones ya alineados.

    PSI = sum_i (p_act_i - p_ref_i) * ln(p_act_i / p_ref_i)

    Es simetrico y no negativo. Cada termino aporta doble senal: la diferencia de
    masa y el cociente, asi que un bin pequeno que se duplica pesa poco y un bin
    grande que se mueve poco tambien. Eso es deseable y es la razon por la que el
    PSI se usa para vigilar en el tiempo en lugar de un p-valor.
    """
    return float(np.sum((p_act - p_ref) * np.log(p_act / p_ref)))


def psi(referencia: pd.Series, actual: pd.Series, *, categorica: bool = False) -> float:
    """Population Stability Index entre dos muestras de la misma columna."""
    if categorica:
        p_ref, p_act = _proporciones_categoricas(referencia, actual)
    else:
        p_ref, p_act = _proporciones_numericas(referencia, actual)
    return psi_desde_proporciones(p_ref, p_act)


def distancia_jensen_shannon(
    referencia: pd.Series,
    actual: pd.Series,
    *,
    categorica: bool = False,
) -> float:
    """Distancia de Jensen-Shannon (base 2), acotada en [0, 1].

    Es la raiz de la divergencia de Jensen-Shannon. Se prefiere la **distancia**
    y no la divergencia por una razon practica: al estar acotada en [0, 1] es
    comparable entre columnas y entre periodos, mientras que un PSI de 0.8 no
    tiene techo con el que compararse. Evidently usa esta misma metrica por
    defecto para categoricas.
    """
    if categorica:
        p_ref, p_act = _proporciones_categoricas(referencia, actual)
    else:
        p_ref, p_act = _proporciones_numericas(referencia, actual)
    valor = float(jensenshannon(p_ref, p_act, base=2.0))
    return 0.0 if math.isnan(valor) else valor


def v_de_cramer(tabla: np.ndarray, chi2: float) -> float:
    """V de Cramer: chi-cuadrado normalizado a [0, 1].

    Por que hace falta: el estadistico chi-cuadrado crece linealmente con n, asi
    que no es comparable entre corridas de distinto tamano y no dice nada sobre
    la magnitud del cambio. La V divide por n y por los grados de libertad, y
    entonces si es un tamano de efecto.
    """
    n = float(tabla.sum())
    if n <= 0:
        return 0.0
    k = min(tabla.shape) - 1
    if k <= 0:
        return 0.0
    return float(math.sqrt((chi2 / n) / k))


# =============================================================================
# Preparacion de muestras
# =============================================================================
def _submuestrear(serie: pd.Series, maximo: int, semilla: int) -> tuple[pd.Series, bool]:
    """Submuestrea de forma determinista si la serie excede el maximo."""
    if maximo <= 0 or len(serie) <= maximo:
        return serie, False
    return serie.sample(n=maximo, random_state=semilla), True


def _agrupar_categorias_raras(
    conteo: pd.Series,
    minimo: int,
) -> pd.Series:
    """Agrupa en ``OTRAS`` las categorias con menos de ``minimo`` observaciones."""
    if conteo.empty:
        return conteo
    raras = conteo[conteo < minimo]
    if raras.empty:
        return conteo
    frecuentes = conteo[conteo >= minimo]
    frecuentes = pd.concat([frecuentes, pd.Series({OTRAS: float(raras.sum())})])
    return frecuentes


# =============================================================================
# Veredicto
# =============================================================================
def _decidir(
    *,
    criterio: str,
    p_valor: float | None,
    efecto: float | None,
    umbral_efecto: float,
    valor_psi: float | None,
    alfa: float,
) -> tuple[bool, str]:
    """Aplica el criterio elegido y devuelve ``(drift, motivo)``.

    El motivo se guarda porque es la parte que se lee en la revision: "drift" sin
    explicacion no permite decidir si hay que reentrenar o si hay que ajustar el
    umbral.
    """
    significativo = p_valor is not None and p_valor < alfa
    relevante = efecto is not None and efecto >= umbral_efecto

    if criterio == "p_valor":
        # Criterio deliberadamente malo. Se conserva para poder mostrarlo.
        return significativo, (
            f"p={_fmt(p_valor)} < alfa={alfa} (criterio solo-p-valor: "
            "sensible al tamano de muestra)"
            if significativo
            else f"p={_fmt(p_valor)} >= alfa={alfa}"
        )

    if criterio == "psi":
        alto = valor_psi is not None and valor_psi >= PSI_ALTO
        if alto:
            return True, f"PSI={_fmt(valor_psi)} >= {PSI_ALTO} (cambio significativo)"
        moderado = valor_psi is not None and valor_psi >= PSI_MODERADO
        nivel = "moderado, vigilar" if moderado else "estable"
        return False, f"PSI={_fmt(valor_psi)} ({nivel})"

    # criterio == "efecto": significancia Y magnitud.
    if significativo and relevante:
        return True, (
            f"efecto={_fmt(efecto)} >= {umbral_efecto} y p={_fmt(p_valor)} < {alfa}: "
            "el cambio es distinguible del ruido y ademas es grande"
        )
    if significativo and not relevante:
        return False, (
            f"significativo (p={_fmt(p_valor)}) pero efecto={_fmt(efecto)} < {umbral_efecto}: "
            "diferencia detectable por el tamano de muestra, no por su magnitud"
        )
    if relevante and not significativo:
        return False, (
            f"efecto={_fmt(efecto)} >= {umbral_efecto} pero p={_fmt(p_valor)} >= {alfa}: "
            "muestra insuficiente para distinguirlo del ruido; recolectar mas datos"
        )
    return False, f"sin evidencia: efecto={_fmt(efecto)}, p={_fmt(p_valor)}"


def _fmt(valor: float | None) -> str:
    return "n/d" if valor is None else f"{valor:.4g}"


def umbral_de(columna: str, tipo: str, umbrales: Mapping[str, float] | None = None) -> float:
    """Umbral de tamano de efecto de una columna, con fallback por tipo."""
    tabla = dict(UMBRALES_POR_FEATURE)
    if umbrales:
        tabla.update(umbrales)
    if columna in tabla:
        return tabla[columna]
    return UMBRAL_KS if tipo == TIPO_NUMERICA else UMBRAL_CRAMER


# =============================================================================
# Evaluacion por columna
# =============================================================================
def evaluar_numerica(
    referencia: pd.Series,
    actual: pd.Series,
    *,
    columna: str,
    criterio: Criterio = "efecto",
    umbral_efecto: float | None = None,
    alfa: float = ALFA,
    max_filas: int = MAX_FILAS,
) -> ResultadoColumna:
    """Kolmogorov-Smirnov de dos muestras + PSI + Jensen-Shannon.

    El estadistico D del KS **es** el tamano de efecto: la maxima distancia
    vertical entre las dos CDF empiricas, en [0, 1] e independiente de n. Que el
    test traiga su propio tamano de efecto es la razon por la que el KS es un
    buen primer test para numericas; el p-valor asociado, en cambio, es el que
    hay que mirar con desconfianza cuando n es grande.

    Limitaciones que hay que decir en clase: el KS es poco sensible en las colas
    (donde suele estar el riesgo) y no aplica a distribuciones discretas con
    muchos empates sin correcciones. Para colas, Wasserstein o un cuantil
    explicito son mejores.
    """
    ref = pd.to_numeric(referencia, errors="coerce").dropna()
    act = pd.to_numeric(actual, errors="coerce").dropna()
    umbral = umbral_efecto if umbral_efecto is not None else umbral_de(columna, TIPO_NUMERICA)

    if ref.empty or act.empty:
        return ResultadoColumna(
            columna=columna,
            tipo=TIPO_NUMERICA,
            metodo="ks_2samp",
            drift=False,
            motivo="no evaluable: una de las dos muestras esta vacia",
            umbral_efecto=umbral,
            n_referencia=len(ref),
            n_actual=len(act),
            aviso="muestra vacia",
        )

    ref_m, recortada_ref = _submuestrear(ref, max_filas, SEMILLA)
    act_m, recortada_act = _submuestrear(act, max_filas, SEMILLA)
    aviso = f"submuestreado a {max_filas} filas" if (recortada_ref or recortada_act) else ""

    resultado = stats.ks_2samp(ref_m.to_numpy(), act_m.to_numpy())
    estadistico = float(resultado.statistic)
    p_valor = float(resultado.pvalue)

    valor_psi = psi(ref, act)
    js = distancia_jensen_shannon(ref, act)

    drift, motivo = _decidir(
        criterio=criterio,
        p_valor=p_valor,
        efecto=estadistico,
        umbral_efecto=umbral,
        valor_psi=valor_psi,
        alfa=alfa,
    )
    return ResultadoColumna(
        columna=columna,
        tipo=TIPO_NUMERICA,
        metodo="ks_2samp",
        drift=drift,
        motivo=motivo,
        estadistico=estadistico,
        p_valor=p_valor,
        tamano_efecto=estadistico,
        nombre_efecto="ks_d",
        umbral_efecto=umbral,
        psi=valor_psi,
        jensen_shannon=js,
        n_referencia=len(ref),
        n_actual=len(act),
        aviso=aviso,
    )


def evaluar_categorica(
    referencia: pd.Series,
    actual: pd.Series,
    *,
    columna: str,
    criterio: Criterio = "efecto",
    umbral_efecto: float | None = None,
    alfa: float = ALFA,
    min_frecuencia: int = MIN_FRECUENCIA_ESPERADA,
) -> ResultadoColumna:
    """Chi-cuadrado de independencia + V de Cramer + PSI + Jensen-Shannon.

    Se contrasta la tabla de contingencia (categoria x periodo): si el periodo no
    aporta informacion sobre la categoria, no hay drift.

    Dos trampas que se manejan aqui de forma explicita:

    1. **Celdas con frecuencia esperada baja.** El chi-cuadrado asume esperadas
       >= 5 por celda. `PU_DO` tiene miles de niveles y una cola larguisima de
       pares vistos una o dos veces; sin agrupar, el estadistico se infla y el
       test detecta drift siempre. Las categorias raras se agrupan en ``OTRAS``.
    2. **Categorias nuevas.** Un valor que no existia en la referencia es una
       senal de drift de pleno derecho (una zona nueva, un codigo nuevo) y se
       reporta aparte en ``categorias_nuevas``, porque el test lo diluye entre
       las demas celdas.
    """
    ref = referencia.astype("string").fillna("_nulo")
    act = actual.astype("string").fillna("_nulo")
    umbral = umbral_efecto if umbral_efecto is not None else umbral_de(columna, TIPO_CATEGORICA)

    if ref.empty or act.empty:
        return ResultadoColumna(
            columna=columna,
            tipo=TIPO_CATEGORICA,
            metodo="chi2_contingency",
            drift=False,
            motivo="no evaluable: una de las dos muestras esta vacia",
            umbral_efecto=umbral,
            n_referencia=len(ref),
            n_actual=len(act),
            aviso="muestra vacia",
        )

    conteo_ref = ref.value_counts()
    conteo_act = act.value_counts()
    nuevas = sorted(set(conteo_act.index) - set(conteo_ref.index))

    total = _agrupar_categorias_raras(
        conteo_ref.add(conteo_act, fill_value=0).astype("float64"), min_frecuencia
    )
    categorias = [c for c in total.index if c != OTRAS]
    filas_ref = [float(conteo_ref.get(c, 0)) for c in categorias]
    filas_act = [float(conteo_act.get(c, 0)) for c in categorias]
    if OTRAS in total.index:
        resto_ref = float(conteo_ref.sum()) - sum(filas_ref)
        resto_act = float(conteo_act.sum()) - sum(filas_act)
        categorias.append(OTRAS)
        filas_ref.append(resto_ref)
        filas_act.append(resto_act)

    tabla = np.array([filas_ref, filas_act], dtype="float64")
    # Se descartan columnas todo-cero: chi2_contingency falla con esperadas 0.
    tabla = tabla[:, tabla.sum(axis=0) > 0]

    aviso = ""
    if tabla.shape[1] < 2:
        aviso = "una sola categoria efectiva; el chi-cuadrado no aplica"
        return ResultadoColumna(
            columna=columna,
            tipo=TIPO_CATEGORICA,
            metodo="chi2_contingency",
            drift=False,
            motivo="no evaluable: " + aviso,
            umbral_efecto=umbral,
            n_referencia=len(ref),
            n_actual=len(act),
            categorias_nuevas=len(nuevas),
            aviso=aviso,
        )

    chi2, p_valor, _, _ = stats.chi2_contingency(tabla)
    cramer = v_de_cramer(tabla, float(chi2))
    valor_psi = psi(ref, act, categorica=True)
    js = distancia_jensen_shannon(ref, act, categorica=True)

    if OTRAS in categorias:
        aviso = f"categorias con menos de {min_frecuencia} observaciones agrupadas en {OTRAS}"

    drift, motivo = _decidir(
        criterio=criterio,
        p_valor=float(p_valor),
        efecto=cramer,
        umbral_efecto=umbral,
        valor_psi=valor_psi,
        alfa=alfa,
    )
    if nuevas:
        motivo += f"; {len(nuevas)} categorias nuevas respecto a la referencia"
    return ResultadoColumna(
        columna=columna,
        tipo=TIPO_CATEGORICA,
        metodo="chi2_contingency",
        drift=drift,
        motivo=motivo,
        estadistico=float(chi2),
        p_valor=float(p_valor),
        tamano_efecto=cramer,
        nombre_efecto="cramer_v",
        umbral_efecto=umbral,
        psi=valor_psi,
        jensen_shannon=js,
        n_referencia=len(ref),
        n_actual=len(act),
        categorias_nuevas=len(nuevas),
        aviso=aviso,
    )


# =============================================================================
# Punto de entrada del modulo
# =============================================================================
def linea_base_nula(
    referencia: pd.DataFrame,
    *,
    columnas_numericas: Sequence[str],
    columnas_categoricas: Sequence[str],
    semilla: int = SEMILLA,
) -> dict[str, float]:
    """Tamano de efecto entre dos mitades aleatorias de la referencia.

    Es el ruido del instrumento: por construccion **no hay drift** entre dos
    mitades del mismo dataset, asi que cualquier efecto que aparezca es el sesgo y
    la varianza del estimador con este `n` y esta cardinalidad.

    Para que sirve: **calibrar los umbrales**. Un umbral por debajo de la linea
    base nula produce falsos positivos garantizados, y ese es un error real y
    comun con features categoricas de alta cardinalidad: la V de Cramer tiene
    sesgo positivo cuando hay muchas celdas con conteos bajos, asi que `PU_DO`
    marca ~0.12 sobre datos donde no pasa nada. Un umbral de 0.10 para esa columna
    habria alertado sobre dos mitades del mismo mes.

    El procedimiento —medir el ruido antes de fijar el umbral— es el mismo que se
    usa para calibrar cualquier alerta, y es lo que separa un umbral defendible de
    un numero copiado de un blog.

    Returns:
        ``{columna: tamano_de_efecto}``. Compararlo con ``UMBRALES_POR_FEATURE``.
    """
    mitad_a = referencia.sample(frac=0.5, random_state=semilla)
    mitad_b = referencia.drop(mitad_a.index)
    resultado = detectar_drift(
        mitad_a,
        mitad_b,
        columnas_numericas=columnas_numericas,
        columnas_categoricas=columnas_categoricas,
    )
    return {
        columna.columna: float(columna.tamano_efecto)
        for columna in resultado.columnas
        if columna.tamano_efecto is not None
    }


def detectar_drift(
    referencia: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    columnas_numericas: Sequence[str],
    columnas_categoricas: Sequence[str],
    criterio: Criterio = "efecto",
    umbral_columnas: float = 0.30,
    umbrales_efecto: Mapping[str, float] | None = None,
    alfa: float = ALFA,
) -> ResultadoDrift:
    """Evalua drift columna por columna y agrega el veredicto del dataset.

    Args:
        referencia: datos con los que se entreno (o el periodo base).
        actual: datos de produccion a evaluar.
        columnas_numericas: se evaluan con KS.
        columnas_categoricas: se evaluan con chi-cuadrado.
        criterio: ``"efecto"`` (recomendado), ``"p_valor"`` (didactico, malo) o
            ``"psi"``.
        umbral_columnas: fraccion de columnas con drift que dispara la alerta.
        umbrales_efecto: sobreescribe ``UMBRALES_POR_FEATURE`` por columna.
        alfa: nivel de significancia de los tests.

    Returns:
        ``ResultadoDrift`` con el detalle por columna. Las columnas ausentes en
        cualquiera de los dos dataframes se omiten y se anotan en ``avisos``: una
        columna que desaparece es un problema de contrato de datos (S02), no de
        drift, y mezclarlos esconde el mas grave de los dos.
    """
    if criterio not in CRITERIOS:
        raise ValueError(f"criterio invalido: {criterio!r}. Opciones: {CRITERIOS}")

    avisos: list[str] = []
    resultados: list[ResultadoColumna] = []

    for columna in columnas_numericas:
        if columna not in referencia.columns or columna not in actual.columns:
            avisos.append(f"columna numerica ausente, no evaluada: {columna}")
            continue
        resultados.append(
            evaluar_numerica(
                referencia[columna],
                actual[columna],
                columna=columna,
                criterio=criterio,
                umbral_efecto=(umbrales_efecto or {}).get(columna),
                alfa=alfa,
            )
        )

    for columna in columnas_categoricas:
        if columna not in referencia.columns or columna not in actual.columns:
            avisos.append(f"columna categorica ausente, no evaluada: {columna}")
            continue
        resultados.append(
            evaluar_categorica(
                referencia[columna],
                actual[columna],
                columna=columna,
                criterio=criterio,
                umbral_efecto=(umbrales_efecto or {}).get(columna),
                alfa=alfa,
            )
        )

    if not resultados:
        avisos.append("no se evaluo ninguna columna: revisa los nombres del contrato")

    resultado = ResultadoDrift(
        motor="estadistico",
        criterio=criterio,
        columnas=tuple(resultados),
        umbral_columnas=umbral_columnas,
        avisos=tuple(avisos),
    )
    logger.info(
        "drift (motor=estadistico, criterio=%s): %d/%d columnas (%.1f%%), umbral %.0f%% -> %s",
        criterio,
        len(resultado.con_drift),
        len(resultado.columnas),
        100 * resultado.fraccion_con_drift,
        100 * umbral_columnas,
        "ALERTA" if resultado.hay_drift else "ok",
    )
    return resultado
