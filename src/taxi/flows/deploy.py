"""Deployments de los flows del caso guia (Prefect 3).

Un flow que solo se ejecuta cuando alguien escribe `python ...` no esta
orquestado: esta automatizado a medias. El deployment es lo que convierte al flow
en algo que el servidor conoce, puede programar, puede parametrizar y puede
lanzar sin que nadie este presente.

`serve` vs `deploy` + work pool
-------------------------------
| Criterio | `flow.serve(...)` | `flow.deploy(..., work_pool_name=...)` |
|---|---|---|
| Quien ejecuta | el proceso que quedo vivo | un **worker** que toma trabajo del work pool |
| Infraestructura | estatica: la maquina donde corriste el comando | dinamica: contenedor/pod por corrida |
| Aislamiento | ninguno (mismo entorno del proceso) | por corrida (imagen propia) |
| Setup | cero | work pool + worker + registro de imagen |
| Cuando usarlo | clase, laboratorio, un servidor propio con una sola carga | produccion, cargas heterogeneas, dependencias en conflicto |

En clase usamos `serve`: cero infraestructura y se ve el resultado en la UI en
treinta segundos. En produccion se usa `deploy` con work pool, y `deploy()`
**exige** `work_pool_name`: sin work pool no hay quien ejecute. Un `.deploy()`
sin ese argumento no puede funcionar en Prefect 3.

Los **agents fueron eliminados** en Prefect 3: `prefect agent start` no existe.
El modelo es workers + work pools. Tampoco existen ya `Deployment.build_from_flow`
ni los bloques de infraestructura (`DockerContainer`, `KubernetesJob`) como
mecanismo de despliegue.

Por que `cron="*/2 * * * *"` reentrenando el modelo completo es un anti-patron
-----------------------------------------------------------------------------
Es un ejemplo que circula documentado como buena practica ("for learning
purposes"): reentrenar el modelo **completo** cada dos minutos, descargando los
parquets de la TLC en cada corrida. Es incorrecto por cinco razones
independientes:

1. **No aporta senal.** Los datos son particiones mensuales inmutables: entre las
   14:02 y las 14:04 no hay un solo dato nuevo. Se reentrena sobre exactamente el
   mismo dataset y se produce un modelo distinto solo por el ruido del proceso.
2. **Cuesta.** Descarga de decenas de MB por corrida (720 corridas al dia) y CPU
   de entrenamiento. En una nube eso es dinero; contra el servidor de la TLC es
   abuso de un recurso publico y gratuito.
3. **Ensucia el registry.** Con auto-promocion produce 720
   versiones "de produccion" al dia y hace ilegible el historial: el linaje de
   que modelo sirvio que prediccion deja de poder reconstruirse.
4. **Rompe la nocion de Continuous Training.** CT no significa "reentrenar
   seguido", significa "reentrenar **cuando hay una razon**": llegaron datos
   nuevos, hay drift, cayo la performance. Un cron cada dos minutos es lo
   contrario de un trigger.
5. **Ensena el habito equivocado.** El estudiante lo copia al proyecto y luego a
   su trabajo, donde el mismo patron sobre datos reales cuesta plata y ruido.

Lo correcto para este caso guia es un trigger **por llegada de datos**, aproximado
con un schedule mensual alineado a la publicacion de la TLC (que publica el mes
anterior con algunas semanas de rezago). El diseno del trigger es lo que el taller
pide argumentar en un ADR.
"""

from __future__ import annotations

import argparse
from typing import Any, Final

from prefect import serve
from prefect.schedules import Cron, Schedule

from taxi.flows.batch import batch_flow
from taxi.flows.training import entrenamiento_flow

#: Timezone del curso. Sin timezone, un cron se interpreta en UTC y el "3 a.m."
#: del enunciado ocurre a las 10 p.m. del dia anterior en Bogota.
ZONA: Final[str] = "America/Bogota"

#: Reentrenamiento mensual: dia 5 a las 03:00. El dia 5 y no el 1 porque la TLC
#: no publica el mes cerrado el primer dia; dejar margen evita una corrida que
#: falla siempre en el mismo punto del calendario.
CRON_ENTRENAMIENTO: Final[str] = "0 3 5 * *"

#: Batch de predicciones: dia 6 a las 04:00, despues de que el gate de CI tuvo la
#: oportunidad de promover al candidato del dia anterior.
CRON_BATCH: Final[str] = "0 4 6 * *"

