# Soluciones de referencia — S02

| Archivo | Qué resuelve |
|---|---|
| [`solucion-taller.md`](solucion-taller.md) | El [taller](../taller.md), criterio de aceptación por criterio de aceptación, aplicado al caso guía |

**El repositorio del curso es la solución de referencia de este taller.** El contrato,
los `fixtures` rotos, los tests de los tres niveles, la descarga con hash y el `split`
temporal **ya están implementados** en:

| Archivo | Qué demuestra |
|---|---|
| [`src/taxi/data/contract.py`](../../../src/taxi/data/contract.py) | los tres niveles de check, con su razonamiento y su calibración |
| [`src/taxi/data/loaders.py`](../../../src/taxi/data/loaders.py) | descarga con SHA-256, filtro **contabilizado**, orden de validación |
| [`src/taxi/features/contract.py`](../../../src/taxi/features/contract.py) | la definición única de features, y la separación crudas / derivadas |
| [`tests/conftest.py`](../../../tests/conftest.py) | los `fixtures` generados en código, incluidos los tres rotos |
| [`tests/data/test_contrato_datos.py`](../../../tests/data/test_contrato_datos.py) | acepta lo válido, rechaza cada `fixture` roto |
| [`tests/data/test_niveles_de_check.py`](../../../tests/data/test_niveles_de_check.py) | los tres niveles por separado, el control negativo y la calibración del umbral |

Por eso la solución **enlaza** al archivo en lugar de copiarlo: una copia se
desactualiza en silencio, y este es justamente el curso donde eso no se puede permitir.

Son **una** solución, no *la* solución. Lo que se evalúa es que los trece criterios de
aceptación se cumplan y que los umbrales estén **calibrados con los datos del
estudiante**, no que coincidan con los de aquí. De hecho **no van a coincidir**: el
umbral de fracción del caso guía sale de haber medido `0,054 %` en el parquet de la TLC,
y copiarlo es exactamente el error que el criterio 6 penaliza.

Recomendación para el instructor: **no publicar esta carpeta antes del taller.** El
valor pedagógico está en el intento; con la solución a la vista el intento no ocurre.
