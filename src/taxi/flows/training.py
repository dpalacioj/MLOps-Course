"""Flow de entrenamiento orquestado con Prefect 3 (Sesion 4).

Que agrega la orquestacion sobre `taxi train`
---------------------------------------------
El mismo entrenamiento se puede lanzar a mano. Lo que agrega este flow es lo que
no se ve en la salida de la terminal:

1. **Grafo explicito**: cada paso es una `@task` y las dependencias se derivan de
   los datos que un paso le pasa al siguiente. Cuando falla, se sabe *cual* paso
   fallo, no solo que "el script fallo".
2. **Resiliencia**: `retries` con backoff en la unica task que habla con la red.
3. **Caching**: la preparacion de datos no se repite si los inputs no cambiaron.
4. **Observabilidad**: `get_run_logger()` escribe en el run, y los artifacts
   dejan el reporte de metricas **junto a la corrida** que lo produjo.
5. **Programacion**: el flow se puede desplegar con un schedule (ver
   :mod:`taxi.flows.deploy`).

Decision de diseno central
--------------------------
El flow **registra el candidato con el alias ``candidate`` y NO lo promueve**.

El atajo tentador es que cada corrida mueva la version a produccion usando la
antigua API de *stages* de MLflow (deprecada desde 2.9.0), que ademas archiva de
paso las versiones anteriores. Eso hace que un modelo llegue a produccion por el
solo hecho de que el entrenamiento termino sin excepciones: sin gate, sin
holdout y sin posibilidad de rechazo.

Aqui la responsabilidad esta separada:

- el flow **produce** un candidato y deja la evidencia (metricas + tags);
- el gate de promocion (Sesion 6, en CI) **decide** si ese candidato se convierte
  en `@champion`, comparandolo contra el champion actual en un holdout fijo.

Rollback, con esta separacion, es mover un alias: una operacion de un segundo.

Sobre la particion de test
--------------------------
Este flow evalua en `PARTICION_VALID`. `PARTICION_TEST` es el juez del gate y no
se toca aqui: si se usa para iterar, el gate deja de significar algo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pandas as pd
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact
from prefect.exceptions import MissingContextError
from prefect.logging.loggers import LoggingAdapter
from prefect.tasks import task_input_hash

from taxi.config import (
    ALIAS_CANDIDATO,
    EXPERIMENTOS,
    MLFLOW_TRACKING_URI,
    MODELO_REGRESION,
    PARTICION_VALID,
    PARTICIONES_TRAIN,
    SEMILLA,
    Particion,
)
from taxi.data import contract as dc
from taxi.data.loaders import cachear, descargar_particion, preparar_particiones
from taxi.features import contract as fc

#: Hiperparametros del **fallback** de este modulo. La fuente de verdad de los
#: hiperparametros del curso es `taxi.models.train.PARAMS_XGBOOST`; estos solo se
#: usan si ese modulo no esta disponible, para que el flow siga siendo ejecutable
#: por si mismo. Duplicarlos en dos lugares es como se acaba con cuatro
#: definiciones distintas del mismo modelo y ninguna que sea la de verdad.
PARAMS_FALLBACK: Final[dict[str, Any]] = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5.0,
}

#: Vigencia del cache de preparacion de datos. Las particiones de la TLC son
#: inmutables una vez publicadas, asi que 24 h es conservador; lo que protege es
#: el caso de una republicacion del archivo por parte del proveedor.
VIGENCIA_CACHE: Final[timedelta] = timedelta(hours=24)


def _log() -> logging.Logger | LoggingAdapter:
    """Logger del run si hay contexto de Prefect; logger de modulo si no.

    `get_run_logger()` lanza `MissingContextError` fuera de un run, y eso
    impediria invocar las tasks con `.fn()` en los tests unitarios. Con este
    fallback, la misma funcion se puede ejecutar dentro del flow (y sus logs
    aparecen en la UI, asociados al run) o como funcion normal desde pytest.
    """
    try:
        return get_run_logger()
    except MissingContextError:
        return logging.getLogger(__name__)


# =============================================================================
# Helpers puros — sin Prefect, sin MLflow. Se testean directo.
# =============================================================================
def particion_desde_etiqueta(etiqueta: str) -> Particion:
    """Convierte ``"2023-01"`` en ``Particion(2023, 1)``.

    Los parametros de un deployment tienen que ser serializables a JSON, asi que
    el flow recibe etiquetas (strings) y no dataclasses.

    Raises:
        ValueError: si la etiqueta no tiene la forma ``YYYY-MM`` o el mes esta
            fuera de rango. Falla temprano y con un mensaje que dice que se
            esperaba, en lugar de pedirle a la TLC un archivo inexistente.

    >>> particion_desde_etiqueta("2023-04")
    Particion(anio=2023, mes=4)
    """
    partes = etiqueta.strip().split("-")
    if len(partes) != 2 or not partes[0].isdigit() or not partes[1].isdigit():
        raise ValueError(f"Etiqueta de particion invalida: {etiqueta!r}. Se esperaba 'YYYY-MM'.")
    anio, mes = int(partes[0]), int(partes[1])
    if not 1 <= mes <= 12:
        raise ValueError(f"Mes fuera de rango en {etiqueta!r}: {mes}.")
    return Particion(anio, mes)


def siguiente_particion(particion: Particion) -> Particion:
    """Devuelve la particion mensual siguiente.

    Tiene test propio, incluido el salto de diciembre a enero: es donde este
    tipo de funcion se rompe siempre, y es una linea de codigo que nadie duda en
    escribir a mano y casi nadie prueba.

    >>> siguiente_particion(Particion(2023, 12))
    Particion(anio=2024, mes=1)
    """
    if particion.mes == 12:
        return Particion(particion.anio + 1, 1)
    return Particion(particion.anio, particion.mes + 1)


def nombre_cache(particiones: tuple[Particion, ...]) -> str:
    """Nombre estable del dataset preparado, derivado de sus particiones."""
    return "train-" + "_".join(p.etiqueta for p in particiones)


@dataclass(frozen=True)
class ModeloEntrenado:
    """Resultado del entrenamiento, sin metricas todavia.

    Se separa del calculo de metricas a proposito: `entrenar` produce el
    artefacto y `evaluar` lo juzga. Son dos responsabilidades y dos tasks.
    """

    run_id: str
    model_uri: str
    estimador: Any
    params: dict[str, Any] = field(default_factory=dict)


def _configurar_mlflow(experimento: str) -> None:
    """Configura MLflow. **Se llama desde dentro de las tasks, nunca al importar.**

    El `pipeline.py` anterior ejecutaba `setup_mlflow()` a nivel de modulo
    (linea 22): importarlo abria una conexion y creaba un experimento como
    efecto colateral. Eso vuelve el modulo intesteable —no se puede importar sin
    tener MLflow arriba— y hace que el orden de los imports cambie el
    comportamiento del programa.
    """
    import mlflow

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experimento)


def _url_ui_mlflow() -> str | None:
    """URL navegable del tracking server, o ``None`` si el backend no es HTTP.

    Se comprueba el esquema antes de construirla. El atajo habitual —
        ``get_tracking_uri().replace("sqlite:///", "http://localhost:5000/")`` —
        produce con un backend SQLite un `http://localhost:5000/mlflow.db`: un enlace
        roto dentro del artifact. Si no hay UI, lo correcto es no publicar enlace.
    """
    import mlflow

    uri = mlflow.get_tracking_uri()
    return uri if uri.startswith(("http://", "https://")) else None


def _modulo(ruta: str) -> Any | None:
    """Importa un modulo del paquete de forma **tardia**, o devuelve None.

    Se usa para `taxi.models.train` y `taxi.models.registry`. El import tardio
    tiene dos motivos: importar `taxi.flows.training` no deberia arrastrar
    xgboost ni MLflow, y el flow no queda acoplado al orden en que se implementan
    los modulos del paquete.
    """
    import importlib

    try:
        return importlib.import_module(ruta)
    except ImportError:
        return None


def _construir_estimador(params: dict[str, Any]) -> Any:
    """Construye el pipeline (features -> DictVectorizer -> XGBoost).

    Delega en `taxi.models.train.pipeline_xgboost(**params)`, que es la unica
    definicion del modelo del curso. El fallback local solo existe para que el
    flow sea ejecutable si ese modulo no esta disponible.

    El estimador recibe un **DataFrame** (sus primeros pasos derivan los
    diccionarios), no una lista de diccionarios: asi la signature del modelo
    registrado describe un DataFrame, que es lo que envian la API (S05) y el
    batch.
    """
    modulo = _modulo("taxi.models.train")
    if modulo is not None and hasattr(modulo, "pipeline_xgboost"):
        return modulo.pipeline_xgboost(**params)

    # Fallback: solo se llega aqui si `taxi.models.train` no se pudo importar
    # (por ejemplo, sin xgboost instalado). Construye el mismo pipeline en linea.
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer
    from xgboost import XGBRegressor

    return Pipeline(
        [
            ("dicts", FunctionTransformer(fc.a_diccionarios)),
            ("dv", DictVectorizer()),
            (
                "modelo",
                XGBRegressor(
                    objective="reg:squarederror",
                    random_state=SEMILLA,
                    n_jobs=-1,
                    tree_method="hist",
                    **{**PARAMS_FALLBACK, **params},
                ),
            ),
        ]
    )


def _ajustar(estimador: Any, df_train: pd.DataFrame, df_valid: pd.DataFrame) -> Any:
    """Ajusta el estimador, delegando en `taxi.models.train.ajustar` si existe.

    Esa funcion resuelve una sutileza que este flow no deberia reimplementar: el
    `eval_set` del early stopping de XGBoost necesita la matriz **ya
    transformada**, y transformarla con `fit_transform` seria leakage del
    conjunto de validacion al vocabulario del vectorizador.
    """
    modulo = _modulo("taxi.models.train")
    if modulo is not None and hasattr(modulo, "ajustar"):
        return modulo.ajustar(estimador, df_train, df_valid)

    # Fallback sin early stopping: sin `taxi.models.train.ajustar` no hay forma
    # de pasar el `eval_set` transformado, asi que se ajusta sobre train a secas.
    estimador.fit(df_train, df_train[fc.TARGET_REGRESION])
    return estimador


def calcular_metricas(y_real: pd.Series, y_pred: Any) -> dict[str, float]:
    """RMSE, MAE y R2.

    Se usa `root_mean_squared_error`. El parametro `squared` de
    `mean_squared_error` fue removido de scikit-learn, asi que la forma antigua de
    calcular el RMSE ya no funciona.
    """
    from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

    return {
        "rmse": float(root_mean_squared_error(y_real, y_pred)),
        "mae": float(mean_absolute_error(y_real, y_pred)),
        "r2": float(r2_score(y_real, y_pred)),
    }


# =============================================================================
# Tasks
# =============================================================================
@task(
    name="extraer",
    description="Descarga una particion mensual de la NYC TLC y verifica su hash.",
    retries=3,
    retry_delay_seconds=[10, 30, 60],
)
def extraer(particion: Particion) -> Path:
    """Descarga la particion y devuelve la ruta local del parquet.

    **Por que el backoff no es opcional.** Cuando el fallo es de red, la causa
    suele ser saturacion o rate limiting del otro lado. Reintentar de inmediato
    (`retry_delay_seconds=2`, como estaba en `retries.py`) agrega carga
    exactamente cuando el servicio esta peor, y los tres intentos se agotan
    dentro de la misma ventana de degradacion: es equivalente a no tener
    reintentos. Con `[10, 30, 60]` los intentos cubren ~100 segundos, que es la
    escala de un pico de red o de un despliegue del proveedor.

    La lista da control explicito por intento; `retry_delay_seconds=10` con
    `retry_jitter_factor` es la alternativa cuando hay muchas tasks en paralelo y
    conviene desincronizarlas para no producir un thundering herd.
    """
    logger = _log()
    logger.info("Extrayendo particion %s", particion.etiqueta)
    ruta = descargar_particion(particion)
    logger.info("Particion %s disponible en %s", particion.etiqueta, ruta)
    return ruta


@task(
    name="validar",
    description="Valida el contrato Pandera del parquet crudo.",
)
def validar(ruta: Path) -> dict[str, Any]:
    """Valida el contrato de datos en la **frontera** del pipeline.

    Se valida donde el dato entra, no donde se usa. El objetivo es que un cambio
    silencioso de los datos (unidades, rango, categoria nueva, descarga truncada)
    se convierta en un fallo ruidoso antes de gastar CPU en entrenar y antes de
    registrar un modelo con metricas plausibles calculadas sobre datos malos.

    Devuelve un resumen pequeno —no el DataFrame— porque este valor viaja como
    input de otras tasks y como resultado en la UI.

    Raises:
        pandera.errors.SchemaErrors: si el contrato no se cumple.
    """
    logger = _log()
    df = pd.read_parquet(ruta)
    dc.validar_crudos(df)
    resumen = {
        "archivo": ruta.name,
        "filas": len(df),
        "columnas": int(df.shape[1]),
    }
    logger.info("Contrato de crudos OK para %s: %d filas", ruta.name, resumen["filas"])
    return resumen


@task(
    name="preparar",
    description="Filtra, muestrea y deriva features de un conjunto de particiones.",
    cache_key_fn=task_input_hash,
    cache_expiration=VIGENCIA_CACHE,
    # Prefect lo activaria solo al ver `cache_key_fn`; se declara explicito
    # porque sin persistencia el cache no sobrevive entre corridas y la mejora
    # de tiempo que el taller pide medir no aparece.
    persist_result=True,
)
def preparar(particiones: tuple[Particion, ...]) -> pd.DataFrame:
    """Prepara el dataset de entrenamiento y lo deja en `data/processed/`.

    **Caching.** `cache_key_fn=task_input_hash` calcula la clave a partir de los
    inputs de la task. Si se la llama otra vez con las mismas particiones dentro
    de la ventana de `cache_expiration`, Prefect devuelve el resultado
    persistido y no vuelve a leer, filtrar ni muestrear.

    Diferencia con el caching automatico de Prefect 3: por defecto la politica es
    `DEFAULT` (inputs + codigo de la task + id del flow run), es decir el cache
    normalmente **no** se comparte entre corridas distintas del flow.
    `task_input_hash` depende solo de los inputs, asi que si se comparte — que es
    lo que queremos para no re-descargar datos inmutables. El precio es real: si
    cambias el cuerpo de la task sin cambiar los inputs, sigues sirviendo el
    resultado viejo. La alternativa moderna, mas segura, es
    ``cache_policy=INPUTS + TASK_SOURCE``, que invalida al cambiar el codigo.

    El `cachear()` final escribe el parquet procesado. Es una **escritura**, no
    un atajo de lectura: si tambien se leyera de ahi, habria dos caches y la
    medicion del taller no diria nada sobre ninguno de los dos.
    """
    logger = _log()
    logger.info(
        "Preparando %d particion(es): %s", len(particiones), [p.etiqueta for p in particiones]
    )
    df = preparar_particiones(particiones)
    ruta = cachear(df, nombre_cache(particiones))
    logger.info("Dataset preparado: %d filas -> %s", len(df), ruta)
    return df


@task(
    name="entrenar",
    description="Entrena el modelo y lo registra como run de MLflow.",
)
def entrenar(
    df_train: pd.DataFrame,
    df_valid: pd.DataFrame,
    params: dict[str, Any] | None = None,
    experimento: str = EXPERIMENTOS["pipeline"],
) -> ModeloEntrenado:
    """Entrena el estimador y lo loguea en MLflow con signature e input_example.

    Recibe tambien `df_valid` porque el early stopping necesita un `eval_set`:
    declarar `early_stopping_rounds` sin pasar datos de validacion es lo que
    hacia el pipeline anterior, donde ademas
    `early_stopping_rounds=50 > num_boost_round=30` volvia el mecanismo
    inoperante. El conjunto de validacion se usa para **parar**, no para medir el
    resultado final: eso es `evaluar`.

    La signature es lo que permite detectar train/serve skew antes de produccion:
    sin ella, servir un `float` donde el modelo espera un `int` falla en tiempo
    de inferencia y con un error opaco.
    """
    import mlflow
    from mlflow.models import infer_signature

    logger = _log()
    _configurar_mlflow(experimento)

    params_finales = dict(params or {})
    estimador = _construir_estimador(params_finales)

    logger.info("Entrenando con %d filas de train y %d de validacion", len(df_train), len(df_valid))

    with mlflow.start_run(run_name="s04-entrenamiento-orquestado") as run:
        _ajustar(estimador, df_train, df_valid)
        if params_finales:
            mlflow.log_params(params_finales)
        mlflow.set_tag("orquestador", "prefect")
        mlflow.set_tag("flow", "entrenamiento-taxi")
        mlflow.log_metric("filas_train", float(len(df_train)))

        ejemplo = df_train[fc.FEATURES].head(5)
        firma = infer_signature(ejemplo, estimador.predict(ejemplo))
        info = mlflow.sklearn.log_model(
            estimador,
            # `name=` es el parametro de MLflow 3. `artifact_path=` esta
            # deprecado y era lo que usaba `optimization.py:229`, ademas de
            # forma posicional, que es aun mas fragil.
            name="model",
            signature=firma,
            input_example=ejemplo,
            # El default de `mlflow.sklearn` paso a ser `skops`, que rechaza
            # tipos no confiables: un Pipeline con XGBRegressor adentro no se
            # puede cargar sin declararlos. cloudpickle funciona, y el costo es
            # explicito: deserializar ejecuta codigo, asi que solo se cargan
            # artefactos de un registry propio.
            serialization_format="cloudpickle",
        )
        # Sin try/except alrededor del logging, a proposito. Envolverlo degrada
        # el fallo a un warning: el pipeline termina "en verde" con un run sin
        # modelo, y el problema se descubre al desplegar.
        run_id = run.info.run_id

    logger.info("Modelo entrenado en el run %s (%s)", run_id, info.model_uri)
    return ModeloEntrenado(
        run_id=run_id,
        model_uri=info.model_uri,
        estimador=estimador,
        params=params_finales,
    )


@task(
    name="evaluar",
    description="Evalua el modelo en la particion de validacion.",
)
def evaluar(
    modelo: ModeloEntrenado,
    df_valid: pd.DataFrame,
    experimento: str = EXPERIMENTOS["pipeline"],
) -> dict[str, float]:
    """Calcula las metricas en validacion y las loguea en el run del modelo.

    Se evalua en `PARTICION_VALID`, nunca en `PARTICION_TEST`: el holdout de test
    es el juez del gate de promocion (S06) y usarlo aqui —donde se itera— lo
    contaminaria.
    """
    import mlflow

    logger = _log()
    _configurar_mlflow(experimento)

    x_valid = df_valid[fc.FEATURES]
    y_valid = df_valid[fc.TARGET_REGRESION]
    metricas = calcular_metricas(y_valid, modelo.estimador.predict(x_valid))
    metricas["filas_valid"] = float(len(df_valid))

    with mlflow.start_run(run_id=modelo.run_id):
        mlflow.log_metrics(metricas)

    logger.info(
        "Validacion: rmse=%.4f mae=%.4f r2=%.4f",
        metricas["rmse"],
        metricas["mae"],
        metricas["r2"],
    )
    return metricas


@task(
    name="registrar_candidato",
    description="Registra la version en el registry con el alias candidate.",
)
def registrar_candidato(
    modelo: ModeloEntrenado,
    metricas: dict[str, float],
    particiones_train: tuple[Particion, ...],
    nombre_modelo: str = MODELO_REGRESION,
    experimento: str = EXPERIMENTOS["pipeline"],
) -> str:
    """Registra el modelo y le pone el alias ``candidate``. **No promueve.**

    Lo que esta task hace y lo que deliberadamente no hace:

    - **Si**: crea la version, escribe tags con la evidencia (metricas,
      particiones, run de Prefect) y mueve el alias `candidate`.
    - **No**: mueve `champion` ni archiva versiones anteriores. Eso es el gate
      (S06) y necesita comparar contra el champion actual en el holdout fijo. El
      unico `validation_status` que se escribe es `pending`, y lo escribe
      `taxi.models.registry`: no debe existir una version en el registry con
      estado de validacion desconocido.

    Prohibida aqui, y en todo el curso, la API de stages de MLflow: el metodo que
    movia versiones entre `Staging` y `Production` y las URIs de la forma
    `models:/<nombre>/<stage>`. Los stages estan deprecados, y el alias expresa
    mejor la misma idea: una referencia mutable a "el modelo que sirve",
    desacoplada del numero de version.

    Returns:
        La version registrada, como string.
    """
    import mlflow
    from mlflow import MlflowClient
    from prefect.runtime import flow_run

    logger = _log()
    _configurar_mlflow(experimento)

    # La semantica de "registrar un candidato" (crear la version, alias
    # `candidate`, `validation_status=pending`) vive en taxi.models.registry.
    # Duplicarla aqui garantizaria que las dos copias se desincronicen.
    registry = _modulo("taxi.models.registry")
    if registry is not None and hasattr(registry, "registrar_candidato"):
        version_registrada = registry.registrar_candidato(
            modelo.model_uri,
            nombre_modelo,
            descripcion="Candidato producido por el flow de Prefect (Sesion 4).",
        )
    else:
        # Fallback: registra sin la descripcion ni las validaciones que anade
        # `taxi.models.registry.registrar_candidato`.
        version_registrada = mlflow.register_model(modelo.model_uri, nombre_modelo)

    version = str(version_registrada.version)
    cliente = MlflowClient()

    tags = {
        "rmse_valid": f"{metricas['rmse']:.4f}",
        "mae_valid": f"{metricas['mae']:.4f}",
        "particiones_train": ",".join(p.etiqueta for p in particiones_train),
        "prefect_flow_run_id": str(flow_run.id or "sin-flow-run"),
        "registrado_por": "taxi.flows.training",
    }
    for clave, valor in tags.items():
        cliente.set_model_version_tag(nombre_modelo, version, clave, valor)

    # Idempotente: por el camino delegado el alias ya quedo puesto. Se repite
    # para que el camino de fallback tambien lo garantice.
    cliente.set_registered_model_alias(nombre_modelo, ALIAS_CANDIDATO, version)
    logger.info(
        "Registrado %s v%s con alias @%s. NO se promueve a champion: "
        "la promocion es un gate y el gate vive en CI (Sesion 6).",
        nombre_modelo,
        version,
        ALIAS_CANDIDATO,
    )
    return version


@task(name="publicar_reporte", description="Publica los artifacts de la corrida.")
def publicar_reporte(
    metricas: dict[str, float],
    resumenes_datos: list[dict[str, Any]],
    modelo: ModeloEntrenado,
    version: str | None,
    nombre_modelo: str = MODELO_REGRESION,
) -> None:
    """Crea los artifacts de Prefect de la corrida.

    El reporte vive **junto a la corrida** que lo produjo. Un HTML en el disco
    del instructor no es un reporte: no se sabe de que ejecucion salio.
    """
    filas_totales = sum(int(r["filas"]) for r in resumenes_datos)
    tabla = [
        {"metrica": "rmse_valid", "valor": round(metricas["rmse"], 4), "unidad": "minutos"},
        {"metrica": "mae_valid", "valor": round(metricas["mae"], 4), "unidad": "minutos"},
        {"metrica": "r2_valid", "valor": round(metricas["r2"], 4), "unidad": "adimensional"},
        {"metrica": "filas_validacion", "valor": int(metricas["filas_valid"]), "unidad": "filas"},
        {"metrica": "filas_crudas_leidas", "valor": filas_totales, "unidad": "filas"},
    ]
    create_table_artifact(
        key="metricas-corrida",
        table=tabla,
        description="Metricas de validacion de esta corrida del flow de entrenamiento.",
    )

    url_ui = _url_ui_mlflow()
    linea_mlflow = (
        f"- **MLflow**: [{modelo.run_id}]({url_ui})"
        if url_ui
        else f"- **MLflow run**: `{modelo.run_id}` (backend sin UI HTTP)"
    )
    linea_version = (
        f"- **Version registrada**: `{nombre_modelo}` v{version} con alias `@{ALIAS_CANDIDATO}`"
        if version
        else "- **Version registrada**: ninguna (se corrio con `registrar=False`)"
    )

    markdown = f"""# Corrida del flow de entrenamiento

