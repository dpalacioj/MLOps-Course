"""Entrenamiento con tracking, comparacion de modelos y busqueda de hiperparametros.

Problema que resuelve
---------------------
Entrenar un modelo es facil; saber **cual** modelo se entreno, con que datos, con
que parametros y si es mejor que el anterior es el trabajo real. Este modulo
existe para que cada entrenamiento deje evidencia suficiente como para
reproducirlo y para compararlo con cualquier otro, sin depender de la memoria de
quien lo corrio.

Tres decisiones estructurales, con su motivo:

**1. El preprocesamiento va DENTRO del artefacto.** El pipeline serializado
incluye el vectorizador. Guardar `preprocessor.b` y `model.ubj` como archivos
separados y copiarlos a mano entre modulos tiene un fallo silencioso: si los dos
se desincronizan, el modelo sirve predicciones sobre features mal codificadas y
nada lanza una excepcion. Un artefacto, una version, un hash.

**2. Los valores por defecto viven en un solo lugar.** Declarar
`EARLY_STOPPING_ROUNDS = 50` y entrenar con `num_boost_round=30` hace que el
early stopping no pueda dispararse nunca, porque el entrenamiento termina
antes de acumular 50 rondas sin mejora. Ademas definia constantes
(`MAX_DEPTH`, `LEARNING_RATE`) que ningun call site usaba. Aqui las constantes
son la unica fuente y el test `test_early_stopping_tiene_margen` verifica que la
relacion entre ambas siga teniendo sentido.

**3. El holdout no se toca durante la seleccion.** Los hiperparametros se eligen
con `PARTICION_VALID`. `PARTICION_TEST` se evalua, como maximo, una vez por
candidato y solo para el gate de promocion. Si se usa para tunear, el gate deja
de medir generalizacion y pasa a medir cuanto se sobreajusto al juez.

Nota sobre serializacion
------------------------
`mlflow.sklearn.log_model` usa `serialization_format='skops'` por defecto en
mlflow 3 (antes era cloudpickle). skops carga solo tipos de una allowlist en
lugar de ejecutar codigo arbitrario al deserializar, lo que cierra un vector de
ejecucion remota de codigo: un artefacto de modelo es un archivo que baja de un
bucket y se carga en un proceso de produccion. El precio es que los tipos que no
son de sklearn hay que declararlos con `skops_trusted_types`; ver
`_tipos_confiables_skops`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import mlflow
import numpy as np
import optuna
import pandas as pd
import xgboost
from matplotlib.figure import Figure
from mlflow.models import infer_signature
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from xgboost import XGBRegressor

from taxi import config
from taxi.data import loaders
from taxi.features import contract as fc
from taxi.models import evaluate, registry

logger = logging.getLogger(__name__)


# =============================================================================
# Hiperparametros por defecto — UNICA fuente de verdad
# =============================================================================
#: Rondas maximas de boosting. Es el techo, no el objetivo: con early stopping
#: activo el entrenamiento para solo cuando deja de mejorar.
RONDAS_BOOST: Final[int] = 500
#: Rondas consecutivas sin mejora en validacion antes de detener.
#: INVARIANTE: debe ser bastante menor que RONDAS_BOOST. Si no lo es, el early
#: stopping es decorativo: con 50 sobre 30 rondas no puede dispararse nunca.
RONDAS_EARLY_STOPPING: Final[int] = 50

PARAMS_XGBOOST: Final[dict[str, Any]] = {
    "n_estimators": RONDAS_BOOST,
    "early_stopping_rounds": RONDAS_EARLY_STOPPING,
    "max_depth": 6,
    "learning_rate": 0.1,
    "min_child_weight": 1.0,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "tree_method": "hist",
    "random_state": config.SEMILLA,
    "n_jobs": -1,
    "verbosity": 0,
}

PARAMS_RANDOM_FOREST: Final[dict[str, Any]] = {
    # 100 arboles con profundidad acotada: el objetivo es que entrenar en clase
    # tarde segundos. Un bosque sin acotar sobre ~4000 features one-hot tarda
    # minutos y nadie itera.
    "n_estimators": 100,
    "max_depth": 20,
    "min_samples_leaf": 5,
    "n_jobs": -1,
    "random_state": config.SEMILLA,
}

#: Espacio de busqueda de Optuna. Los rangos son los que se tunean; todo lo que
#: no aparece aqui se toma de PARAMS_XGBOOST. Definirlo como dato y no como
#: codigo permite loguearlo con el study y saber que espacio se exploro.
ESPACIO_XGBOOST: Final[dict[str, tuple[Any, ...]]] = {
    "max_depth": ("int", 3, 12),
    "learning_rate": ("logfloat", 0.01, 0.3),
    "min_child_weight": ("logfloat", 0.5, 20.0),
    "subsample": ("float", 0.6, 1.0),
    "colsample_bytree": ("float", 0.6, 1.0),
    "reg_alpha": ("logfloat", 1e-3, 10.0),
    "reg_lambda": ("logfloat", 1e-3, 10.0),
}

#: Muestra maxima para el grafico de residuales. Un scatter de 180 000 puntos
#: pesa megabytes y no muestra nada que no muestre uno de 5000.
MAX_PUNTOS_RESIDUALES: Final[int] = 5_000
#: Features a mostrar en el grafico de importancia. Con PU_DO one-hot hay miles.
TOP_FEATURES_GRAFICO: Final[int] = 20


# =============================================================================
# Adaptador de frontera del pipeline
# =============================================================================
class ADiccionarios(BaseEstimator, TransformerMixin):
    """Convierte un DataFrame en la lista de diccionarios que espera DictVectorizer.

    Por que existe: `DictVectorizer` consume `Iterable[Mapping]`, no DataFrames.
    Si el pipeline arranca directamente en el vectorizador, el artefacto queda
    inservible al cargarse como pyfunc: MLflow convierte la entrada a DataFrame
    antes de llamar a `predict`, y el vectorizador falla con un
    `AttributeError: 'str' object has no attribute 'items'` (verificado contra
    mlflow 3.15.1). El sintoma aparece en produccion, no al entrenar.

    Poner la conversion como primer paso del pipeline hace que el artefacto
    acepte las dos formas —DataFrame y lista de diccionarios— y que la frontera
    del modelo quede versionada junto a el en lugar de reimplementarse en cada
    consumidor (API, batch, gate). Esa duplicacion era la causa de que el repo
    anterior tuviera tres definiciones incompatibles de las mismas features.
    """

    def __init__(self, columnas: list[str] | None = None) -> None:
        self.columnas = columnas

    def fit(self, X: Any, y: Any = None) -> ADiccionarios:
        """No aprende nada; existe para cumplir la interfaz de sklearn."""
        return self

    def transform(self, X: Any) -> list[dict[str, Any]]:
        """Normaliza la entrada a lista de diccionarios."""
        if isinstance(X, pd.DataFrame):
            columnas = self.columnas or list(X.columns)
            faltantes = [c for c in columnas if c not in X.columns]
            if faltantes:
                raise KeyError(
                    f"Faltan features en la entrada del modelo: {faltantes}. Esperadas: {columnas}"
                )
            return X[columnas].to_dict(orient="records")
        return list(X)


# =============================================================================
# Construccion de pipelines
# =============================================================================
def _envolver(estimador: Any) -> Pipeline:
    """Envuelve un estimador en el pipeline estandar del curso."""
    return Pipeline(
        [
            ("diccionarios", ADiccionarios(list(fc.FEATURES))),
            ("vectorizador", DictVectorizer(sparse=True)),
            ("modelo", estimador),
        ]
    )


def pipeline_media() -> Pipeline:
    """Baseline trivial: predecir siempre la duracion media.

    No es un modelo, es la vara de medir. Cualquier modelo que no le gane no
    esta aprendiendo nada del dato, y sin este numero un RMSE de 6.5 minutos no
    se puede interpretar.
    """
    return _envolver(DummyRegressor(strategy="mean"))


def pipeline_lineal() -> Pipeline:
    """Baseline razonable: regresion lineal sobre las features one-hot.

    Es el segundo escalon: entrena en segundos, es interpretable y suele quedar
    a un 10-15% del mejor modelo. La distancia entre este y el modelo complejo
    es la que justifica (o no) el costo operativo del modelo complejo.
    """
    return _envolver(LinearRegression())


def pipeline_random_forest(**overrides: Any) -> Pipeline:
    """RandomForest con los parametros de ``PARAMS_RANDOM_FOREST``."""
    params = {**PARAMS_RANDOM_FOREST, **overrides}
    return _envolver(RandomForestRegressor(**params))


def pipeline_xgboost(**overrides: Any) -> Pipeline:
    """XGBoost con los parametros de ``PARAMS_XGBOOST``.

    ``early_stopping_rounds`` se pasa en el constructor (es la forma vigente en
    xgboost 3.x con la API de sklearn, no un argumento de ``fit``) y solo tiene
    efecto si ``fit`` recibe ``eval_set``. Eso lo garantiza ``ajustar``.
    """
    params = {**PARAMS_XGBOOST, **overrides}
    return _envolver(XGBRegressor(**params))


CONSTRUCTORES: Final[dict[str, Any]] = {
    "media": pipeline_media,
    "lineal": pipeline_lineal,
    "random_forest": pipeline_random_forest,
    "xgboost": pipeline_xgboost,
}


def _usa_early_stopping(pipeline: Pipeline) -> bool:
    """True si el estimador final necesita ``eval_set`` para el early stopping."""
    modelo = pipeline.named_steps["modelo"]
    return bool(getattr(modelo, "early_stopping_rounds", None))


def ajustar(
    pipeline: Pipeline,
    df_train: pd.DataFrame,
    df_valid: pd.DataFrame | None = None,
    *,
    callbacks: Sequence[Any] | None = None,
) -> Pipeline:
    """Ajusta el pipeline, activando early stopping cuando corresponde.

    Aqui hay una sutileza que conviene mostrar en clase: ``eval_set`` de XGBoost
    espera la matriz **ya transformada**. Si se pasara el DataFrame de
    validacion, XGBoost lo veria con un numero de columnas distinto al de
    entrenamiento. Por eso los pasos de preprocesamiento se ajustan primero y de
    forma explicita, y el ``eval_set`` se construye con ``transform`` (nunca con
    ``fit_transform``: eso seria leakage del conjunto de validacion al
    vocabulario del vectorizador).

    Args:
        pipeline: pipeline sin ajustar.
        df_train: datos de entrenamiento, ya procesados.
        df_valid: datos de validacion. Obligatorio si el modelo usa early
            stopping.
        callbacks: callbacks de XGBoost (p. ej. el podador de Optuna).

    Returns:
        El mismo pipeline, ajustado.
    """
    y_train = df_train[fc.TARGET_REGRESION].to_numpy(dtype=float)

    if not _usa_early_stopping(pipeline):
        pipeline.fit(df_train, y_train)
        return pipeline

    if df_valid is None:
        raise ValueError(
            "El modelo tiene early_stopping_rounds pero no se paso df_valid. "
            "Sin eval_set el early stopping no se dispara nunca."
        )

    a_dicts = pipeline.named_steps["diccionarios"]
    vectorizador = pipeline.named_steps["vectorizador"]
    modelo = pipeline.named_steps["modelo"]

    x_train = vectorizador.fit_transform(a_dicts.fit_transform(df_train))
    x_valid = vectorizador.transform(a_dicts.transform(df_valid))
    y_valid = df_valid[fc.TARGET_REGRESION].to_numpy(dtype=float)

    if callbacks:
        modelo.set_params(callbacks=list(callbacks))
    modelo.fit(x_train, y_train, eval_set=[(x_valid, y_valid)], verbose=False)

    if callbacks:
        # Se DESATAN los callbacks en cuanto termina el fit. No es cosmetica:
        # xgboost los guarda como un parametro del estimador, y el podador de
        # Optuna mantiene una referencia al Trial, que referencia al Study, que
        # referencia al sampler, al pruner y al storage con el historial completo.
        # Al serializar el pipeline, todo eso viaja DENTRO del artefacto del
        # modelo. Con skops falla de forma ruidosa ("untrusted types: optuna...");
        # con cloudpickle habria funcionado en silencio, dejando un artefacto
        # inflado que solo se puede cargar donde optuna este instalado y con la
        # misma version. El objeto que se registra debe contener el modelo y su
        # preprocesamiento, nada mas.
        modelo.set_params(callbacks=None)
    return pipeline


# =============================================================================
# Carga de datos
# =============================================================================
def cargar_particion(particion: config.Particion, *, usar_cache: bool = True) -> pd.DataFrame:
    """Carga una particion procesada, desde cache si esta disponible.

    El cache se llama como la particion (``data/processed/2023-01.parquet``) para
    que un mismo mes no se materialice dos veces con dos nombres distintos.
    """
    if usar_cache:
        cacheado = loaders.cargar_cache(particion.etiqueta)
        if cacheado is not None:
            logger.info("%s: %d filas desde cache", particion, len(cacheado))
            return cacheado
    df = loaders.preparar_particion(particion)
    loaders.cachear(df, particion.etiqueta)
    return df


def cargar_split(
    particiones: Sequence[config.Particion],
    *,
    usar_cache: bool = True,
) -> pd.DataFrame:
    """Concatena varias particiones en orden temporal."""
    marcos = [cargar_particion(p, usar_cache=usar_cache) for p in particiones]
    return pd.concat(marcos, ignore_index=True).sort_values(fc.COL_PICKUP).reset_index(drop=True)


def cargar_train(*, usar_cache: bool = True) -> pd.DataFrame:
    """Datos de entrenamiento (``PARTICIONES_TRAIN``)."""
    return cargar_split(config.PARTICIONES_TRAIN, usar_cache=usar_cache)


def cargar_valid(*, usar_cache: bool = True) -> pd.DataFrame:
    """Datos de validacion (``PARTICION_VALID``). Aqui SI se seleccionan hiperparametros."""
    return cargar_particion(config.PARTICION_VALID, usar_cache=usar_cache)


def cargar_holdout(*, usar_cache: bool = True) -> pd.DataFrame:
    """Holdout fijo (``PARTICION_TEST``).

    ADVERTENCIA: este conjunto es el juez del gate de promocion. No se usa para
    elegir modelos ni hiperparametros. Cada vez que se mira para tomar una
    decision de modelado se gasta un poco de su capacidad de estimar
    generalizacion, y esa capacidad no se recupera.
    """
    return cargar_particion(config.PARTICION_TEST, usar_cache=usar_cache)


def preparar_datos(*, usar_cache: bool = True) -> dict[str, int]:
    """Materializa y cachea todas las particiones del caso guia.

    Returns:
        ``{etiqueta_de_particion: numero_de_filas}``.
    """
    config.asegurar_directorios()
    filas: dict[str, int] = {}
    for particion in config.TODAS_LAS_PARTICIONES:
        df = cargar_particion(particion, usar_cache=usar_cache)
        filas[particion.etiqueta] = len(df)
    return filas


# =============================================================================
# Tracking
# =============================================================================
def preparar_mlflow(clave_experimento: str) -> str:
    """Apunta MLflow al tracking server del curso y fija el experimento."""
    nombre = config.EXPERIMENTOS.get(clave_experimento, clave_experimento)
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(nombre)
    logger.info("MLflow: %s | experimento %s", config.MLFLOW_TRACKING_URI, nombre)
    return nombre


def _tipos_confiables_skops(pipeline: Pipeline) -> list[str]:
    """Tipos que skops debe aceptar al deserializar este pipeline.

    skops solo reconstruye tipos de una allowlist; cualquier otro hay que
    declararlo explicitamente. Es exactamente lo contrario de cloudpickle, que
    ejecuta lo que venga en el archivo. Declarar la lista a mano se siente
    tedioso hasta que se piensa que la alternativa es "cargar un .pkl que bajo
    de un bucket y confiar".

    Verificado contra mlflow 3.15.1 + skops: sin esto, `log_model` de un
    pipeline con `ADiccionarios` o con `XGBRegressor` falla con
    "The saved sklearn model references untrusted types".
    """
    tipos = [f"{ADiccionarios.__module__}.{ADiccionarios.__qualname__}"]
    if isinstance(pipeline.named_steps["modelo"], xgboost.sklearn.XGBModel):
        tipos += ["xgboost.core.Booster", "xgboost.sklearn.XGBRegressor"]
    return tipos


def _ejemplo_de_entrada(df: pd.DataFrame, filas: int = 5) -> pd.DataFrame:
    """Construye el input_example con los tipos MAS ANCHOS de cada feature.

    Aqui hay una trampa que solo aparece al servir, no al entrenar. El dataframe
    procesado guarda ``hora_pickup`` como ``int16`` para ahorrar memoria. Si el
    input_example se pasa tal cual, ``infer_signature`` declara la columna como
    ``integer`` (int32) y MLflow, al hacer enforcement de la firma, RECHAZA una
    peticion cuya columna llegue como ``int64`` —que es lo que produce cualquier
    cliente normal, incluido pandas por defecto— con el mensaje
    "Can not safely convert int64 to int32". Verificado contra mlflow 3.15.1.

    La regla general: una firma es un contrato con consumidores que no controlas.
    Debe declarar el tipo mas permisivo que el modelo acepta, no el mas compacto
    con el que se entreno. MLflow permite ensanchar (int16 -> int64) pero nunca
    estrechar.
    """
    ejemplo = df[fc.FEATURES].head(filas).copy()
    for columna in fc.FEATURES_NUMERICAS:
        if pd.api.types.is_integer_dtype(ejemplo[columna]):
            ejemplo[columna] = ejemplo[columna].astype("int64")
        else:
            ejemplo[columna] = ejemplo[columna].astype("float64")
    for columna in fc.FEATURES_CATEGORICAS:
        ejemplo[columna] = ejemplo[columna].astype("string").astype("object")
    return ejemplo


def _figura_importancia(pipeline: Pipeline) -> Figure | None:
    """Grafico de las features mas influyentes, o ``None`` si el modelo no expone importancia."""
    modelo = pipeline.named_steps["modelo"]
    if hasattr(modelo, "feature_importances_"):
        pesos = np.asarray(modelo.feature_importances_, dtype=float)
        titulo = "Importancia de features (ganancia)"
    elif hasattr(modelo, "coef_"):
        pesos = np.abs(np.asarray(modelo.coef_, dtype=float)).reshape(-1)
        titulo = "Magnitud del coeficiente lineal"
    else:
        return None

    nombres = np.asarray(pipeline.named_steps["vectorizador"].get_feature_names_out())
    if len(nombres) != len(pesos):
        logger.warning("nombres (%d) y pesos (%d) no coinciden", len(nombres), len(pesos))
        return None

    orden = np.argsort(pesos)[-TOP_FEATURES_GRAFICO:]
    fig = Figure(figsize=(8, 6))
    ejes = fig.add_subplot(111)
    ejes.barh(nombres[orden], pesos[orden], color="#3b6ea5")
    ejes.set_title(f"{titulo} — top {TOP_FEATURES_GRAFICO}")
    ejes.set_xlabel("importancia")
    fig.tight_layout()
    return fig


def _figura_residuales(y_true: np.ndarray, y_pred: np.ndarray) -> Figure:
    """Residuales contra prediccion.

    Es el grafico que revela lo que el RMSE esconde: heterocedasticidad, sesgo
    sistematico en los viajes largos, y el efecto del filtro de duracion (los
    residuales se truncan en los bordes del rango valido).
    """
    generador = np.random.default_rng(config.SEMILLA)
    if len(y_true) > MAX_PUNTOS_RESIDUALES:
        indices = generador.choice(len(y_true), size=MAX_PUNTOS_RESIDUALES, replace=False)
        y_true, y_pred = y_true[indices], y_pred[indices]

    fig = Figure(figsize=(8, 5))
    ejes = fig.add_subplot(111)
    ejes.scatter(y_pred, y_true - y_pred, s=6, alpha=0.25, color="#3b6ea5")
    ejes.axhline(0.0, color="#b03030", linewidth=1.2)
    ejes.set_xlabel("duracion predicha (min)")
    ejes.set_ylabel("residual = real - predicha (min)")
    ejes.set_title("Residuales en validacion")
    fig.tight_layout()
    return fig


@dataclass
class ResultadoEntrenamiento:
    """Todo lo que un entrenamiento debe devolver para ser comparable."""

    nombre: str
    run_id: str
    model_uri: str
    params: dict[str, Any] = field(default_factory=dict)
    metricas: dict[str, float] = field(default_factory=dict)
    subgrupos: dict[str, float] = field(default_factory=dict)
    version_registrada: str | None = None

    @property
    def rmse_valid(self) -> float:
        return float(self.metricas.get("valid_rmse", float("nan")))


def _loguear_entrenamiento(
    nombre: str,
    pipeline: Pipeline,
    df_train: pd.DataFrame,
    df_valid: pd.DataFrame,
    *,
    params_extra: Mapping[str, Any] | None = None,
    registrar: bool = False,
    tags_extra: Mapping[str, str] | None = None,
) -> ResultadoEntrenamiento:
    """Loguea params, metricas, artefactos y el modelo del run activo.

    Asume que ya hay un run activo: quien llama decide si es un run suelto, un
    child run de HPO o el run final del mejor modelo.
    """
    run = mlflow.active_run()
    if run is None:
        raise RuntimeError("_loguear_entrenamiento requiere un run de MLflow activo")

    modelo = pipeline.named_steps["modelo"]
    params: dict[str, Any] = {
        "modelo": type(modelo).__name__,
        "n_features_vectorizadas": len(
            pipeline.named_steps["vectorizador"].get_feature_names_out()
        ),
        "filas_train": len(df_train),
        "filas_valid": len(df_valid),
        "semilla": config.SEMILLA,
        **{f"m_{k}": v for k, v in modelo.get_params().items() if not callable(v)},
        **(params_extra or {}),
    }
    # callbacks es una lista de objetos: su repr contiene direcciones de memoria
    # y ensucia la comparacion de runs en la UI.
    params.pop("m_callbacks", None)
    mlflow.log_params(params)

    mlflow.set_tags(
        {
            "caso": "nyc-green-taxi",
            "target": fc.TARGET_REGRESION,
            "particiones_train": ",".join(p.etiqueta for p in config.PARTICIONES_TRAIN),
            "particion_valid": config.PARTICION_VALID.etiqueta,
            "features": ",".join(fc.FEATURES),
            "holdout_evaluado": "no",
            **(tags_extra or {}),
        }
    )

    metricas_train, _ = evaluate.evaluar_modelo(pipeline, df_train, prefijo="train_")
    metricas_valid, subgrupos = evaluate.evaluar_modelo(pipeline, df_valid, prefijo="valid_")
    metricas = {**metricas_train, **metricas_valid}
    mlflow.log_metrics({**metricas, **subgrupos})
    mlflow.log_dict(subgrupos, "metricas/subgrupos_valid.json")

    mejor_iteracion = getattr(modelo, "best_iteration", None)
    if mejor_iteracion is not None:
        # Evidencia de que el early stopping REALMENTE actuo. Si esto sale
        # siempre igual a n_estimators - 1, el early stopping no esta operando.
        mlflow.log_metric("mejor_iteracion", float(mejor_iteracion))

    figura = _figura_importancia(pipeline)
    if figura is not None:
        mlflow.log_figure(figura, "graficos/importancia_features.png")
    y_valid = df_valid[fc.TARGET_REGRESION].to_numpy(dtype=float)
    y_pred = np.asarray(pipeline.predict(df_valid), dtype=float).reshape(-1)
    mlflow.log_figure(_figura_residuales(y_valid, y_pred), "graficos/residuales_valid.png")

    ejemplo = _ejemplo_de_entrada(df_valid)
    firma = infer_signature(ejemplo, pipeline.predict(ejemplo))
    info = mlflow.sklearn.log_model(
        sk_model=pipeline,
        name="modelo",
        signature=firma,
        input_example=ejemplo,
        skops_trusted_types=_tipos_confiables_skops(pipeline),
        registered_model_name=config.MODELO_REGRESION if registrar else None,
    )

    version = getattr(info, "registered_model_version", None)
    if registrar:
        if version is None:
            mv = registry.ultima_version(config.MODELO_REGRESION)
            version = mv.version if mv else None
        if version is not None:
            registry.asignar_alias(config.MODELO_REGRESION, config.ALIAS_CANDIDATO, version)
            registry.marcar_validacion(config.MODELO_REGRESION, version, "pending")

    return ResultadoEntrenamiento(
        nombre=nombre,
        run_id=run.info.run_id,
        model_uri=info.model_uri,
        params=params,
        metricas=metricas,
        subgrupos=subgrupos,
        version_registrada=str(version) if version is not None else None,
    )


# =============================================================================
# Entrenamientos de alto nivel
# =============================================================================
def entrenar_baseline(
    *,
    modelo: str = "lineal",
    registrar: bool = False,
    usar_cache: bool = True,
    experimento: str = "baseline",
) -> ResultadoEntrenamiento:
    """Entrena un unico modelo y lo loguea en MLflow.

    Args:
        modelo: clave de ``CONSTRUCTORES`` (``media``, ``lineal``,
            ``random_forest``, ``xgboost``).
        registrar: si True, registra el modelo y le pone el alias ``candidate``.
        usar_cache: reutiliza las particiones ya materializadas.
        experimento: clave de ``config.EXPERIMENTOS``.
    """
    if modelo not in CONSTRUCTORES:
        raise ValueError(f"modelo desconocido: {modelo!r}. Opciones: {sorted(CONSTRUCTORES)}")

    preparar_mlflow(experimento)
    df_train = cargar_train(usar_cache=usar_cache)
    df_valid = cargar_valid(usar_cache=usar_cache)

    pipeline = CONSTRUCTORES[modelo]()
    with mlflow.start_run(run_name=f"baseline-{modelo}"):
        ajustar(pipeline, df_train, df_valid)
        resultado = _loguear_entrenamiento(
            modelo,
            pipeline,
            df_train,
            df_valid,
            registrar=registrar,
            tags_extra={"tipo": "baseline"},
        )
    logger.info("%s: valid_rmse=%.4f", modelo, resultado.rmse_valid)
    return resultado


def comparar_modelos(
    *,
    modelos: Sequence[str] = ("media", "lineal", "random_forest", "xgboost"),
    registrar_mejor: bool = False,
    usar_cache: bool = True,
    experimento: str = "comparacion",
) -> list[ResultadoEntrenamiento]:
    """Entrena varios modelos sobre los mismos datos y los compara.

    Cada modelo va en su propio run, con los mismos tags de datos y features.
    Esa es la condicion para que la comparacion signifique algo: si dos runs
    usaron particiones o features distintas, la diferencia de RMSE no se puede
    atribuir al modelo.

    El baseline ``media`` esta en la lista a proposito. Es el numero contra el
    que se interpreta todo lo demas.

    Returns:
        Resultados ordenados de mejor a peor ``valid_rmse``.
    """
    preparar_mlflow(experimento)
    df_train = cargar_train(usar_cache=usar_cache)
    df_valid = cargar_valid(usar_cache=usar_cache)

    resultados: list[ResultadoEntrenamiento] = []
    for nombre in modelos:
        if nombre not in CONSTRUCTORES:
            raise ValueError(f"modelo desconocido: {nombre!r}")
        pipeline = CONSTRUCTORES[nombre]()
        with mlflow.start_run(run_name=f"comparacion-{nombre}"):
            ajustar(pipeline, df_train, df_valid)
            resultados.append(
                _loguear_entrenamiento(
                    nombre,
                    pipeline,
                    df_train,
                    df_valid,
                    tags_extra={"tipo": "comparacion"},
                )
            )
        logger.info("%-14s valid_rmse=%.4f", nombre, resultados[-1].rmse_valid)

    resultados.sort(key=lambda r: r.rmse_valid)
    logger.info("Mejor modelo: %s (%.4f)", resultados[0].nombre, resultados[0].rmse_valid)

    if registrar_mejor:
        mejor = resultados[0]
        pipeline = CONSTRUCTORES[mejor.nombre]()
        with mlflow.start_run(run_name=f"registro-{mejor.nombre}"):
            ajustar(pipeline, df_train, df_valid)
            registrado = _loguear_entrenamiento(
                mejor.nombre,
                pipeline,
                df_train,
                df_valid,
                registrar=True,
                tags_extra={"tipo": "candidato", "seleccionado_por": "comparacion"},
            )
        resultados[0] = registrado
    return resultados


class _PodadorOptuna(xgboost.callback.TrainingCallback):
    """Puente entre el historial de evaluacion de XGBoost y el pruner de Optuna.

    Sin esto el pruner no tiene nada que podar: Optuna solo puede cortar un
    trial si recibe valores intermedios, y un ``fit`` de sklearn es una caja
    negra que solo devuelve el resultado final. El callback reporta el RMSE de
    validacion en cada ronda de boosting, con lo que Optuna puede abandonar
    temprano una combinacion que ya se ve peor que la mediana.

    (Existe ``optuna-integration`` con un callback equivalente, pero es un
    paquete aparte que este curso no declara como dependencia. Escribirlo a mano
    son diez lineas y muestra que el mecanismo no tiene magia.)
    """

    def __init__(self, trial: optuna.Trial, conjunto: str = "validation_0", metrica: str = "rmse"):
        self._trial = trial
        self._conjunto = conjunto
        self._metrica = metrica

    def after_iteration(self, model: Any, epoch: int, evals_log: Any) -> bool:
        historial = evals_log.get(self._conjunto, {}).get(self._metrica)
        if not historial:
            return False
        self._trial.report(float(historial[-1]), step=epoch)
        if self._trial.should_prune():
            raise optuna.TrialPruned(f"trial podado en la ronda {epoch}")
        return False


def _sugerir(trial: optuna.Trial) -> dict[str, Any]:
    """Traduce ``ESPACIO_XGBOOST`` a llamadas ``suggest_*``."""
    propuesta: dict[str, Any] = {}
    for nombre, spec in ESPACIO_XGBOOST.items():
        clase, bajo, alto = spec
        if clase == "int":
            propuesta[nombre] = trial.suggest_int(nombre, int(bajo), int(alto))
        elif clase == "logfloat":
            propuesta[nombre] = trial.suggest_float(nombre, float(bajo), float(alto), log=True)
        else:
            propuesta[nombre] = trial.suggest_float(nombre, float(bajo), float(alto))
    return propuesta


def optimizar_hiperparametros(
    trials: int = 20,
    *,
    registrar_mejor: bool = True,
    usar_cache: bool = True,
    experimento: str = "hpo",
) -> ResultadoEntrenamiento:
    """Busqueda de hiperparametros de XGBoost con Optuna.

    Estructura de runs: **un parent run para el study y un child run por trial**
    (``nested=True``). Es la diferencia entre una UI de MLflow legible y 200 runs
    sueltos sin relacion entre si. En el parent quedan el espacio de busqueda,
    el numero de trials y los mejores parametros; en cada child, la combinacion
    concreta y su metrica.

    El objetivo se calcula SIEMPRE sobre ``PARTICION_VALID``. El holdout no
    participa: la busqueda lo veria cientos de veces y el gate perderia sentido.

    Args:
        trials: numero de combinaciones a probar.
        registrar_mejor: reentrena con ``study.best_params`` y registra el modelo
            como candidato.
        usar_cache: reutiliza las particiones ya materializadas.
        experimento: clave de ``config.EXPERIMENTOS``.

    Returns:
        El resultado del reentrenamiento con los mejores parametros.
    """
    preparar_mlflow(experimento)
    df_train = cargar_train(usar_cache=usar_cache)
    df_valid = cargar_valid(usar_cache=usar_cache)

    def objetivo(trial: optuna.Trial) -> float:
        propuesta = _sugerir(trial)
        pipeline = pipeline_xgboost(**propuesta)
        with mlflow.start_run(run_name=f"trial-{trial.number:03d}", nested=True):
            ajustar(pipeline, df_train, df_valid, callbacks=[_PodadorOptuna(trial)])
            resultado = _loguear_entrenamiento(
                f"trial-{trial.number:03d}",
                pipeline,
                df_train,
                df_valid,
                params_extra={"trial": trial.number, **propuesta},
                tags_extra={"tipo": "hpo-trial"},
            )
        return resultado.rmse_valid

    # Sampler y pruner con semilla explicita: dos corridas del mismo study con
    # los mismos datos exploran las mismas combinaciones. Sin la semilla, "mi
    # mejor RMSE fue 4.31" no es una afirmacion reproducible.
    study = optuna.create_study(
        study_name=f"hpo-xgboost-{trials}",
        direction="minimize",
        sampler=TPESampler(seed=config.SEMILLA),
        pruner=MedianPruner(n_startup_trials=5, n_warmup_steps=20, interval_steps=10),
    )

    with mlflow.start_run(run_name=f"hpo-xgboost-{trials}-trials") as parent:
        mlflow.set_tags({"tipo": "hpo-parent", "sampler": "TPESampler", "pruner": "MedianPruner"})
        mlflow.log_params(
            {
                "trials": trials,
                "espacio": {k: list(v) for k, v in ESPACIO_XGBOOST.items()},
                "semilla": config.SEMILLA,
                "rondas_boost": RONDAS_BOOST,
                "rondas_early_stopping": RONDAS_EARLY_STOPPING,
            }
        )
        study.optimize(objetivo, n_trials=trials, catch=())

        completados = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
        podados = [t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED]
        mlflow.log_metrics(
            {
                "mejor_valid_rmse": float(study.best_value),
                "trials_completados": float(len(completados)),
                "trials_podados": float(len(podados)),
            }
        )
        mlflow.log_dict(dict(study.best_params), "hpo/best_params.json")
        logger.info(
            "HPO: mejor valid_rmse=%.4f con %s (%d completados, %d podados)",
            study.best_value,
            study.best_params,
            len(completados),
            len(podados),
        )

        pipeline = pipeline_xgboost(**study.best_params)
        with mlflow.start_run(run_name="mejor-modelo", nested=True):
            resultado = _loguear_entrenamiento(
                "xgboost-hpo",
                ajustar(pipeline, df_train, df_valid),
                df_train,
                df_valid,
                params_extra={"origen": "study.best_params", **study.best_params},
                registrar=registrar_mejor,
                tags_extra={
                    "tipo": "candidato",
                    "seleccionado_por": "hpo",
                    "parent_run_id": parent.info.run_id,
                },
            )
    return resultado


# =============================================================================
# Holdout — se mira al final y solo para el gate
# =============================================================================
def evaluar_en_holdout(
    modelo: Any,
    *,
    run_id: str | None = None,
    usar_cache: bool = True,
) -> tuple[dict[str, float], dict[str, float]]:
    """Evalua un modelo en el holdout fijo y, si se indica, loguea el resultado.

    Por que esta separado del entrenamiento y no es un paso mas del pipeline:

    - ``PARTICION_TEST`` es el juez del gate de promocion. Solo se mira **despues**
      de que la seleccion de modelo e hiperparametros haya terminado usando
      ``PARTICION_VALID``.
    - Usarlo para seleccionar convierte el holdout en un segundo conjunto de
      validacion. El numero que reporta sigue existiendo, pero deja de ser una
      estimacion de generalizacion: mide cuanto se ajusto la busqueda al juez.
      El gate seguiria en verde y el modelo seguiria degradandose en produccion.
    - Las metricas se loguean con el prefijo ``holdout_`` y el tag
      ``holdout_evaluado=si``, de modo que en la UI se ve exactamente que runs
      lo consultaron. Si son muchos, hay un problema de metodo.

    Args:
        modelo: pipeline ajustado o modelo pyfunc.
        run_id: run de MLflow donde loguear. ``None`` para no loguear.
        usar_cache: reutiliza el holdout materializado.

    Returns:
        Tupla ``(metricas_globales, metricas_por_subgrupo)``.
    """
    df_holdout = cargar_holdout(usar_cache=usar_cache)
    metricas, subgrupos = evaluate.evaluar_modelo(modelo, df_holdout, prefijo="holdout_")
    subgrupos_con_prefijo = {f"holdout_{k}": v for k, v in subgrupos.items()}

    if run_id:
        with mlflow.start_run(run_id=run_id):
            mlflow.log_metrics({**metricas, **subgrupos_con_prefijo})
            mlflow.set_tag("holdout_evaluado", "si")
            mlflow.set_tag("holdout_particion", config.PARTICION_TEST.etiqueta)
            mlflow.log_dict(subgrupos, "metricas/subgrupos_holdout.json")

    logger.info(
        "Holdout %s: rmse=%.4f mae=%.4f r2=%.4f",
        config.PARTICION_TEST,
        metricas["holdout_rmse"],
        metricas["holdout_mae"],
        metricas["holdout_r2"],
    )
    return metricas, subgrupos
