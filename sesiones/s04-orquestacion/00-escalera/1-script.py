"""Peldano 1 de la escalera — SCRIPT: "ejecuta codigo".

Python puro. Tres llamadas a funcion, en orden, y un `print` entre cada una. No
hay decoradores, no hay servidor, no hay dependencias fuera de la libreria
estandar. **Y funciona**: para una enorme cantidad de trabajos, esto es
suficiente y subir de peldano solo agrega piezas que hay que mantener.

Correrlo bien:

    uv run python 1-script.py

Correrlo mal, con el paso 3 fallando:

    ESCALERA_FALLAR_EN=3 uv run python 1-script.py

Lo que se obtiene del fallo: un traceback y codigo de salida 1. Lo que **no**
queda de esa corrida, ni de la buena: quien la lanzo, a que hora, cuanto tardo
cada paso, con que parametros, en que estado termino, ni si es la primera vez que
falla. Y al relanzarlo, los pasos 1 y 2 se repiten enteros aunque hubieran
terminado bien: ese es el costo que se mide en el README de esta carpeta.

Este archivo es tambien lo que ejecuta el peldano 2 (`2-cron/`), sin una sola
linea de diferencia.
"""

import sys

from pasos import cronometrar, paso_1_descargar, paso_2_preparar, paso_3_resumir


def main() -> int:
    print("pipeline: arranca")
    crudo = paso_1_descargar()
    limpio = paso_2_preparar(crudo)
    paso_3_resumir(limpio)
    # No hay `try/except`: si algo falla, el traceback sube y el proceso muere
    # con codigo != 0. Esconderlo detras de un except seria peor, porque el
    # script terminaria "bien" sin haber hecho el trabajo.
    print("pipeline: termina")
    cronometrar("pipeline completo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
