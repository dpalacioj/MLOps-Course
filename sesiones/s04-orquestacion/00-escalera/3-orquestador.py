"""Peldano 3 de la escalera — ORQUESTADOR: "administra todo el workflow".

Las mismas tres funciones de `pasos.py`, en el mismo orden. La unica diferencia
con `1-script.py` son los decoradores y el `intento=` que se les pasa; el README
de esta carpeta los pone lado a lado, en la seccion "Peldano 1 y peldano 3, lado
a lado".

Correrlo bien:

    uv run python 3-orquestador.py

Correrlo con el paso 3 fallando:

    ESCALERA_FALLAR_EN=3 uv run python 3-orquestador.py

Y aqui esta lo que separa este peldano del anterior: el paso 3 falla, Prefect
espera, lo reintenta, **y los pasos 1 y 2 no se vuelven a ejecutar** porque su
estado ya es `Completed`. El flow termina en `Completed`, no en un traceback.

Si ademas esta arriba el servidor (`make prefect`, y luego el `prefect config
set` de `00-intro-prefect/README.md`), la corrida queda en
<http://127.0.0.1:4200> con su nombre, su duracion, sus logs, sus parametros, su
estado final y sus reintentos. Sin servidor el flow corre igual, contra una API
efimera, pero no queda nada que mirar despues.

Lo que este archivo **no** hace todavia: schedules, deployments, work pools,
artifacts, variables ni secretos. Eso es la progresion de `00-intro-prefect/`,
que es a donde sigue la clase.
"""

from pathlib import Path

from pasos import paso_1_descargar, paso_2_preparar, paso_3_resumir
from prefect import flow, get_run_logger, task
from prefect.runtime import task_run

# Los tres decoradores repiten los mismos argumentos a proposito, en vez de
# factorizarlos en un diccionario: se leen de corrido y se pueden cambiar uno
# por uno. El porque del backoff creciente (1 s, luego 3 s) esta en
# `00-intro-prefect/pasos/03-reintentos.py`.


@task(retries=2, retry_delay_seconds=[1, 3], retry_jitter_factor=0.2)
def descargar() -> Path:
    """Paso 1 como task. `task_run.run_count` es el numero de intento actual."""
    return paso_1_descargar(intento=task_run.run_count)


@task(retries=2, retry_delay_seconds=[1, 3], retry_jitter_factor=0.2)
def preparar(crudo: Path) -> Path:
    """Paso 2 como task. Recibe el resultado del paso 1: de ahi sale el grafo."""
    return paso_2_preparar(crudo, intento=task_run.run_count)


@task(retries=2, retry_delay_seconds=[1, 3], retry_jitter_factor=0.2)
def resumir(limpio: Path) -> Path:
    """Paso 3 como task."""
    return paso_3_resumir(limpio, intento=task_run.run_count)


@flow(name="escalera-peldano-3", log_prints=True)
def pipeline() -> str:
    """El mismo pipeline del peldano 1, ahora con estado por paso."""
    logger = get_run_logger()
    crudo = descargar()
    limpio = preparar(crudo)
    resumen = resumir(limpio)
    logger.info("Resumen escrito en %s", resumen)
    return str(resumen)


if __name__ == "__main__":
    pipeline()
