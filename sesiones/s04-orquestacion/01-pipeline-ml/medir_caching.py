"""Mide el efecto del caching: ejecuta la task `preparar` dos veces y compara.

Por que un script y no un numero en el material: la duracion depende de la red,
del disco y de si el parquet ya estaba descargado. El material anterior afirmaba
"la primera vez descarga los datos (45 seg), la segunda tarda 0 segundos", y en
clase eso se desmiente solo. Lo que se ensena es **como medirlo**, y el resultado
es el que salga en esa maquina.

    uv run python sesiones/s04-orquestacion/01-pipeline-ml/medir_caching.py

Requiere el servidor de Prefect apuntado con PREFECT_API_URL (o usa el servidor
temporal que Prefect levanta solo).
"""

from __future__ import annotations

import time

from prefect import flow

from taxi.config import PARTICIONES_TRAIN
from taxi.flows.training import preparar


@flow(name="medir-caching", log_prints=True)
def medir(repeticiones: int = 2) -> list[float]:
    """Llama a `preparar` varias veces con los mismos inputs y mide cada llamada.

    La clave de cache de `preparar` es `task_input_hash`: depende solo de los
    inputs, no del flow run. Por eso el resultado se comparte entre corridas
    distintas del flow, que es exactamente lo que hace que la segunda ejecucion
    sea mas rapida.
    """
    duraciones: list[float] = []
    for intento in range(1, repeticiones + 1):
        inicio = time.perf_counter()
        df = preparar(PARTICIONES_TRAIN)
        transcurrido = time.perf_counter() - inicio
        duraciones.append(transcurrido)
        print(f"Ejecucion {intento}: {transcurrido:6.2f} s  ({len(df):,} filas)")
    return duraciones


if __name__ == "__main__":
    medidas = medir()
    if len(medidas) >= 2 and medidas[1] > 0:
        print(f"\nAceleracion de la segunda ejecucion: {medidas[0] / medidas[1]:.1f}x")
    print(
        "\nSi la segunda ejecucion NO fue mas rapida, revisa en este orden:\n"
        "  1. que la primera haya terminado en Completed (una task fallida no cachea);\n"
        "  2. que `persist_result` este activo en la task;\n"
        "  3. que no haya pasado `cache_expiration`;\n"
        "  4. que los inputs sean identicos (una tupla distinta es otra clave)."
    )
