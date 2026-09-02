"""Bloques `Secret` de Prefect: como guardar una credencial y como NO guardarla.

Lo que NUNCA hay que escribir, aunque sea la forma mas corta y la que aparece
en muchos ejemplos:

    my_secret_block = Secret(value="shhh!-it's-a-secret")   # <-- jamas

Un secreto que esta en el repositorio no es un secreto. Y no se arregla borrando
la linea: queda en el historial de git para siempre, asi que hay que **rotar la
credencial**. El pre-commit del curso corre `gitleaks` precisamente para que este
error no llegue a un commit.

El valor se lee del entorno (o se pide por teclado) y el bloque se crea una sola
vez. Lo que se versiona es el **nombre** del bloque, nunca su contenido.
"""

import getpass
import os

from prefect.blocks.system import Secret

NOMBRE_BLOQUE = "openai-api-key"


def crear_secreto(nombre: str = NOMBRE_BLOQUE) -> None:
    """Crea o actualiza el bloque Secret leyendo el valor del entorno."""
    valor = os.getenv("OPENAI_API_KEY") or getpass.getpass(f"Valor para '{nombre}': ")
    if not valor:
        raise SystemExit("No se recibio ningun valor: no se crea el bloque.")

    # overwrite=True permite rotar la credencial sin borrar el bloque a mano.
    Secret(value=valor).save(name=nombre, overwrite=True)
    print(f"Bloque Secret '{nombre}' guardado. El valor no queda en el repositorio.")


def leer_secreto(nombre: str = NOMBRE_BLOQUE) -> str:
    """Lee el bloque. Devuelve el valor en claro: nunca lo imprimas en un log."""
    return str(Secret.load(nombre).get())


if __name__ == "__main__":
    crear_secreto()
