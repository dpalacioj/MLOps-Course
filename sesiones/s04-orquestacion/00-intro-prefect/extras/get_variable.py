"""Variables de Prefect: configuracion que cambia sin volver a desplegar.

Una `Variable` es un valor de configuracion no sensible (un umbral, el nombre de
un modelo, una lista de particiones) que se edita desde la UI o la CLI. Para
credenciales se usa un bloque `Secret` (ver `create_secret.py`); una Variable se
lee en claro.

    prefect variable set trials_optuna 20
    prefect variable ls
"""

from prefect.variables import Variable


def leer_configuracion() -> int:
    """Lee la variable con un default explicito.

    El `default` importa: sin el, `Variable.get` devuelve None si la variable no
    existe y el error aparece veinte lineas despues, convertido en un TypeError
    incomprensible.
    """
    return int(Variable.get("trials_optuna", default=20))


if __name__ == "__main__":
    print(f"trials_optuna = {leer_configuracion()}")
