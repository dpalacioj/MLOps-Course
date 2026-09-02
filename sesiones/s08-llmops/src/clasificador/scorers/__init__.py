"""Evals en dos capas: deterministas primero, juez solo para lo que lo necesita.

El orden es la leccion, no un detalle de organizacion:

1. ``deterministas``  JSON valido, enum, rangos, longitud, PII, exactitud contra
   la etiqueta humana. Baratos, rapidos y sin varianza. Cubren la mayoria de los
   fallos reales de un sistema con salida estructurada.
2. ``juez``           LLM-as-judge con rubrica externa, **solo** para la calidad
   del resumen, que es lo unico que no tiene respuesta unica.
3. ``acuerdo``        porcentaje de acuerdo y kappa de Cohen entre el juez y una
   muestra etiquetada por humanos. Sin esto, el numero del juez no se reporta.

Empezar por el juez es el error de orden mas comun: es la parte vistosa y la
menos fiable.
"""

from __future__ import annotations

__all__: list[str] = []
