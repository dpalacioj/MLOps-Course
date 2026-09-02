"""Gate de promocion: decide si un candidato reemplaza al ``@champion``.

Problema que resuelve
---------------------
"El modelo nuevo tiene mejor RMSE, subamoslo" es exactamente como se degradan los
sistemas de ML en produccion. Faltan tres preguntas:

1. Los datos con los que se midio, son validos? (si no, la metrica no dice nada)
2. La mejora es real, o cabe dentro del ruido de muestreo?
3. Mejoro en promedio a costa de empeorar en algun segmento?

Este modulo contesta las tres, deja registro de cada respuesta y solo entonces
mueve el alias. Es la diferencia entre un despliegue y una decision.

Diseno: **la politica son funciones puras** (``decidir``), y la parte que habla
con MLflow esta aparte (``promover``). Por eso el gate se puede testear sin
levantar nada, y por eso ``tests/unit/test_promocion.py`` es rapido y confiable.

Rollback: no hay un procedimiento aparte. Volver atras es mover ``@champion`` a
la version anterior. Es una escritura de metadatos —sub-segundo, sin reentrenar,
sin rebuild de imagen— y funciona porque las versiones del registry son
inmutables. Esa propiedad es la razon principal para referenciar el modelo por
alias en lugar de copiar el artefacto a un directorio.

Exit codes cuando se ejecuta como script:

    0  promovido (o ya era el champion)
    1  RECHAZADO  <- el CI debe fallar aqui
    2  error de infraestructura (no se pudo medir)

El 1 y el 2 se distinguen a proposito: "el modelo no es lo bastante bueno" es un
resultado exitoso del gate; "no pude medir" es una falla del gate. Confundirlos
hace que un MLflow caido se lea como un modelo malo.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field

from miproyecto.config import (
    ALIAS_PRODUCCION,
    DEGRADACION_MAXIMA_SUBGRUPO,
    MEJORA_MINIMA_RELATIVA,
    MODELO_REGISTRADO,
    TAG_VALIDACION,
)

logger = logging.getLogger(__name__)

EXITO_PROMOVIDO = 0
EXITO_RECHAZADO = 1
ERROR_INFRA = 2

#: Metrica que decide. Se declara aqui para que no haya dos criterios en el
#: proyecto ("en el notebook comparo r2 y en el gate rmse").
METRICA_DECISORIA = "rmse"
#: True si la metrica decisoria es un error (bajar es mejorar).
METRICA_ES_ERROR = True


@dataclass
class Decision:
    """Resultado del gate, con el motivo por escrito.

    Un gate que devuelve solo True/False es inauditable: tres semanas despues
    nadie sabe por que ese modelo llego a produccion.
    """

    promover: bool
    motivo: str
    delta_relativo: float | None = None
    subgrupos_degradados: list[str] = field(default_factory=list)


def delta_relativo(candidato: float, champion: float) -> float:
    """Cambio relativo del candidato respecto al champion.

    Convencion: para un error, negativo es mejor. Se documenta porque el signo
    es la fuente numero uno de confusion al leer la tabla del gate.
    """
    if champion == 0:
        raise ZeroDivisionError("la metrica del champion es 0: no hay linea base valida")
    return (candidato - champion) / champion


def _mejora(delta: float) -> bool:
    return delta < 0 if METRICA_ES_ERROR else delta > 0


def subgrupos_degradados(
    subgrupos_candidato: dict[str, float],
    subgrupos_champion: dict[str, float],
    *,
    umbral: float = DEGRADACION_MAXIMA_SUBGRUPO,
) -> list[str]:
    """Subgrupos donde el candidato empeora mas de ``umbral`` en relativo.

    Solo compara claves presentes en ambos: un subgrupo que aparece por primera
    vez no tiene con que compararse, y tratarlo como degradacion produciria un
    rechazo espurio cada vez que llega una categoria nueva.
    """
    degradados: list[str] = []
    for clave, valor in subgrupos_candidato.items():
        if not clave.startswith(f"{METRICA_DECISORIA}_"):
            continue
        base = subgrupos_champion.get(clave)
        if base is None or base == 0:
            continue
        if delta_relativo(valor, base) > umbral:
            degradados.append(clave)
    return sorted(degradados)


def decidir(
    metricas_candidato: dict[str, float],
    metricas_champion: dict[str, float] | None,
    *,
    subgrupos_candidato: dict[str, float] | None = None,
    subgrupos_champion: dict[str, float] | None = None,
    mejora_minima: float = MEJORA_MINIMA_RELATIVA,
    umbral_subgrupo: float = DEGRADACION_MAXIMA_SUBGRUPO,
    datos_validos: bool = True,
) -> Decision:
    """Aplica la politica de promocion. Funcion pura: no toca MLflow ni disco.

    Args:
        metricas_candidato: metricas del candidato en el holdout FIJO.
        metricas_champion: metricas del champion en el MISMO holdout. ``None``
            cuando todavia no hay champion.
        subgrupos_candidato: metricas por subgrupo del candidato.
        subgrupos_champion: metricas por subgrupo del champion.
        mejora_minima: mejora relativa minima exigida. Exigir un margen (y no
            solo "empatar") evita el churn de modelos por ruido de muestreo.
        umbral_subgrupo: degradacion relativa maxima tolerada por subgrupo.
        datos_validos: resultado de los tests de datos. Si es False no se
            compara nada: una metrica medida sobre datos invalidos no significa
            nada, y promover por ella es peor que no promover.
    """
    if not datos_validos:
        return Decision(False, "los tests de datos no pasaron: la metrica no es interpretable")

    if METRICA_DECISORIA not in metricas_candidato:
        return Decision(False, f"el candidato no reporta {METRICA_DECISORIA}")

    if metricas_champion is None:
        return Decision(True, "no hay champion: el candidato se promueve como linea base")

    delta = delta_relativo(
        metricas_candidato[METRICA_DECISORIA], metricas_champion[METRICA_DECISORIA]
    )

    if not _mejora(delta) or abs(delta) < mejora_minima:
        return Decision(
            False,
            f"la mejora ({delta:+.2%}) no supera el margen minimo exigido "
            f"({mejora_minima:.2%}); cabe dentro del ruido",
            delta_relativo=delta,
        )

    degradados = subgrupos_degradados(
        subgrupos_candidato or {},
        subgrupos_champion or {},
        umbral=umbral_subgrupo,
    )
    if degradados:
        return Decision(
            False,
            f"mejora global de {delta:+.2%} pero degrada mas de "
            f"{umbral_subgrupo:.0%} en: {', '.join(degradados)}",
            delta_relativo=delta,
            subgrupos_degradados=degradados,
        )

    return Decision(
        True,
        f"mejora {delta:+.2%} en {METRICA_DECISORIA} sin degradar subgrupos",
        delta_relativo=delta,
    )


def promover(version: str, decision: Decision, *, dry_run: bool = False) -> None:
    """Escribe el tag de validacion y mueve el alias ``@champion``.

    El tag se escribe SIEMPRE (tambien cuando se rechaza): la evidencia de por
    que un modelo no se promovio vale tanto como la de por que si.
    """
    import mlflow

    from miproyecto.config import MLFLOW_TRACKING_URI

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    cliente = mlflow.MlflowClient()
    estado = "passed" if decision.promover else "failed"

    if dry_run:
        logger.info(
            "[dry-run] %s=%s en la version %s; motivo: %s",
            TAG_VALIDACION,
            estado,
            version,
            decision.motivo,
        )
        return

    cliente.set_model_version_tag(MODELO_REGISTRADO, version, TAG_VALIDACION, estado)
    cliente.set_model_version_tag(MODELO_REGISTRADO, version, "gate_motivo", decision.motivo)
    if decision.promover:
        cliente.set_registered_model_alias(MODELO_REGISTRADO, ALIAS_PRODUCCION, version)
        logger.info("version %s promovida a @%s", version, ALIAS_PRODUCCION)
    else:
        logger.warning("version %s RECHAZADA: %s", version, decision.motivo)


def main() -> int:
    """Punto de entrada del gate. Lo llama ``make promote`` y el CI.

    TODO(estudiante) 15: implementa la lectura de metricas del candidato y del
    champion desde el registry (``cliente.get_model_version_by_alias``) y
    evaluando ambos en ``PARTICION_TEST``. Manten `decidir` pura: pasale
    diccionarios, no clientes de MLflow.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger.error(
        "El gate todavia no esta implementado (TODO 15). Sale con codigo de "
        "infraestructura para que el CI no interprete esto como un modelo malo."
    )
    return ERROR_INFRA


if __name__ == "__main__":
    sys.exit(main())
