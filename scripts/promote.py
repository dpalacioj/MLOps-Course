#!/usr/bin/env python
"""Gate de promocion: decide si un candidato reemplaza al @champion.

Problema que resuelve
---------------------
"El modelo nuevo tiene mejor RMSE, subamoslo" es como se degradan los sistemas
de ML en produccion. Falta responder tres preguntas antes de mover trafico:

1. Los datos con los que se midio, son validos? (si no, la metrica no significa
   nada)
2. La mejora es real, o cabe dentro del ruido de muestreo?
3. Mejoro en promedio a costa de empeorar en algun segmento?

Este script contesta las tres, deja registro de cada respuesta y solo entonces
mueve el alias. Es la diferencia entre un despliegue y una decision.

El script es solo la capa de presentacion: la politica vive en
``taxi.models.evaluate`` como funciones puras, y por eso se puede testear sin
levantar MLflow (ver ``tests/unit/test_gate.py``).

Uso
---
    python scripts/promote.py                      # resuelve la ultima version
    python scripts/promote.py --candidato-version 7
    python scripts/promote.py --dry-run            # no escribe nada
    taxi promote --dry-run                         # equivalente por el CLI

Exit codes
----------
    0  el candidato se promovio (o ya era el champion)
    1  el candidato fue rechazado  <- el CI debe fallar aqui
    2  error de infraestructura (no se pudo hablar con MLflow, faltan datos)

El codigo 1 y el 2 se distinguen a proposito: "el modelo no es lo bastante
bueno" es un resultado exitoso del gate; "no pude medir" es una falla del gate.
Confundirlos hace que un MLflow caido se lea como un modelo malo.

Rollback
--------
No hay un procedimiento de rollback aparte. Volver atras es mover @champion a la
version anterior:

    python -c "from taxi.models import registry; \
               registry.asignar_alias('nyc-taxi-duration', 'champion', '6')"

Eso es una escritura de metadatos: sub-segundo, sin reentrenar, sin rebuild de
imagen, sin redeploy. Las versiones del registry son inmutables, asi que la
version anterior sigue intacta y el artefacto es bit a bit el que estaba
sirviendo. Esta propiedad es la razon principal por la que el modelo se
referencia por alias y no se copia a un directorio.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import click
import pandas as pd
from rich.console import Console
from rich.table import Table

from taxi import config
from taxi.models import evaluate, registry

logger = logging.getLogger(__name__)
consola = Console()

EXITO_PROMOVIDO = 0
EXITO_RECHAZADO = 1
ERROR_INFRA = 2


def _tabla_comparativa(
    metricas_candidato: dict[str, float],
    metricas_champion: dict[str, float] | None,
    subgrupos_candidato: dict[str, float],
    subgrupos_champion: dict[str, float] | None,
    *,
    umbral_subgrupo: float,
) -> Table:
    """Tabla candidato vs champion, global y por subgrupo.

    La columna de delta usa la convencion "negativo es mejor" porque la metrica
    es un error. Se marca explicitamente para que nadie tenga que adivinar.
    """
    tabla = Table(title="Candidato vs @champion en el holdout fijo", header_style="bold")
    tabla.add_column("metrica")
    tabla.add_column("candidato", justify="right")
    tabla.add_column("champion", justify="right")
    tabla.add_column("delta rel.", justify="right")
    tabla.add_column("")

    def fila(
        clave: str,
        valor_c: float,
        valor_ch: float | None,
        *,
        es_error: bool,
        aplica_umbral: bool = False,
    ) -> None:
        if valor_ch is None or valor_ch == 0:
            tabla.add_row(clave, f"{valor_c:.4f}", "-", "-", "sin linea base")
            return
        delta = (valor_c - valor_ch) / valor_ch
        # Para un error, bajar es mejorar; para r2, subir es mejorar.
        mejora = delta < 0 if es_error else delta > 0
        marca = "mejora" if mejora else "empeora"
        color = "green" if mejora else "red"
        # El umbral por subgrupo se marca SOLO en las filas de subgrupo. Ponerlo
        # tambien en las globales daria a entender que el criterio 2 usa ese
        # umbral, cuando usa MEJORA_MINIMA_RELATIVA, que es distinto y mas
        # estricto. Una tabla que confunde dos umbrales es peor que una sin
        # marcas.
        if aplica_umbral and delta > umbral_subgrupo:
            marca = f"DEGRADA > {umbral_subgrupo:.0%}"
        tabla.add_row(
            clave,
            f"{valor_c:.4f}",
            f"{valor_ch:.4f}",
            f"[{color}]{delta:+.2%}[/{color}]",
            f"[{color}]{marca}[/{color}]",
        )

    for clave in ("rmse", "mae", "r2"):
        fila(
            clave,
            metricas_candidato[clave],
            metricas_champion[clave] if metricas_champion else None,
            es_error=clave != "r2",
        )

    tabla.add_section()
    for clave in sorted(k for k in subgrupos_candidato if k.startswith("rmse_")):
        n = int(subgrupos_candidato.get(clave.replace("rmse_", "n_"), 0))
        fila(
            f"{clave}  (n={n})",
            subgrupos_candidato[clave],
            subgrupos_champion.get(clave) if subgrupos_champion else None,
            es_error=True,
            aplica_umbral=True,
        )
    return tabla


def _tabla_criterios(decision: evaluate.DecisionGate) -> Table:
    """Los criterios del gate con su veredicto y el numero que lo justifica."""
    tabla = Table(title="Criterios del gate", header_style="bold")
    tabla.add_column("#", justify="right")
    tabla.add_column("criterio")
    tabla.add_column("estado")
    tabla.add_column("detalle", overflow="fold")
    for indice, criterio in enumerate(decision.criterios, start=1):
        color = "green" if criterio.aprobado else ("yellow" if not criterio.evaluado else "red")
        tabla.add_row(
            str(indice),
            criterio.nombre,
            f"[{color}]{criterio.estado}[/{color}]",
            criterio.detalle,
        )
    return tabla


def _cargar_modelo(uri: str) -> Any:
    """Carga un modelo pyfunc por URI, sin importar con que flavor se entreno."""
    import mlflow

    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    return mlflow.pyfunc.load_model(uri)


def ejecutar_gate(
    *,
    nombre_modelo: str = config.MODELO_REGRESION,
    candidato_version: str | None = None,
    mejora_minima: float = config.MEJORA_MINIMA_RELATIVA,
    umbral_subgrupo: float = evaluate.UMBRAL_DEGRADACION_SUBGRUPO,
    dry_run: bool = False,
    holdout: pd.DataFrame | None = None,
) -> int:
    """Corre el gate completo y devuelve el exit code.

    Args:
        nombre_modelo: nombre del modelo registrado.
        candidato_version: version a evaluar. ``None`` resuelve la ultima
            registrada (conveniente en clase, explicito en CD real).
        mejora_minima: margen relativo de RMSE global exigido.
        umbral_subgrupo: degradacion relativa maxima tolerada por subgrupo.
        dry_run: evalua e informa, pero no escribe tags ni mueve aliases.
        holdout: dataframe del holdout, inyectable para tests.

    Returns:
        ``EXITO_PROMOVIDO``, ``EXITO_RECHAZADO`` o ``ERROR_INFRA``.
    """
    cli = registry.cliente()

    # Las consultas de METADATOS van con timeout corto: si MLflow no responde, el
    # gate debe devolver ERROR_INFRA en segundos, no colgar el job de CD durante
    # minutos reintentando. La descarga de los ARTEFACTOS (mas abajo) usa los
    # defaults, porque ahi tardar si es legitimo.
    with registry.fallar_rapido():
        if candidato_version is None:
            mv = registry.ultima_version(nombre_modelo, cliente_mlflow=cli)
            if mv is None:
                consola.print(
                    f"[red]No hay ninguna version registrada de '{nombre_modelo}'.[/red]\n"
                    "Entrena y registra un candidato primero: taxi train --hpo"
                )
                return ERROR_INFRA
            candidato_version = str(mv.version)
        champion = registry.version_por_alias(
            nombre_modelo, config.ALIAS_PRODUCCION, cliente_mlflow=cli
        )

    consola.print(f"Candidato: [bold]{nombre_modelo}[/bold] version {candidato_version}")

    if champion is not None and str(champion.version) == str(candidato_version):
        consola.print(
            f"[yellow]La version {candidato_version} ya es @{config.ALIAS_PRODUCCION}. "
            "Nada que promover.[/yellow]"
        )
        return EXITO_PROMOVIDO

    # ---- Holdout -----------------------------------------------------------
    if holdout is None:
        try:
            from taxi.models import train

            holdout = train.cargar_holdout()
        except Exception as exc:
            consola.print(f"[red]No se pudo cargar el holdout: {exc}[/red]")
            consola.print("Corre `taxi data` primero.")
            return ERROR_INFRA
    consola.print(
        f"Holdout: particion fija {config.PARTICION_TEST} con {len(holdout)} filas. "
        "No se uso para seleccionar hiperparametros."
    )

    # ---- Evaluacion --------------------------------------------------------
    # El champion se REEVALUA sobre el holdout actual en lugar de leer las
    # metricas de su run. Si el holdout o el codigo de la metrica cambiaron
    # desde que se entreno, los numeros guardados no son comparables, y un gate
    # que compara numeros incomparables es peor que no tener gate.
    try:
        modelo_candidato = _cargar_modelo(f"models:/{nombre_modelo}/{candidato_version}")
        metricas_candidato, subgrupos_candidato = evaluate.evaluar_modelo(modelo_candidato, holdout)
    except Exception as exc:
        consola.print(f"[red]No se pudo evaluar el candidato: {exc}[/red]")
        return ERROR_INFRA

    metricas_champion: dict[str, float] | None = None
    subgrupos_champion: dict[str, float] | None = None
    if champion is None:
        consola.print(
            f"[yellow]No hay @{config.ALIAS_PRODUCCION}: este seria el PRIMER modelo "
            "en produccion.[/yellow]"
        )
    else:
        consola.print(f"Champion actual: version {champion.version}")
        try:
            modelo_champion = _cargar_modelo(
                config.uri_modelo(nombre_modelo, config.ALIAS_PRODUCCION)
            )
            metricas_champion, subgrupos_champion = evaluate.evaluar_modelo(
                modelo_champion, holdout
            )
        except Exception as exc:
            consola.print(f"[red]No se pudo evaluar el champion: {exc}[/red]")
            return ERROR_INFRA

    # ---- Decision ----------------------------------------------------------
    decision = evaluate.decidir_promocion(
        holdout,
        metricas_candidato,
        subgrupos_candidato,
        metricas_champion,
        subgrupos_champion,
        mejora_minima=mejora_minima,
        umbral_subgrupo=umbral_subgrupo,
    )

    consola.print()
    consola.print(
        _tabla_comparativa(
            metricas_candidato,
            metricas_champion,
            subgrupos_candidato,
            subgrupos_champion,
            umbral_subgrupo=umbral_subgrupo,
        )
    )
    consola.print()
    consola.print(_tabla_criterios(decision))
    consola.print()

    # ---- Efectos: primero el tag, despues el alias -------------------------
    if dry_run:
        consola.print(
            "[cyan]--dry-run: no se escribio el tag ni se movio el alias.[/cyan]\n"
            f"Habria escrito {config.TAG_VALIDACION}={decision.estado_validacion} "
            f"y {'movido' if decision.promover else 'NO movido'} "
            f"@{config.ALIAS_PRODUCCION} a la version {candidato_version}."
        )
    else:
        registry.marcar_validacion(
            nombre_modelo, candidato_version, decision.estado_validacion, cliente_mlflow=cli
        )
        if decision.promover:
            registry.asignar_alias(
                nombre_modelo,
                config.ALIAS_PRODUCCION,
                candidato_version,
                cliente_mlflow=cli,
            )

    if decision.promover:
        anterior = f" (anterior: version {champion.version})" if champion else ""
        consola.print(
            f"[bold green]PROMOVIDO[/bold green] — {decision.motivo}\n"
            f"@{config.ALIAS_PRODUCCION} de '{nombre_modelo}' -> version "
            f"{candidato_version}{anterior}"
        )
        if champion:
            consola.print(
                f"[dim]Rollback: registry.asignar_alias('{nombre_modelo}', "
                f"'{config.ALIAS_PRODUCCION}', '{champion.version}') — "
                "una escritura de metadatos, sin reentrenar ni redeployar.[/dim]"
            )
        return EXITO_PROMOVIDO

    consola.print(
        f"[bold red]RECHAZADO[/bold red] — {decision.motivo}\n"
        f"@{config.ALIAS_PRODUCCION} sigue en "
        f"{'version ' + str(champion.version) if champion else 'ninguna version'}. "
        "El modelo que ya estaba sirviendo no se toco."
    )
    return EXITO_RECHAZADO


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--modelo", "nombre_modelo", default=config.MODELO_REGRESION, show_default=True)
@click.option(
    "--candidato-version",
    default=None,
    help="Version a evaluar. Por defecto, la ultima registrada.",
)
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
    default=evaluate.UMBRAL_DEGRADACION_SUBGRUPO,
    show_default=True,
    help="Degradacion relativa maxima tolerada en cualquier subgrupo.",
)
@click.option("--dry-run", is_flag=True, help="Evalua e informa sin escribir tags ni aliases.")
@click.option("--verbose", "-v", is_flag=True, help="Log en nivel INFO.")
def main(
    nombre_modelo: str,
    candidato_version: str | None,
    mejora_minima: float,
    umbral_subgrupo: float,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Ejecuta el gate de promocion y termina con el exit code correspondiente."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)-8s %(name)s: %(message)s",
    )
    codigo = ejecutar_gate(
        nombre_modelo=nombre_modelo,
        candidato_version=candidato_version,
        mejora_minima=mejora_minima,
        umbral_subgrupo=umbral_subgrupo,
        dry_run=dry_run,
    )
    sys.exit(codigo)


if __name__ == "__main__":
    main()
