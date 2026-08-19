# Los tres escenarios de despliegue de MLflow

Los notebooks de [`../notebooks/`](../notebooks/) enseñan el **qué** (params,
métricas, autolog, HPO, registry). Estos tres enseñan el **dónde**.

| Escenario | Tracking server | Backend store | Artifacts | Registry | Se ejecuta en clase |
|---|---|---|---|---|---|
| [1 · file store local](scenario-1-file-store.ipynb) | no | archivos (`mlruns/`) | local | **no disponible** | sí |
| [2 · servidor local](scenario-2-server-local.ipynb) | sí (`127.0.0.1:5001`) | SQLite | local | disponible | sí |
| [3 · AWS](scenario-3-aws.ipynb) | EC2 | RDS PostgreSQL | S3 | disponible | **no**: se lee |

**Lo que hay que retener de los tres juntos:** el código de entrenamiento es
idéntico. Lo único que cambia es el valor de `MLFLOW_TRACKING_URI`. Cambia *dónde*
corre, no *cómo* se escribe.

**El escenario 3 no se ejecuta**: requiere infraestructura en AWS y cuesta dinero.
Se lee, se discute y se retoma en S06. La alternativa gratuita para ver la misma
arquitectura funcionando es el `docker-compose.yml` del curso (`make up`), que
levanta MLflow con Postgres y MinIO; MinIO habla el protocolo S3, así que el código
no cambia al pasar a AWS.

## Por qué el dataset es Iris

El tema de estos notebooks es la **topología**, no el modelo. Con Iris, cada
entrenamiento tarda menos de un segundo y la discusión se queda donde tiene que
estar: en dónde vive la metadata y dónde viven los artifacts. Cambiar a un dataset
grande solo añadiría minutos de espera a una conversación de infraestructura.

## Antes de empezar: el kernel de Jupyter

Para que el entorno virtual del curso aparezca como kernel:

```bash
uv run python -m ipykernel install --user --name mlops-udm --display-name "mlops udm"
```

Después, en Jupyter: *Kernel → Change kernel → mlops udm*. Si `import mlflow` falla
en el notebook pero funciona en la terminal, el kernel seleccionado es otro
intérprete. (El detalle completo de entornos está en
[`../../s01-reproducibilidad/`](../../s01-reproducibilidad/).)

## El escenario 2 es el que se usa el resto del curso

```bash
make mlflow    # server en 127.0.0.1:5001, backend SQLite, artifacts en ./mlartifacts
```

Con sus límites dichos en voz alta: SQLite es un archivo, así que dos procesos
escribiendo a la vez dan `database is locked`, los artifacts viven en un solo disco
y no hay backups. Suficiente para clase; insuficiente para un pipeline automatizado.