{linea_mlflow}
{linea_version}
- **Generado**: {datetime.now(UTC).isoformat(timespec="seconds")}

## Metricas en validacion

| Metrica | Valor |
|---|---|
| RMSE | {metricas["rmse"]:.4f} min |
| MAE | {metricas["mae"]:.4f} min |
| R2 | {metricas["r2"]:.4f} |

## Estado de promocion

El candidato **no** fue promovido. La promocion a `@champion` es una decision del
gate de CI (Sesion 6), que compara este candidato contra el champion actual en el
holdout fijo y exige, ademas, que los tests de datos pasen.

## Hiperparametros

{chr(10).join(f"- `{clave}`: {valor}" for clave, valor in sorted(modelo.params.items()))}
"""
    create_markdown_artifact(
        key="resumen-entrenamiento",
        markdown=markdown,
        description="Resumen de la corrida: metricas, version registrada y estado de promocion.",
    )


# =============================================================================
# Flow
# =============================================================================
@flow(
    name="entrenamiento-taxi",
    description=(
        "Entrena el modelo de duracion de viajes y registra el candidato. "
        "No promueve: la promocion es un gate en CI."
    ),
    log_prints=True,
)
def entrenamiento_flow(
    particiones_train: list[str] | None = None,
    particion_valid: str | None = None,
    params_modelo: dict[str, Any] | None = None,
    experimento: str = EXPERIMENTOS["pipeline"],
    nombre_modelo: str = MODELO_REGRESION,
    registrar: bool = True,
) -> dict[str, Any]:
    """Pipeline de entrenamiento: extraer -> validar -> preparar -> entrenar -> evaluar -> registrar.

    Args:
        particiones_train: etiquetas ``YYYY-MM`` de entrenamiento. Por defecto,
            `PARTICIONES_TRAIN` de `config.py`.
        particion_valid: etiqueta de validacion. Por defecto, la particion
            siguiente a la ultima de entrenamiento.
        params_modelo: sobrescribe `PARAMS_POR_DEFECTO`.
        experimento: experimento de MLflow donde escribir.
        nombre_modelo: nombre del modelo registrado.
        registrar: si es False entrena y evalua sin tocar el registry. Util para
            probar el pipeline en clase sin ensuciar el registry con versiones.

    Returns:
        Dict con `run_id`, `model_version`, `metricas` y las particiones usadas.
        El estado final del flow se deriva de este valor de retorno (o de la
        excepcion): en Prefect 3 ya no se deduce de los estados de las tasks.
    """
    logger = _log()

    etiquetas_train = particiones_train or [p.etiqueta for p in PARTICIONES_TRAIN]
    particiones = tuple(particion_desde_etiqueta(e) for e in etiquetas_train)
    valid = (
        particion_desde_etiqueta(particion_valid)
        if particion_valid
        else siguiente_particion(particiones[-1])
    )
    if valid != PARTICION_VALID:
        logger.info(
            "Validando con %s (config.PARTICION_VALID es %s)", valid.etiqueta, PARTICION_VALID
        )

    # 1-2. Extraer y validar en la frontera. Falla antes de gastar CPU.
    resumenes: list[dict[str, Any]] = []
    for particion in (*particiones, valid):
        ruta = extraer(particion)
        resumenes.append(validar(ruta))

    # 3. Preparar (con cache).
    df_train = preparar(particiones)
    df_valid = preparar((valid,))

    # 4-5. Entrenar y evaluar.
    modelo = entrenar(df_train, df_valid, params_modelo, experimento)
    metricas = evaluar(modelo, df_valid, experimento)

    # 6. Registrar el candidato. Sin promover.
    version = (
        registrar_candidato(modelo, metricas, particiones, nombre_modelo, experimento)
        if registrar
        else None
    )

    publicar_reporte(metricas, resumenes, modelo, version, nombre_modelo)

    return {
        "run_id": modelo.run_id,
        "model_uri": modelo.model_uri,
        "model_version": version,
        "alias": ALIAS_CANDIDATO if version else None,
        "promovido": False,
        "metricas": metricas,
        "particiones_train": [p.etiqueta for p in particiones],
        "particion_valid": valid.etiqueta,
    }


if __name__ == "__main__":
    resultado = entrenamiento_flow()
    print(f"run_id={resultado['run_id']} version={resultado['model_version']}")
    print(f"rmse_valid={resultado['metricas']['rmse']:.4f}")
