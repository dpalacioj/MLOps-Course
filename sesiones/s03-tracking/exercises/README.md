# Ejercicios de la sesión 3

Dos ejercicios guiados, con TODO numerados y **criterios de completitud
medibles**. Se resuelven en el tramo de taller o como refuerzo antes de la
entrega del hito.

| Ejercicio | Enunciado | Notebook | Qué practica | Dataset |
|---|---|---|---|---|
| 01 | [`ejercicio-01.md`](ejercicio-01.md) | [`ejercicio-01-agregar-tracking.ipynb`](ejercicio-01-agregar-tracking.ipynb) | Tracking: tags, params, métricas y artifacts sobre un entrenamiento que ya funciona | NYC Green Taxi (el caso guía) |
| 02 | [`ejercicio-02.md`](ejercicio-02.md) | [`ejercicio-02-model-registry.ipynb`](ejercicio-02-model-registry.ipynb) | Registry: versiones, tags de validación, aliases `champion`/`candidate` y carga por alias | Iris |

**Por qué el 02 usa Iris:** el tema es el ciclo de vida del modelo en el
registry, no el modelo. Con Iris cada entrenamiento tarda menos de un segundo, así
que se pueden hacer dos versiones y mover aliases sin que la clase espere. La
diferencia de dataset es deliberada, no un descuido.

## Antes de empezar (los dos ejercicios)

```bash
make data      # materializa las particiones del caso guia (solo el ejercicio 01)
make mlflow    # tracking server en http://127.0.0.1:5001
```

El **ejercicio 02 necesita el servidor con backend de base de datos**. Con
`mlflow ui` a secas, o con un file store (`file://mlruns`), el Model Registry no
existe y los TODO 3 en adelante fallan. `make mlflow` ya usa SQLite.

## Cómo se corrigen

Cada enunciado tiene una tabla **Criterios de completitud** con cantidades
verificables (3 tags, 3 params, 2 artefactos, 2 versiones…). No es una lista de
buenas intenciones: se cuenta en la UI o con la celda de verificación que trae
cada notebook.

Las soluciones de referencia están en
[`../_soluciones/`](../_soluciones/) — mira ahí **después** de intentarlo, no
antes.

## Material de apoyo

- [`../notebooks/02-tracking-con-mlflow.ipynb`](../notebooks/02-tracking-con-mlflow.ipynb) — el ejemplo completo de tracking
- [`../notebooks/03-hpo-y-registry.ipynb`](../notebooks/03-hpo-y-registry.ipynb) — registry, aliases y model card
- [`../scripts/train-mlflow-basico.py`](../scripts/train-mlflow-basico.py) — la versión mínima en un script
- [`../../../docs/adr/002-aliases-en-vez-de-stages.md`](../../../docs/adr/002-aliases-en-vez-de-stages.md) — por qué aliases y no stages
