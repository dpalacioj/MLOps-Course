# Soluciones de referencia — S05

| Archivo | Qué resuelve |
|---|---|
| `solucion-taller.md` | Taller (`../taller.md`), aplicado al caso guía, con los ocho criterios de aceptación uno por uno |
| `verificar.sh` | Genera la evidencia que el taller pide pegar en el PR |

Son **una** solución, no *la* solución. Lo que se evalúa es que el servicio cumpla
los criterios de aceptación y que las decisiones estén argumentadas, no que el código
coincida con el de aquí.

Particularidad de esta sesión: la solución del caso guía **ya está en el
repositorio** ([`src/taxi/api/`](../../../src/taxi/api/), [`Dockerfile`](../../../Dockerfile),
[`tests/api/`](../../../tests/api/)). Este archivo no la duplica: la recorre indicando
qué línea satisface qué criterio y qué se acepta como alternativa válida. Duplicar el
código aquí crearía una segunda copia que se desincroniza, que es exactamente el
anti-patrón que la sesión corrige.

Recomendación para el instructor: no publicar esta carpeta antes del taller. El valor
pedagógico está en el intento, y con la solución a la vista el intento no ocurre.
