"""Clasificador de quejas: la app de referencia de la sesion 8 (LLMOps).

Vive fuera de ``src/taxi`` a proposito. Es un caso aparte —entrada de texto libre,
salida estructurada, un LLM en el medio— y meterlo en el paquete del caso guia
tendria dos efectos indeseables: obligaria a instalar el extra ``llmops`` para
correr la suite completa del curso, y mezclaria un problema de regresion tabular
con uno de generacion en el mismo namespace.

La frontera es deliberada y es en si misma una decision de MLOps: un extra
opcional que rompe la instalacion base no es opcional.

Modulos
-------
- ``esquema``       contrato de salida y validacion Pydantic
- ``proveedor``     abstraccion sobre el LLM (fake, eco, openai)
- ``prompts``       archivos versionados + Prompt Registry de MLflow
- ``clasificador``  la funcion instrumentada, con retry con feedback
- ``tracing``       configuracion del tracing, con modo degradado
- ``datos``         carga y validacion del dataset de evals
- ``costos``        estimacion de costo con precios parametrizables
- ``scorers``       deterministas, juez y calibracion juez-humano
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
