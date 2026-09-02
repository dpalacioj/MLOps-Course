"""Usar un bloque `Secret` para llamar a un LLM.

Dos correcciones respecto a la version anterior:

1. El modelo estaba hardcodeado como `gpt-3.5-turbo`, que hoy es un modelo
   legacy. Los nombres de modelo son la parte del codigo que envejece mas rapido:
   se leen de configuracion (una `Variable` de Prefect o una variable de entorno)
   para poder cambiarlos sin tocar el codigo ni volver a desplegar. **Verifica la
   lista de modelos vigentes del proveedor antes de la clase**: cualquier nombre
   escrito en un material de curso queda obsoleto.
2. Se usa `get_run_logger()` en lugar de `print` para lo que debe quedar en el
   run, y no se loguea la respuesta completa: en una app real puede contener
   datos del usuario (ver S08: PII en las trazas).

Requiere el extra de LLMOps del curso: `uv sync --extra llmops`.
"""

import os

from prefect import flow, get_run_logger, task
from prefect.blocks.system import Secret
from prefect.variables import Variable


@task(retries=2, retry_delay_seconds=[5, 15])
def llamar_llm(prompt: str) -> str:
    """Llama al LLM con la credencial guardada en un bloque Secret."""
    from openai import OpenAI

    logger = get_run_logger()

    # El secreto se resuelve en tiempo de ejecucion. No esta en el codigo, no
    # esta en la imagen y no esta en el repositorio.
    api_key = Secret.load("openai-api-key").get()

    # Configuracion, no codigo: se puede cambiar desde la UI de Prefect.
    modelo = Variable.get("openai_model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    logger.info("Consultando el modelo %s", modelo)

    cliente = OpenAI(api_key=api_key)
    respuesta = cliente.chat.completions.create(
        model=str(modelo),
        messages=[{"role": "user", "content": prompt}],
    )
    contenido = respuesta.choices[0].message.content or ""
    logger.info("Respuesta recibida: %d caracteres", len(contenido))
    return contenido


@flow
def flow_llm(prompt: str = "Explica MLOps en una frase.") -> str:
    """Flow minimo de una llamada a un LLM."""
    return llamar_llm(prompt)


if __name__ == "__main__":
    print(flow_llm())
