# 01 · El pipeline de ML orquestado

Aquí **no hay una copia del pipeline**. El pipeline vive una sola vez, en el
paquete instalable, y esta carpeta solo lo ejecuta y lo analiza:

| Qué | Dónde vive |
|---|---|
| Flow de entrenamiento | `src/taxi/flows/training.py` |
| Pipeline batch de predicciones | `src/taxi/flows/batch.py` |
| Deployments y schedules | `src/taxi/flows/deploy.py` |
| Modelo, features y registry | `src/taxi/models/`, `src/taxi/features/`, `src/taxi/data/` |

Esta carpeta **no** contiene una copia del pipeline: lo importa. Mantener una
implementación paralela por sesión multiplica la superficie de bugs y deja al
curso sin una fuente de verdad — dos copias con features distintas entrenan dos
modelos distintos y ninguna de las dos es la que sirve en producción.

## Ejecutar

```bash
# 0. Servicios (dos terminales aparte)
make mlflow            # MLflow en http://127.0.0.1:5001
uv run prefect server start
uv run prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api

# 1. Entrenamiento completo (extraer, validar, preparar, entrenar, evaluar, registrar)
uv run python -m taxi.flows.training

# 2. Medir el efecto del caching: dos ejecuciones, tiempos comparados
uv run python sesiones/s04-orquestacion/01-pipeline-ml/medir_caching.py

# 3. Batch de predicciones (requiere un modelo en @champion)
uv run python -m taxi.flows.batch

# 4. Deployments con schedule
uv run python -m taxi.flows.deploy serve
```

Después del entrenamiento, en la UI de Prefect: **Runs → entrenamiento-taxi →
Artifacts**. Hay una tabla con las métricas de esa corrida y un markdown con el
resumen, incluida la frase que importa: el candidato **no** fue promovido.

## Lo que hay que mirar en el código, en este orden

1. **`extraer`** — `retries=3` con `retry_delay_seconds=[10, 30, 60]`. El backoff
   no es decorativo: reintentar de inmediato contra un servicio saturado agrega
   carga cuando está peor.
2. **`validar`** — el contrato de datos en la frontera. Falla antes de gastar CPU.
3. **`preparar`** — `cache_key_fn=task_input_hash` + `cache_expiration` +
   `persist_result`. Sin persistencia no hay caché entre corridas.
4. **`entrenar`** — `log_model(..., name="model")` (no `artifact_path=`), con
   `signature` e `input_example`. Y **sin** `try/except` alrededor del logging: el
   pipeline anterior degradaba ese fallo a un warning y terminaba "en verde" con
   un run sin modelo.
5. **`evaluar`** — mide en validación. El holdout de test es del gate (S06).
6. **`registrar_candidato`** — alias `candidate`, `validation_status=pending`,
   tags con la evidencia. **No** mueve `champion`.

## Consultar las predicciones del batch

```bash
sqlite3 -header -column data/predicciones.db < sesiones/s04-orquestacion/01-pipeline-ml/consultas-predicciones.sql
```

Las seis consultas de `consultas-predicciones.sql` están ordenadas por la
pregunta que responden: volumen por corrida, comparación entre versiones,
distribución de predicciones, trazabilidad de una predicción concreta, atípicas y
verificación de integridad. La última debe devolver **cero filas**: si devuelve
alguna, hay predicciones sin versión de modelo y la tabla dejó de servir para
auditar.

## Ejercicio

`ejercicio/` — construir un flow de clasificación con las funciones vacías y los
TODO numerados. La solución de referencia está en `../_soluciones/`.
