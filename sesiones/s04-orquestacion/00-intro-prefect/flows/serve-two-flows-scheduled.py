"""Paso 6b: dos flows con schedules distintos en el mismo proceso.

Es la forma en que conviven, por ejemplo, un entrenamiento mensual y una
validacion diaria: dos deployments, dos schedules, un proceso.
"""

import time

from prefect import flow, serve
from prefect.schedules import Cron, Interval


@flow
def flow_lento(segundos: int = 30) -> None:
    """Duerme el tiempo indicado."""
    time.sleep(segundos)


@flow
def flow_rapido() -> None:
    """Vuelve de inmediato."""
    return


if __name__ == "__main__":
    lento = flow_lento.to_deployment(
        name="lento-programado",
        schedules=[Interval(60, timezone="America/Bogota")],  # cada 60 segundos
    )
    rapido = flow_rapido.to_deployment(
        name="rapido-programado",
        schedules=[Cron("* * * * *", timezone="America/Bogota")],  # cada minuto
    )
    serve(lento, rapido)
