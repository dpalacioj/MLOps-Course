# Soluciones de referencia — S03

| Archivo | Qué resuelve |
|---|---|
| [`solucion-ejercicio-01.ipynb`](solucion-ejercicio-01.ipynb) | [`../exercises/ejercicio-01.md`](../exercises/ejercicio-01.md) — tracking completo, más los cuatro bonus |
| [`solucion-ejercicio-02.ipynb`](solucion-ejercicio-02.ipynb) | [`../exercises/ejercicio-02.md`](../exercises/ejercicio-02.md) — registry con tags y aliases, más promoción y rollback |
| [`solucion-taller.md`](solucion-taller.md) | [`../taller.md`](../taller.md), aplicado al caso guía, con la evidencia de cada criterio |

Son **una** solución, no *la* solución. Lo que se evalúa son los criterios de
completitud y de aceptación, y que las decisiones estén argumentadas — no que el
código coincida con el de aquí.

Cada notebook cierra con una tabla de **errores frecuentes y su causa**: es lo más
útil para el instructor mientras circula por el aula.

Recomendación: **no publicar esta carpeta antes del taller.** El valor pedagógico
está en el intento, y con la solución a la vista el intento no ocurre.

## Cómo ejecutarlas

```bash
make data      # solo para la solucion del ejercicio 01 y el taller
make mlflow    # tracking server con backend SQLite, en 127.0.0.1:5001
```

Los notebooks se guardan **sin outputs** (`nbstripout` en el pre-commit). Si
quieres verlos resueltos, ejecútalos.
