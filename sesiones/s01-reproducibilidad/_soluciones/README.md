# Soluciones de referencia — S01

| Archivo | Qué resuelve |
|---|---|
| [`solucion-taller.md`](solucion-taller.md) | El [taller](../taller.md), criterio de aceptación por criterio de aceptación, aplicado al repositorio del curso |
| [`adr-000-stack.md`](adr-000-stack.md) | Ejemplo completo del `docs/adr/000-stack.md` que pide el punto 9 del taller, rellenado de verdad |

Son **una** solución, no *la* solución. Lo que se evalúa es que los diez criterios
de aceptación se cumplan y que las decisiones estén argumentadas, no que el stack
coincida con el de aquí. Un proyecto con Poetry, `poetry.lock` commiteado y CI verde
cumple exactamente igual.

El repositorio del curso **es** la solución de referencia de la mayor parte del
taller. Cuando la respuesta ya está implementada en el repo, la solución enlaza al
archivo en lugar de copiarlo: así no puede quedar desactualizada.

Recomendación para el instructor: **no publicar esta carpeta antes del taller.** El
valor pedagógico está en el intento; con la solución a la vista el intento no
ocurre. En particular, el ADR de ejemplo desactiva por completo el ejercicio de
pensar en las alternativas descartadas, que es el 80 % del valor del punto 9.
