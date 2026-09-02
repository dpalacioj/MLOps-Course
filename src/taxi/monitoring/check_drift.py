"""Check de drift accionable: referencia vs produccion, con exit code.

Problema que resuelve
---------------------
El monitoreo que se queda a medias produce **un HTML que nadie abre**, y peor si
lo produce sobre datos inventados —un `numpy.random.exponential(3.0)` contra
`exponential(5.5)`, por ejemplo—: el drift se detecta siempre, el resultado nunca
es ambiguo y no hay nada que decidir. Un check que siempre dice "drift" no ensena
a monitorear; ensena a confiar en una salida verde.

Este modulo cambia tres cosas:

1. **Datos reales.** La referencia son las particiones de entrenamiento
   (2023-01..03) y la "produccion" son 2023-07 (estacionalidad de verano) y
   2024-01 (un ano despues: tarifas y patrones distintos). El drift es real y a
   veces es **ambiguo**, que es la situacion profesional que hay que aprender a
   resolver.
2. **Exit code.** Si la fraccion de columnas con drift supera el umbral, el
   proceso termina con codigo distinto de cero. Eso lo convierte en un paso de
   pipeline: un job programado que falla abre una alerta, mientras que un HTML en
   una carpeta no le llega a nadie.
3. **Degradacion elegante.** Si `evidently` no esta instalado o su API cambio, el
   check corre con `taxi.monitoring.estadistico` (scipy) y lo dice en la salida.
   Se pierde el HTML, no la senal. Un monitoreo que se apaga cuando una
   dependencia opcional falla es peor que no tenerlo, porque nadie nota la
   ausencia.

Uso
---
    taxi drift                                   # interactivo
    taxi drift --particion 2024-01
    python -m taxi.monitoring.check_drift        # el que corre en CI
    python -m taxi.monitoring.check_drift --umbral 0.2 --sin-evidently

Exit codes
----------
- ``0``: la fraccion de columnas con drift esta en o por debajo del umbral.
- ``1``: se supero el umbral. Hay que revisar (no necesariamente reentrenar).
- ``2``: no se pudo evaluar (sin datos, sin columnas). Un fallo de medicion no se
  reporta como "todo bien"; se distingue del veredicto negativo a proposito.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import click
import pandas as pd

from taxi.config import (
    PARTICIONES_PRODUCCION,
    PARTICIONES_TRAIN,
    REPORTS_DIR,
    UMBRAL_DRIFT_COLUMNAS,
    Particion,
)
from taxi.features import contract as fc
from taxi.monitoring import reporte
from taxi.monitoring.estadistico import (
    Criterio,
    ResultadoDrift,
    detectar_drift,
)

logger = logging.getLogger(__name__)

EXIT_OK: int = 0
EXIT_DRIFT: int = 1
EXIT_NO_EVALUABLE: int = 2

#: Columnas que se vigilan. Son las features del contrato mas el target.
#:
#: El target se incluye a proposito y con una advertencia: en produccion **no
#: esta disponible** hasta que llegan las etiquetas. Aqui se puede medir porque
#: las particiones de "produccion" son historicas y por lo tanto ya tienen
#: labels; en un sistema real esta parte del reporte solo existe despues del
#: label lag. Confundir las dos situaciones es el error que hace creer que se
#: puede detectar concept drift en tiempo real.
NUMERICAS: tuple[str, ...] = (*fc.FEATURES_NUMERICAS, fc.TARGET_REGRESION)
CATEGORICAS: tuple[str, ...] = tuple(fc.FEATURES_CATEGORICAS)

#: Nombre del experimento de MLflow donde se acumulan las corridas del check.
#: No esta en `config.EXPERIMENTOS` porque el logging a MLflow es opcional aqui;
#: si el curso decide hacerlo obligatorio, se mueve alla.
EXPERIMENTO_MONITOREO: str = "s07-monitoreo"


# =============================================================================
# Resultado
# =============================================================================
@dataclass(frozen=True)
class ResultadoCheck:
    """Todo lo que el check produce: veredicto, artefactos y trazabilidad."""

    drift: ResultadoDrift
    referencia: tuple[str, ...]
    actual: tuple[str, ...]
    filas_referencia: int
    filas_actual: int
    ruta_html: Path | None = None
    ruta_json: Path | None = None
    degradado: bool = False
    motivo_degradacion: str = ""

    @property
    def codigo_salida(self) -> int:
        """Exit code del proceso. Es el contrato con el CI."""
        if not self.drift.columnas:
            return EXIT_NO_EVALUABLE
        return EXIT_DRIFT if self.drift.hay_drift else EXIT_OK

    def metadatos(self) -> dict[str, Any]:
        return {
            "referencia": list(self.referencia),
            "actual": list(self.actual),
            "filas_referencia": self.filas_referencia,
            "filas_actual": self.filas_actual,
            "reporte_html": self.ruta_html.name if self.ruta_html else None,
            "degradado": self.degradado,
            "motivo_degradacion": self.motivo_degradacion,
            "codigo_salida": self.codigo_salida,
        }


# =============================================================================
# Datos
# =============================================================================
def particion_desde_etiqueta(etiqueta: str) -> Particion:
    """Convierte ``"2024-01"`` en ``Particion(2024, 1)``.

    `taxi.flows.training` tiene la misma funcion. No se importa desde alla a
    proposito: ese modulo importa Prefect al nivel de modulo, y el check de drift
    tiene que poder correr en un contenedor de CI sin orquestador instalado.
    Duplicar cuatro lineas de parsing es un precio menor que acoplar el monitoreo
    a una dependencia que no usa.
    """
    partes = etiqueta.strip().split("-")
    if len(partes) != 2 or not partes[0].isdigit() or not partes[1].isdigit():
        raise ValueError(f"Etiqueta de particion invalida: {etiqueta!r}. Se esperaba 'YYYY-MM'.")
    anio, mes = int(partes[0]), int(partes[1])
    if not 1 <= mes <= 12:
        raise ValueError(f"Mes fuera de rango en {etiqueta!r}: {mes}.")
    return Particion(anio, mes)


def _particiones(texto: str | None, defecto: Sequence[Particion]) -> tuple[Particion, ...]:
    """Parsea ``"2023-07,2024-01"`` o devuelve el valor por defecto del curso."""
    if not texto:
        return tuple(defecto)
    return tuple(particion_desde_etiqueta(p) for p in texto.split(",") if p.strip())


def cargar(particiones: Sequence[Particion], *, usar_cache: bool = True) -> pd.DataFrame:
    """Carga y concatena particiones preparadas, desde cache si esta disponible.

    Import diferido de `taxi.models.train`: ese modulo arrastra MLflow, Optuna y
    XGBoost, y el check tiene que poder importarse (y testearse) sin ellos.
    """
    from taxi.models import train

    return train.cargar_split(list(particiones), usar_cache=usar_cache)


# =============================================================================
# Motor Evidently
# =============================================================================
def _importar_evidently() -> Any:
    """Importa la API 0.7 de Evidently o devuelve None con el motivo en el log."""
    try:
        from evidently import DataDefinition, Dataset, Report
        from evidently.presets import DataDriftPreset, DataSummaryPreset
    except ImportError as exc:  # pragma: no cover - depende del entorno
        logger.warning("Evidently no disponible (%s); se usa el motor estadistico", exc)
        return None
    return {
        "DataDefinition": DataDefinition,
        "Dataset": Dataset,
        "Report": Report,
        "DataDriftPreset": DataDriftPreset,
        "DataSummaryPreset": DataSummaryPreset,
    }


def reporte_evidently(
    referencia: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    salida: Path,
    umbral_columnas: float,
    numericas: Sequence[str] = NUMERICAS,
    categoricas: Sequence[str] = CATEGORICAS,
) -> tuple[ResultadoDrift, Path]:
    """Corre el DataDriftPreset de Evidently 0.7 y devuelve el veredicto traducido.

    API vigente (verificada contra 0.7.21). Los tres cambios que rompen el
    material viejo:

    - ``Report`` y ``DataDefinition`` se importan de ``evidently``, no de
      ``evidently.report`` ni ``evidently.metric_preset`` (esos modulos ya no
      existen);
    - ``ColumnMapping`` fue reemplazado por ``DataDefinition``, y los datos se
      envuelven en ``Dataset.from_pandas(df, data_definition=...)``;
    - ``report.run(current, reference)`` recibe **primero el actual** —el orden es
      el inverso del de la API vieja, que usaba argumentos con nombre— y devuelve
      un ``Snapshot`` con ``.save_html()`` y ``.dict()`` (antes ``as_dict()``).

    ``include_tests=True`` es lo que sustituye al viejo ``TestSuite``: ya no hay
    un objeto separado, los tests viajan dentro del Report.

    ADVERTENCIA sobre los umbrales
    ------------------------------
    Este motor **no** usa ``estadistico.UMBRALES_POR_FEATURE``. Evidently elige su
    propio metodo por columna (con 0.7 y tamanos medios: Wasserstein normalizada
    para numericas, Jensen-Shannon para categoricas) y aplica su propio umbral
    (0.1 por defecto). No se le inyectan los umbrales del curso porque **serian
    umbrales de otro estadistico**: los del curso estan calibrados contra la linea
    base nula del KS y de la V de Cramer, y reutilizarlos sobre una distancia
    distinta seria exactamente la sloppiness que el ADR 003 critica.

    Consecuencia practica, y es una leccion sobre comprar en lugar de construir:
    al delegar la deteccion se heredan las decisiones estadisticas del proveedor.
    Si se quiere una sola politica de umbrales, hay dos caminos honestos: usar el
    motor propio (``--sin-evidently``), o forzar
    ``DataDriftPreset(num_method="ks", cat_method="chisquare",
    per_column_threshold=...)`` y **recalibrar** sobre esos estadisticos.
    """
    # Se validan las entradas ANTES de importar la dependencia opcional. Dos
    # motivos: el mensaje de error nombra el problema real (falta una columna del
    # contrato) en lugar del ZeroDivisionError que lanza Evidently al calcular la
    # fraccion sobre cero columnas; y no se paga el import de una libreria pesada
    # para descubrir que no habia nada que comparar.
    columnas = [c for c in (*numericas, *categoricas) if c in referencia.columns]
    if not columnas:
        raise ValueError(
            "ninguna columna del contrato esta presente en la referencia: "
            f"se esperaban {[*numericas, *categoricas]}, hay {sorted(referencia.columns)}"
        )

    api = _importar_evidently()
    if api is None:
        raise ImportError("evidently no esta instalado")

    esquema = api["DataDefinition"](
        numerical_columns=[c for c in numericas if c in columnas],
        categorical_columns=[c for c in categoricas if c in columnas],
    )
    dataset_ref = api["Dataset"].from_pandas(referencia[columnas], data_definition=esquema)
    dataset_act = api["Dataset"].from_pandas(actual[columnas], data_definition=esquema)

    report = api["Report"](
        [api["DataDriftPreset"](), api["DataSummaryPreset"]()],
        include_tests=True,
    )
    evaluacion = report.run(dataset_act, dataset_ref)

    salida.parent.mkdir(parents=True, exist_ok=True)
    evaluacion.save_html(str(salida))
    logger.info("Reporte de Evidently en %s", salida)

    bruto = evaluacion.dict()
    resultado = reporte.desde_evidently(
        bruto,
        columnas_numericas=[c for c in numericas if c in columnas],
        columnas_categoricas=[c for c in categoricas if c in columnas],
        umbral_columnas=umbral_columnas,
    )

    # Contraste con la metrica agregada de Evidently. Si difieren, el motivo casi
    # siempre es que el conjunto de columnas no coincide; verlo aqui ahorra
    # abrir el HTML.
    cuenta, fraccion = reporte.columnas_con_drift_segun_evidently(bruto)
    if fraccion is not None and abs(fraccion - resultado.fraccion_con_drift) > 1e-9:
        logger.info(
            "Evidently reporta %s columnas con drift (fraccion %.3f); el check calcula %.3f "
            "sobre %d columnas del contrato",
            cuenta,
            fraccion,
            resultado.fraccion_con_drift,
            len(resultado.columnas),
        )
    return resultado, salida


# =============================================================================
# Tracking opcional
# =============================================================================
def loguear_en_mlflow(
    resultado: ResultadoCheck, *, experimento: str = EXPERIMENTO_MONITOREO
) -> str | None:
    """Loguea metricas y artefactos del check en MLflow, si hay tracking.

    Tolerante a fallo **y acotado en el tiempo**, que son dos requisitos distintos
    y los dos importan:

    - *tolerante*: el valor del check es el exit code, y perder el tracking no
      debe convertir una senal correcta en un pipeline rojo;
    - *acotado*: sin `registry.fallar_rapido`, mlflow reintenta 7 veces con
      backoff exponencial y 120 s de timeout. Con el servidor apagado —el caso
      normal en el portatil de un estudiante y en un runner de CI— el check queda
      colgado varios minutos antes de "degradar con elegancia". Un fallback que
      tarda cuatro minutos en activarse no es un fallback. Se reutiliza el
      helper de `taxi.models.registry`, que ya resuelve esto para la model card y
      para el gate.

    Returns:
        El ``run_id`` si se logueo, ``None`` si no habia tracking disponible.
    """
    try:
        import mlflow

        from taxi.config import MLFLOW_TRACKING_URI
        from taxi.models.registry import fallar_rapido

        with fallar_rapido():
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            mlflow.set_experiment(experimento)
            etiqueta = "_".join(resultado.actual) or "sin-particion"
            with mlflow.start_run(run_name=f"drift-{etiqueta}") as run:
                mlflow.log_params(
                    {
                        "referencia": ",".join(resultado.referencia),
                        "actual": ",".join(resultado.actual),
                        "motor": resultado.drift.motor,
                        "criterio": resultado.drift.criterio,
                        "umbral_columnas": resultado.drift.umbral_columnas,
                    }
                )
                mlflow.log_metrics(reporte.metricas_para_tracking(resultado.drift))
                for ruta in (resultado.ruta_html, resultado.ruta_json):
                    if ruta is not None and ruta.exists():
                        mlflow.log_artifact(str(ruta), artifact_path="monitoreo")
                return str(run.info.run_id)
    except Exception as exc:
        logger.info("No se logueo en MLflow (%s: %s)", type(exc).__name__, exc)
        return None


# =============================================================================
# Orquestacion del check
# =============================================================================
def nombre_reporte(referencia: Sequence[Particion], actual: Sequence[Particion]) -> str:
    """Nombre estable y autodescriptivo del reporte.

    Que el nombre lleve las particiones comparadas evita el problema de un
    `drift_report.html` fijo: se sobreescribe en cada corrida y deja de poder
    saberse que comparaba.
    """
    ref = "_".join(p.etiqueta for p in referencia)
    act = "_".join(p.etiqueta for p in actual)
    return f"drift_{ref}__vs__{act}"


def ejecutar_check(
    *,
    referencia: Sequence[Particion] = PARTICIONES_TRAIN,
    actual: Sequence[Particion] = PARTICIONES_PRODUCCION,
    umbral: float = UMBRAL_DRIFT_COLUMNAS,
    salida: Path | None = None,
    usar_evidently: bool = True,
    criterio: Criterio = "efecto",
    usar_cache: bool = True,
    mlflow_tracking: bool = True,
    datos: Mapping[str, pd.DataFrame] | None = None,
) -> ResultadoCheck:
    """Ejecuta el check completo y devuelve el resultado. **No** llama a sys.exit.

    Separar el calculo (esta funcion) de la terminacion del proceso (``ejecutar``)
    es lo que permite testearlo sin capturar SystemExit y reutilizarlo desde un
    flow o desde un notebook.

    Args:
        referencia: particiones de referencia (por defecto, las de train).
        actual: particiones de produccion simulada.
        umbral: fraccion de columnas con drift que dispara la alerta.
        salida: directorio de los artefactos. Por defecto ``REPORTS_DIR``.
        usar_evidently: ``False`` fuerza el motor de scipy (util para comparar los
            dos motores sobre los mismos datos, y para el CI sin la dependencia).
        criterio: criterio del motor estadistico. Ver `estadistico.CRITERIOS`.
        usar_cache: usa ``data/processed/`` si ya esta materializado.
        mlflow_tracking: intenta loguear en MLflow. Nunca falla el check.
        datos: inyeccion de dataframes ya cargados,
            ``{"referencia": df, "actual": df}``. Es lo que usan los tests para
            no depender de la red.

    Returns:
        ``ResultadoCheck``.
    """
    directorio = salida or REPORTS_DIR
    if datos is not None:
        df_ref = datos["referencia"]
        df_act = datos["actual"]
    else:
        df_ref = cargar(referencia, usar_cache=usar_cache)
        df_act = cargar(actual, usar_cache=usar_cache)

    logger.info(
        "Referencia %s (%d filas) vs actual %s (%d filas)",
        [p.etiqueta for p in referencia],
        len(df_ref),
        [p.etiqueta for p in actual],
        len(df_act),
    )

    base = nombre_reporte(referencia, actual)
    ruta_html: Path | None = None
    degradado = False
    motivo = ""
    resultado_drift: ResultadoDrift | None = None

    if usar_evidently:
        try:
            resultado_drift, ruta_html = reporte_evidently(
                df_ref,
                df_act,
                salida=directorio / f"{base}.html",
                umbral_columnas=umbral,
            )
        except Exception as exc:
            degradado = True
            motivo = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Evidently fallo (%s). Se continua con el motor estadistico (scipy): "
                "se pierde el HTML, no la deteccion.",
                motivo,
            )
            ruta_html = None

    if resultado_drift is None:
        if not degradado and usar_evidently:
            degradado = True
            motivo = "evidently no disponible"
        resultado_drift = detectar_drift(
            df_ref,
            df_act,
            columnas_numericas=[c for c in NUMERICAS if c in df_ref.columns],
            columnas_categoricas=[c for c in CATEGORICAS if c in df_ref.columns],
            criterio=criterio,
            umbral_columnas=umbral,
        )

    resultado = ResultadoCheck(
        drift=resultado_drift,
        referencia=tuple(p.etiqueta for p in referencia),
        actual=tuple(p.etiqueta for p in actual),
        filas_referencia=len(df_ref),
        filas_actual=len(df_act),
        ruta_html=ruta_html,
        degradado=degradado,
        motivo_degradacion=motivo,
    )

    # El JSON se escribe despues de construir el resultado porque sus metadatos
    # incluyen el exit code, que es una propiedad del resultado completo.
    ruta_json = reporte.a_json(
        resultado.drift,
        directorio / f"{base}.json",
        metadatos=resultado.metadatos(),
    )
    resultado = replace(resultado, ruta_json=ruta_json)

    if mlflow_tracking:
        loguear_en_mlflow(resultado)
    return resultado


def formatear(resultado: ResultadoCheck) -> str:
    """Salida de consola del check, con la trazabilidad arriba."""
    cabecera = [
        f"Referencia: {', '.join(resultado.referencia)} ({resultado.filas_referencia:,} filas)",
        f"Actual:     {', '.join(resultado.actual)} ({resultado.filas_actual:,} filas)",
    ]
    if resultado.degradado:
        cabecera.append(
            f"MODO DEGRADADO: {resultado.motivo_degradacion}. "
            "Deteccion con scipy; no se genero el HTML de Evidently."
        )
    if resultado.drift.motor == "evidently":
        # Se dice de donde vienen los umbrales de la tabla. Sin esta linea, la
        # columna "umbral" se confunde con UMBRALES_POR_FEATURE y el estudiante
        # concluye que su calibracion se aplico cuando no se aplico.
        cabecera.append(
            "Umbrales por columna: los de Evidently (metodo y umbral propios). "
            "Los umbrales calibrados del curso los aplica el motor propio: --sin-evidently."
        )
    if resultado.ruta_html:
        cabecera.append(f"Reporte HTML: {resultado.ruta_html}")
    if resultado.ruta_json:
        cabecera.append(f"Resultado JSON: {resultado.ruta_json}")
    return "\n".join([*cabecera, "", reporte.resumen(resultado.drift)])


# =============================================================================
# CLI
# =============================================================================
@click.command("drift")
@click.option(
    "--referencia",
    default=None,
    help="Particiones de referencia separadas por coma. Por defecto, las de train.",
)
@click.option(
    "--actual",
    default=None,
    help="Particiones de produccion a evaluar. Por defecto, PARTICIONES_PRODUCCION.",
)
@click.option(
    "--particion",
    default=None,
    help="Alias de --actual con una sola particion. Lo usa `taxi drift --particion`.",
)
@click.option(
    "--umbral",
    type=float,
    default=UMBRAL_DRIFT_COLUMNAS,
    show_default=True,
    help="Fraccion de columnas con drift que dispara la alerta (y el exit code 1).",
)
@click.option(
    "--salida",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help="Directorio de los artefactos. Por defecto, reports/.",
)
@click.option(
    "--sin-evidently",
    is_flag=True,
    help="Fuerza el motor de scipy. Util para comparar los dos motores.",
)
@click.option(
    "--criterio",
    type=click.Choice(["efecto", "p_valor", "psi"]),
    default="efecto",
    show_default=True,
    help="Criterio del motor estadistico. 'p_valor' es el criterio MALO, para demostrarlo.",
)
@click.option("--sin-mlflow", is_flag=True, help="No intenta loguear en MLflow.")
@click.option("--no-cache", is_flag=True, help="Re-prepara los datos en lugar de usar el cache.")
@click.option("--verbose", "-v", is_flag=True)
def ejecutar(
    referencia: str | None,
    actual: str | None,
    particion: str | None,
    umbral: float,
    salida: Path | None,
    sin_evidently: bool,
    criterio: str,
    sin_mlflow: bool,
    no_cache: bool,
    verbose: bool,
) -> None:
    """Compara referencia contra produccion simulada y falla si hay drift.

    Exit code 0 sin alerta, 1 con alerta, 2 si no se pudo evaluar.
    """
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)-8s %(name)s: %(message)s",
    )
    resultado = ejecutar_check(
        referencia=_particiones(referencia, PARTICIONES_TRAIN),
        actual=_particiones(particion or actual, PARTICIONES_PRODUCCION),
        umbral=umbral,
        salida=salida,
        usar_evidently=not sin_evidently,
        criterio=criterio,  # type: ignore[arg-type]
        usar_cache=not no_cache,
        mlflow_tracking=not sin_mlflow,
    )
    click.echo(formatear(resultado))

    # Se usa sys.exit y no ctx.exit a proposito. `taxi drift` invoca este comando
    # con `standalone_mode=False`, y en ese modo click **captura** la excepcion
    # Exit que lanza ctx.exit y devuelve el codigo en lugar de propagarlo: el
    # proceso terminaria en 0 y el CI daria por bueno un dataset con drift.
    # SystemExit atraviesa las dos rutas de invocacion.
    codigo = resultado.codigo_salida
    if codigo != EXIT_OK:
        sys.exit(codigo)


if __name__ == "__main__":
    ejecutar()
