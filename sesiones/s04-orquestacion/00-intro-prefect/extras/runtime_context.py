"""Contexto de ejecucion: saber, desde dentro, quien soy y como me llamaron.

`prefect.runtime` da acceso al nombre del run, sus parametros, el deployment que
lo lanzo y el numero de intento. Sirve para logging con contexto y —el uso que
importa en MLOps— para **escribir el id del flow run como tag del modelo
registrado**, que es lo que permite reconstruir el linaje corrida -> modelo.
"""

from prefect import flow, get_run_logger, task
from prefect.runtime import deployment, flow_run, task_run


@task
def mostrar_contexto_de_task() -> None:
    """Imprime el contexto visible desde una task."""
    logger = get_run_logger()
    logger.info("Task run: %s (intento %s)", task_run.name, task_run.run_count)
    logger.info("Parametros del flow run: %s", flow_run.parameters)


@flow(log_prints=True)
def demo_contexto(x: int = 1) -> None:
    """Imprime el contexto visible desde el flow."""
    logger = get_run_logger()
    logger.info("Flow run: %s (id %s)", flow_run.name, flow_run.id)
    # Fuera de un deployment, `deployment.name` es None: el flow se lanzo a mano.
    logger.info("Deployment: %s", deployment.name)
    mostrar_contexto_de_task()


if __name__ == "__main__":
    demo_contexto(x=1)
