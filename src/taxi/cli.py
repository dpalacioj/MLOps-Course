"""Interfaz de linea de comandos del curso: `taxi <subcomando>`.

Problema que resuelve
---------------------
El repo anterior se operaba con una coleccion de scripts sueltos que se invocaban
de formas distintas (`python 02-.../train.py`, `python -m src.pipeline`, celdas
de notebook) y cada uno resolvia por su cuenta rutas, puerto de MLflow y nombres
de experimento. El resultado previsible: los pasos funcionaban aislados y no
encadenados, y en clase se perdian veinte minutos averiguando desde que
directorio habia que ejecutar cada cosa.

Un unico punto de entrada arregla tres cosas a la vez:

1. **Una sola forma de correr el sistema.** `taxi data`, `taxi train`,
   `taxi promote`... El Makefile y el CI llaman exactamente a estos comandos, asi
   que "funciona en mi maquina" y "funciona en CI" significan lo mismo.
2. **La configuracion se resuelve una vez** (`taxi.config`), no en cada script.
3. **Se ve el flujo completo** con `taxi --help`: el ciclo de vida del sistema es
   la lista de subcomandos, en orden.

Este modulo es deliberadamente delgado. La logica vive en `taxi.models` y en
`scripts/`; aqui solo hay parsing de argumentos y presentacion.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import click

from taxi import config

logger = logging.getLogger(__name__)

DIR_SCRIPTS = config.PROJECT_ROOT / "scripts"


def _configurar_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)-8s %(name)s: %(message)s",
    )


def _cargar_script(nombre: str) -> ModuleType:
    """Importa un modulo de ``scripts/`` por ruta.

    Por que asi y no con un import normal: ``scripts/`` no es un paquete
    instalable —es material del repositorio que los estudiantes abren y leen— y
    convertirlo en uno solo para que el CLI lo importe agregaria una capa que no
    aporta nada. La alternativa (duplicar el gate aqui y en el script) es peor:
    dos implementaciones de la politica de promocion se desincronizan, y ese
    tipo de duplicacion es justo lo que este rediseno elimina.

    Tampoco se manipula ``sys.path``: agregarle directorios contamina el path
    del proceso y cambia el comportamiento de imports posteriores, incluidos los
    de librerias de terceros.
    """
    ruta = DIR_SCRIPTS / f"{nombre}.py"
    if not ruta.is_file():
        raise click.ClickException(
            f"No se encontro {ruta}. Este comando necesita el repositorio "
            "completo; ejecutalo desde un checkout, no desde un wheel instalado."
        )
    spec = importlib.util.spec_from_file_location(f"taxi_scripts_{nombre}", ruta)
    if spec is None or spec.loader is None:
        raise click.ClickException(f"No se pudo cargar {ruta}")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="mlops-curso", prog_name="taxi")
def cli() -> None:
    """Curso de MLOps — caso guia NYC Green Taxi.

    Ciclo de vida completo, en orden:

    \b
      taxi data        descarga, valida y cachea las particiones fijas
      taxi train       entrena y loguea en MLflow (baseline, comparacion o HPO)
      taxi promote     gate: decide si el candidato reemplaza al @champion
      taxi model-card  genera docs/model-card.md desde el registry
      taxi drift       compara referencia vs produccion simulada
    """


# =============================================================================
# data
# =============================================================================
@cli.command("data")
@click.option("--forzar", is_flag=True, help="Ignora el cache y re-prepara todo.")
@click.option("--verbose", "-v", is_flag=True)
def comando_data(forzar: bool, verbose: bool) -> None:
    """Descarga, valida y cachea las particiones del caso guia.

    Requiere red la primera vez. Despues todo sale del cache en
    data/processed/.
    """
    _configurar_logging(verbose)
    from taxi.models import train

    filas = train.preparar_datos(usar_cache=not forzar)
    click.echo("Particiones preparadas:")
    for etiqueta, cantidad in filas.items():
        rol = _rol_de_particion(etiqueta)
        click.echo(f"  {etiqueta}  {cantidad:>8,} filas   {rol}")
    click.secho(f"Total: {sum(filas.values()):,} filas", fg="green")


def _rol_de_particion(etiqueta: str) -> str:
    """Etiqueta legible del rol de cada particion, para que no haya que ir al config."""
    if etiqueta in {p.etiqueta for p in config.PARTICIONES_TRAIN}:
        return "train"
    if etiqueta == config.PARTICION_VALID.etiqueta:
        return "valid (seleccion de hiperparametros)"
    if etiqueta == config.PARTICION_TEST.etiqueta:
        return "holdout (juez del gate; NO se usa para tunear)"
    return "produccion simulada (monitoreo)"


# =============================================================================
# train
# =============================================================================
@cli.command("train")
@click.option(
    "--modelo",
    type=click.Choice(["media", "lineal", "random_forest", "xgboost"]),
    default="lineal",
    show_default=True,
    help="Modelo a entrenar cuando no se usa --comparar ni --hpo.",
)
@click.option("--comparar", is_flag=True, help="Entrena todos los modelos y los compara.")
@click.option("--hpo", is_flag=True, help="Busqueda de hiperparametros con Optuna.")
@click.option("--trials", type=int, default=20, show_default=True, help="Trials de Optuna.")
@click.option(
    "--registrar/--no-registrar",
    default=None,
    help="Registra el modelo como @candidate. Por defecto: si con --hpo o --comparar.",
)
@click.option(
    "--holdout",
    is_flag=True,
    help=(
        "Evalua el modelo final en el holdout fijo. Solo para el gate: NUNCA "
        "para elegir modelo o hiperparametros."
    ),
)
@click.option("--no-cache", is_flag=True, help="Re-prepara los datos en lugar de usar el cache.")
@click.option("--verbose", "-v", is_flag=True)
def comando_train(
    modelo: str,
    comparar: bool,
    hpo: bool,
    trials: int,
    registrar: bool | None,
    holdout: bool,
    no_cache: bool,
    verbose: bool,
) -> None:
    """Entrena y deja evidencia en MLflow.

    Tres modos, de menor a mayor costo:

    \b
      taxi train                    un modelo (por defecto, el baseline lineal)
      taxi train --comparar         todos los modelos, mismos datos y features
      taxi train --hpo --trials 20  Optuna con parent run + un child run por trial
    """
    _configurar_logging(verbose)
    if comparar and hpo:
        raise click.UsageError("--comparar y --hpo son excluyentes: elige uno.")

    from taxi.models import train as entrenamiento

    usar_cache = not no_cache
    if hpo:
        resultado = entrenamiento.optimizar_hiperparametros(
            trials=trials,
            registrar_mejor=True if registrar is None else registrar,
            usar_cache=usar_cache,
        )
    elif comparar:
        resultados = entrenamiento.comparar_modelos(
            registrar_mejor=True if registrar is None else registrar,
            usar_cache=usar_cache,
        )
        click.echo("Ranking en validacion (menor RMSE es mejor):")
        for puesto, r in enumerate(resultados, start=1):
            click.echo(f"  {puesto}. {r.nombre:<16} valid_rmse={r.rmse_valid:.4f}")
        resultado = resultados[0]
    else:
        resultado = entrenamiento.entrenar_baseline(
            modelo=modelo,
            registrar=bool(registrar),
            usar_cache=usar_cache,
        )

    click.secho(
        f"{resultado.nombre}: valid_rmse={resultado.rmse_valid:.4f} (run {resultado.run_id[:8]})",
        fg="green",
    )
    if resultado.version_registrada:
        click.echo(
            f"Registrado como {config.MODELO_REGRESION} v{resultado.version_registrada} "
            f"con alias @{config.ALIAS_CANDIDATO} y "
            f"{config.TAG_VALIDACION}=pending. Corre `taxi promote` para el gate."
        )

    if holdout:
        click.secho(
            "Evaluando en el holdout fijo. Recuerda: este numero NO debe usarse "
            "para volver a elegir hiperparametros.",
            fg="yellow",
        )
        # Se recarga el artefacto desde MLflow en lugar de reusar el objeto en
        # memoria: asi se mide exactamente lo que se serializo y se servira, y
        # un fallo de serializacion aparece aqui y no en produccion.
        import mlflow

        metricas, _ = entrenamiento.evaluar_en_holdout(
            mlflow.pyfunc.load_model(resultado.model_uri),
            run_id=resultado.run_id,
            usar_cache=usar_cache,
        )
        for clave, valor in metricas.items():
            click.echo(f"  {clave} = {valor:.4f}")


# =============================================================================
# promote
# =============================================================================
@cli.command("promote")
@click.option("--modelo", "nombre_modelo", default=config.MODELO_REGRESION, show_default=True)
@click.option("--candidato-version", default=None, help="Por defecto, la ultima registrada.")
@click.option(
    "--mejora-minima",
    type=float,
    default=config.MEJORA_MINIMA_RELATIVA,
    show_default=True,
    help="Mejora relativa de RMSE global exigida (0.01 = 1%).",
)
@click.option(
    "--umbral-subgrupo",
    type=float,
    default=None,
    help="Degradacion relativa maxima por subgrupo. Por defecto, la del modulo evaluate.",
)
@click.option("--dry-run", is_flag=True, help="Evalua e informa sin escribir tags ni aliases.")
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def comando_promote(
    ctx: click.Context,
    nombre_modelo: str,
    candidato_version: str | None,
    mejora_minima: float,
    umbral_subgrupo: float | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Gate de promocion: decide si el candidato reemplaza al @champion.

    Exit code 0 si promueve, 1 si rechaza (el CI debe fallar), 2 si no pudo
    medir. Ver scripts/promote.py.
    """
    _configurar_logging(verbose)
    from taxi.models import evaluate

    promote = _cargar_script("promote")
    codigo: int = promote.ejecutar_gate(
        nombre_modelo=nombre_modelo,
        candidato_version=candidato_version,
        mejora_minima=mejora_minima,
        umbral_subgrupo=(
            evaluate.UMBRAL_DEGRADACION_SUBGRUPO if umbral_subgrupo is None else umbral_subgrupo
        ),
        dry_run=dry_run,
    )
    ctx.exit(codigo)


