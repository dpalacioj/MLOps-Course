# Soluciones de referencia — S06

| Archivo | Qué resuelve |
|---|---|
| `solucion-taller.md` | Taller (`../taller.md`), aplicado al caso guía, con los ocho criterios de aceptación uno por uno |
| `evidencia.sh` | Genera la evidencia que el taller pide pegar en el PR |

Son **una** solución, no *la* solución. Lo que se evalúa es que el gate cumpla los
criterios de aceptación y que los umbrales estén argumentados, no que los números
coincidan con los de aquí. De hecho **no van a coincidir**: el margen de mejora exigido
y el umbral por subgrupo dependen del dataset, del tamaño del holdout y del costo de un
error en cada proyecto. Copiarlos es el error que el taller penaliza.

Particularidad de esta sesión: la solución del caso guía **ya está en el repositorio**
([`scripts/promote.py`](../../../scripts/promote.py),
[`src/taxi/models/evaluate.py`](../../../src/taxi/models/evaluate.py),
[`.github/workflows/`](../../../.github/workflows/)). Este archivo no la duplica: la
recorre indicando qué satisface qué criterio y qué se acepta como alternativa válida.

Recomendación para el instructor: no publicar esta carpeta antes del taller. El valor
pedagógico está en el intento, y con la solución a la vista el intento no ocurre.
