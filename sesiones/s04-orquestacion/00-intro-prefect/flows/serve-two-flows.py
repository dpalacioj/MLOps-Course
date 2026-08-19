"""Paso 6 de la progresion: servir dos flows desde un solo proceso.

`to_deployment()` construye el objeto deployment sin servirlo; `serve()` sirve
todos los que se le pasen. Un solo proceso, varios deployments independientes:
cada uno se lanza y se programa por separado.
"""

import time

from prefect import flow, serve


@flow
def flow_lento(segundos: int = 60) -> None:
    """Duerme el tiempo indicado. Sirve para ver un run en estado Running."""
    time.sleep(segundos)


@flow
def flow_rapido() -> None:
    """Vuelve de inmediato."""
    return


if __name__ == "__main__":
    lento = flow_lento.to_deployment(name="lento")
    rapido = flow_rapido.to_deployment(name="rapido")
    serve(lento, rapido)