# =============================================================================
# model-card
# =============================================================================
@cli.command("model-card")
@click.option("--modelo", "nombre_modelo", default=config.MODELO_REGRESION, show_default=True)
@click.option("--alias", default=config.ALIAS_PRODUCCION, show_default=True)
@click.option(
    "--salida",
    type=click.Path(path_type=Path),
    default=None,
    help="Ruta del Markdown. Por defecto, docs/model-card.md.",
)
@click.option("--verbose", "-v", is_flag=True)
def comando_model_card(nombre_modelo: str, alias: str, salida: Path | None, verbose: bool) -> None:
    """Genera docs/model-card.md desde el modelo registrado.

    Funciona sin MLflow disponible: emite la card en modo degradado con un aviso
    visible en lugar de fallar.
    """
    _configurar_logging(verbose)
    model_card = _cargar_script("model_card")
    ruta, info, metadata = model_card.generar(
        nombre_modelo=nombre_modelo,
        alias=alias,
        salida=salida or model_card.RUTA_SALIDA_DEFECTO,
    )
    model_card.informar(ruta, info, metadata, alias=alias)


# =============================================================================
# drift
# =============================================================================
@cli.command("drift")
@click.option(
    "--particion",
    default=None,
    help=(
        "Particion de produccion a comparar contra la referencia, p. ej. 2024-01. "
        "Por defecto, todas las de PARTICIONES_PRODUCCION."
    ),
)
@click.option("--verbose", "-v", is_flag=True)
def comando_drift(particion: str | None, verbose: bool) -> None:
    """Reporte de drift: referencia (train) vs produccion simulada.

    El drift de este curso es REAL, no sintetico: las particiones de produccion
    son julio de 2023 (estacionalidad) y enero de 2024 (un ano de distancia).
    """
    _configurar_logging(verbose)
    # Import dentro de la funcion y tolerante a fallo: el modulo de monitoreo
    # es de otra sesion y puede no estar presente todavia en el checkout del
    # estudiante. Un ImportError en el import de nivel de modulo romperia
    # `taxi --help` y con el TODOS los demas subcomandos, que es un acoplamiento
    # inaceptable entre partes independientes del curso.
    try:
        check_drift = importlib.import_module("taxi.monitoring.check_drift")
    except ImportError as exc:
        raise click.ClickException(
            "El modulo taxi.monitoring.check_drift todavia no esta disponible "
            f"({exc}). Es el contenido de la sesion de monitoreo. Mientras tanto, "
            "el resto del CLI funciona: prueba `taxi data`, `taxi train` o "
            "`taxi promote`."
        ) from exc

    # Se acepta cualquiera de las dos formas de exponer el punto de entrada
    # (funcion simple o comando de click) para no imponerle una firma al otro
    # modulo. Si no encuentra ninguna, lo dice en lugar de fallar con un
    # AttributeError sin contexto.
    for nombre in ("ejecutar", "generar_reporte", "main"):
        entrada: Any = getattr(check_drift, nombre, None)
        if entrada is None:
            continue
        if isinstance(entrada, click.Command):
            argumentos = ["--particion", particion] if particion else []
            entrada.main(args=argumentos, standalone_mode=False)
            return
        resultado = entrada(particion) if particion else entrada()
        if resultado is not None:
            click.echo(resultado)
        return

    raise click.ClickException(
        "taxi.monitoring.check_drift existe pero no expone `ejecutar`, "
        "`generar_reporte` ni `main`. Corre el modulo directamente con "
        "`python -m taxi.monitoring.check_drift`."
    )


def main() -> None:
    """Punto de entrada alternativo, util para `python -m taxi.cli`."""
    cli()


if __name__ == "__main__":
    sys.exit(cli())
