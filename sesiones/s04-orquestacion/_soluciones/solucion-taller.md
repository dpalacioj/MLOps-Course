# Solución de referencia del taller — S04

Aplicada al caso guía. Sirve como rúbrica para revisar los entregables.

## 1-3. El flow

`src/taxi/flows/training.py`. Seis tasks (`extraer`, `validar`, `preparar`,
`entrenar`, `evaluar`, `registrar_candidato`) más `publicar_reporte`.

Qué mirar al revisar:

- **`retries` solo donde el fallo es transitorio.** `extraer` tiene
  `retries=3, retry_delay_seconds=[10, 30, 60]`. `entrenar` no tiene retries: si
  falló por un bug, reintentar tres veces solo tarda tres veces más en decírtelo.
- **El backoff es creciente.** Un `retry_delay_seconds=2` agota los tres intentos
  dentro de la misma ventana de degradación de la red: es casi lo mismo que no
  reintentar.
- **Caching en la preparación**, con `persist_result=True`. Sin persistencia el
  caché no sobrevive entre corridas y el criterio 2 no se puede cumplir.
- **Artifacts** con las métricas de esa corrida, no con métricas de ejemplo.

## 4. Deployment

```bash
uv run prefect work-pool create curso-mlops --type process
uv run prefect worker start --pool curso-mlops          # otra terminal
uv run python -m taxi.flows.deploy serve                # clase
uv run python -m taxi.flows.deploy deploy --work-pool curso-mlops   # persistente
```

Schedule: `0 3 5 * *`, zona `America/Bogota`. El día 5 y no el 1 porque la TLC no
publica el mes cerrado el primer día; sin ese margen, la corrida falla siempre en
el mismo punto del calendario y el equipo aprende a ignorar la alerta.

## 5. Registra sin promover

`registrar_candidato` delega en `taxi.models.registry.registrar_candidato`: crea
la versión, le pone el alias `candidate` y el tag `validation_status=pending`. No
existe en todo el flow una llamada que mueva `champion`.

Verificación rápida:

```bash
uv run python - <<'PY'
from mlflow import MlflowClient
from taxi.config import MODELO_REGRESION
c = MlflowClient()
for alias in ("candidate", "champion"):
    try:
        print(alias, "->", c.get_model_version_by_alias(MODELO_REGRESION, alias).version)
    except Exception:
        print(alias, "-> no existe")
PY
```

Tras correr el flow, `candidate` cambia y `champion` **no**.

## 6. ADR de referencia — trigger de reentrenamiento

### Contexto

Los datos del caso guía son particiones mensuales de la NYC TLC, publicadas con
algunas semanas de rezago sobre el mes cerrado. Una partición, una vez publicada,
es inmutable. Hay labels (la duración real del viaje se conoce al terminar el
viaje), así que la performance real es medible con poco retraso; lo que llega
tarde es el **dato agregado**, no el label.

### Decisión

**Trigger por llegada de datos**, aproximado con un schedule mensual el día 5 a
las 03:00 (`America/Bogota`), más un trigger secundario por drift a partir de S07
(el reporte de Evidently sale con código distinto de cero y eso dispara el flow).

### Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| `*/2 * * * *` (lo que hacía el repo anterior) | Entre las 14:02 y las 14:04 no hay un solo dato nuevo: reentrena sobre el mismo dataset. Cuesta descarga y CPU, produce ~720 versiones diarias e ilegibiliza el registry. Y enseña el hábito contrario al correcto |
| Diario | Los datos son mensuales. 29 de cada 30 corridas no aportan información nueva |
| Solo por drift | Depende de que el monitoreo esté bien calibrado. Con umbrales flojos produce churn de modelos; con umbrales duros no se dispara nunca. Sirve como complemento, no como único trigger |
| Solo manual | Funciona hasta la primera semana con trabajo. Es lo que hay hoy y es lo que estamos corrigiendo |

### Consecuencias

- **Si reentrenamos demasiado seguido**: costo de cómputo y de red, versiones que
  se diferencian solo por ruido, historial del registry inutilizable para
  auditoría y riesgo de promover un modelo peor por variación de muestreo (de ahí
  `MEJORA_MINIMA_RELATIVA = 0.01` en el gate).
- **Si reentrenamos demasiado tarde**: el modelo sirve predicciones degradadas y
  nadie se entera, porque el sistema no tiene forma de saberlo. Es exactamente el
  escenario con el que abre S07.
- **Mitigación**: el reentrenamiento produce un candidato, no un despliegue. El
  gate de S06 decide, y el rollback es mover un alias.

## Errores frecuentes al revisar los entregables

| Síntoma | Causa habitual |
|---|---|
| "El caching no funciona" | La primera corrida no llegó a `Completed`, o `persist_result` está desactivado, o los inputs no son idénticos (una lista y una tupla dan claves distintas) |
| El deployment no aparece en la UI | Falta `prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api` |
| El deployment aparece sin próxima ejecución | Se pasó `cron` sin `timezone` y el cálculo quedó en UTC, o el schedule está pausado |
| `deploy()` falla | Falta `work_pool_name`, o no hay ningún worker escuchando ese pool |
| El flow queda en `Completed` con un run de MLflow sin modelo | El logging del modelo está envuelto en `try/except` |