#: Nombre convencional del work pool del curso.
WORK_POOL: Final[str] = "curso-mlops"


def _schedule(cron: str) -> Schedule:
    """Construye el schedule con `prefect.schedules.Cron`.

    Se pasa siempre dentro de ``schedules=[...]`` (plural). La forma heredada de
    Prefect 2 —la clave `schedule:` con un mapa `cron`/`timezone` en
    `prefect.yaml`, o `schedule={"cron": ..., "timezone": ...}` en codigo— esta
    deprecada: la clave canonica es `schedules:`, y si en `prefect.yaml` aparecen
    las dos el deploy falla. El atajo `cron="..."` sigue siendo valido y es
    equivalente cuando hay un solo schedule y no hace falta declarar la zona.

    `prefect.schedules.Cron` es la API vigente en Prefect 3.8; el
    `CronSchedule` de `prefect.client.schemas.schedules` es el mismo objeto a
    nivel de esquema de la API y sigue funcionando.
    """
    return Cron(cron, timezone=ZONA)


def servir(
    *,
    cron_entrenamiento: str = CRON_ENTRENAMIENTO,
    cron_batch: str = CRON_BATCH,
) -> None:
    """Sirve entrenamiento y batch desde un solo proceso (modo clase).

    El proceso queda vivo y hace polling de las corridas programadas. Ctrl+C lo
    detiene y los deployments desaparecen: `serve` no persiste infraestructura.
    """
    # `to_deployment` esta tipado para soportar tambien flows async, asi que su
    # retorno es una union; se anota Any para no arrastrar ese detalle.
    entrenamiento: Any = entrenamiento_flow.to_deployment(
        name="entrenamiento-mensual",
        schedules=[_schedule(cron_entrenamiento)],
        tags=["s04", "entrenamiento"],
        description="Reentrena y registra el candidato. No promueve.",
        parameters={"registrar": True},
    )
    batch: Any = batch_flow.to_deployment(
        name="batch-mensual",
        schedules=[_schedule(cron_batch)],
        tags=["s04", "batch"],
        description="Predice sobre la particion de produccion y persiste con trazabilidad.",
    )
    serve(entrenamiento, batch)


def desplegar(
    *,
    work_pool_name: str = WORK_POOL,
    imagen: str | None = None,
    cron_entrenamiento: str = CRON_ENTRENAMIENTO,
) -> None:
    """Crea un deployment persistente contra un work pool.

    Requiere el work pool creado y un worker corriendo:

    ```bash
    prefect work-pool create curso-mlops --type process   # o --type docker
    prefect worker start --pool curso-mlops
    ```

    Args:
        work_pool_name: obligatorio para `deploy()` en Prefect 3.
        imagen: imagen a construir/usar. Solo aplica a work pools que ejecutan
            contenedores; con un pool de tipo `process` se deja en None.
        cron_entrenamiento: expresion cron del schedule.
    """
    entrenamiento_flow.deploy(
        name="entrenamiento-mensual",
        work_pool_name=work_pool_name,
        image=imagen,
        # Sin imagen no hay nada que construir ni publicar. Un `build=True` por
        # defecto contra un pool `process` falla de forma confusa.
        build=imagen is not None,
        push=imagen is not None,
        schedules=[_schedule(cron_entrenamiento)],
        tags=["s04", "entrenamiento"],
        description="Reentrena y registra el candidato. No promueve.",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: `python -m taxi.flows.deploy serve|deploy`."""
    parser = argparse.ArgumentParser(description="Deployments de los flows del caso guia.")
    parser.add_argument(
        "modo", choices=["serve", "deploy"], help="serve = clase; deploy = work pool"
    )
    parser.add_argument("--work-pool", default=WORK_POOL, help="Work pool (solo para deploy)")
    parser.add_argument("--imagen", default=None, help="Imagen del contenedor (solo para deploy)")
    parser.add_argument(
        "--cron",
        default=CRON_ENTRENAMIENTO,
        help=f"Cron del entrenamiento (default: {CRON_ENTRENAMIENTO!r}, zona {ZONA})",
    )
    args = parser.parse_args(argv)

    if args.modo == "serve":
        servir(cron_entrenamiento=args.cron)
    else:
        desplegar(
            work_pool_name=args.work_pool,
            imagen=args.imagen,
            cron_entrenamiento=args.cron,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
