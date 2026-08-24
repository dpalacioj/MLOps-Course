# Taller S04 — Orquestar el entrenamiento y diseñar el trigger

Se puede terminar en la misma clase. Es opcional y suma al bonus del curso.
**Sobre:** tu propio repositorio de proyecto (no el del curso).
**Entregable:** un PR con el flow, el ADR y la evidencia de las mediciones.

---

## Contexto

Tu entrenamiento ya está instrumentado con MLflow (S03) y tus datos tienen un
contrato (S02). Hoy dejas de ejecutarlo a mano.

Ojo con el objetivo: no es "usar Prefect". Es que tu entrenamiento pueda correr
**sin que estés delante**, que se sepa qué pasó cuando falle y que no promueva
nada por su cuenta.

---

## 1. Convierte tu entrenamiento en un flow (≥4 tasks)

Mínimo: extraer/cargar, validar, preparar, entrenar. Evaluar y registrar cuentan
como tasks adicionales si las separas.

Requisitos:

- cada task con type hints y docstring de una línea que diga qué garantiza;
- `get_run_logger()` en las tasks, no `print` (con `log_prints=True` en el flow si
  quieres capturar prints de librerías de terceros);
- el flow devuelve un `dict` con lo que otro proceso necesitaría: `run_id`,
  versión registrada y métricas.

## 2. Resiliencia y caching donde corresponde

- `retries` **con backoff creciente** en la task que habla con la red o con el
  almacenamiento remoto. Nada de `retries` en la task de entrenamiento: reintentar
  un entrenamiento que falló por un bug de código solo gasta tiempo.
- Caching en la preparación de datos: `cache_key_fn=task_input_hash` +
  `cache_expiration`. Verifica que `persist_result` esté activo.

## 3. Un artifact con la tabla de métricas de la corrida

`create_table_artifact` con las métricas de **esa** corrida, y
`create_markdown_artifact` con el resumen. El criterio: alguien que abra el run
dentro de tres semanas tiene que poder saber qué se entrenó y con qué resultado
sin abrir un notebook.

## 4. Un deployment con schedule y un worker local

Levanta el work pool y el worker, crea el deployment y compruébalo en la UI.

```bash
uv run prefect work-pool create curso-mlops --type process
uv run prefect worker start --pool curso-mlops
```

El schedule tiene que ser **defendible**. Si tus datos llegan una vez al mes,
`0 3 5 * *` es defendible y `*/10 * * * *` no lo es.

## 5. El flow registra el candidato y NO lo promueve

Alias `candidate`. Ni una línea del flow toca `champion`. Si tu código anterior
promovía, este es el momento de quitarlo y de dejar en el commit por qué.

## 6. ADR: `docs/adr/00X-trigger-de-reentrenamiento.md`

Una página, con estas cuatro secciones:

1. **Contexto** — cada cuánto cambian tus datos, cuándo llegan, si tienes labels y
   con cuánto retraso.
2. **Decisión** — qué trigger eliges (periódico, por llegada de datos, por drift,
   por caída de performance) y con qué frecuencia o umbral concreto.
3. **Alternativas descartadas** — al menos dos, con el motivo.
4. **Consecuencias** — **qué te costaría equivocarte**: qué pasa si reentrenas
   demasiado seguido (costo, churn de modelos, registry ilegible) y qué pasa si
   reentrenas demasiado tarde (predicciones degradadas sin que nadie se entere).

Ancla la discusión en esta tabla y di explícitamente en qué fila caes:

| Estrategia | Cuándo tiene sentido | Riesgo principal |
|---|---|---|
| Periódico (semanal/mensual) | los datos cambian de forma gradual | reentrena sin necesidad; cuesta |
| Por llegada de datos | llegan particiones (el caso del curso) | hay que detectar la disponibilidad |
| Por drift detectado | los cambios son impredecibles | falsos positivos → churn de modelos |
| Por caída de performance | hay labels en producción | los labels llegan tarde (*label lag*) |

---

## Criterios de aceptación (medibles)

| # | Criterio | Cómo lo verificas | Evidencia que entregas |
|---|---|---|---|
| 1 | El flow corre end-to-end sin intervención | un solo comando, termina en `Completed` | captura del run o salida de la terminal |
| 2 | La segunda ejecución es más rápida por caching, **y lo mides** | cronometras las dos ejecuciones y comparas | los dos tiempos y el factor: `t1 = … s`, `t2 = … s`, `t1/t2 = …` |
| 3 | El deployment aparece en la UI con su **próxima ejecución** | Deployments → tu deployment → *Next run* | captura con la fecha y hora de la próxima corrida |
| 4 | El flow registra sin promover | `get_model_version_by_alias(modelo, "champion")` **no cambia** tras correr el flow | la versión de `champion` antes y después |
| 5 | Los retries tienen backoff creciente | `retry_delay_seconds` es una lista ascendente | la línea del decorador |
| 6 | El artifact de métricas existe y corresponde a esa corrida | Runs → tu run → *Artifacts* | captura de la tabla |
| 7 | El ADR tiene las cuatro secciones y una frecuencia concreta | lectura | el archivo en el PR |

### Sobre el criterio 2: medir, no asumir

Nadie te va a creer "el caching funciona" sin números, y con red variable el
número puede ser cualquiera. Mide así:

```bash
# primera ejecución (llena el caché)
time uv run python -m mi_proyecto.flows.training

# segunda ejecución (debería reusar)
time uv run python -m mi_proyecto.flows.training
```

O usa el script del caso guía como plantilla:
`01-pipeline-ml/medir_caching.py`, que ejecuta la task dos veces en el mismo
proceso e imprime los tiempos y el factor de aceleración.

Si la segunda ejecución **no** fue más rápida, eso también es un resultado válido
del taller — siempre que expliques por qué. Revisa en este orden: que la primera
corrida terminara en `Completed`, que `persist_result` esté activo, que no haya
expirado `cache_expiration` y que los inputs sean idénticos.

---

## Qué NO entregar

- Un schedule de minutos reentrenando el modelo completo.
- Un flow que promueva a `champion`.
- `prefect agent start`, `Deployment.build_from_flow`, `schedule=` singular.
- Rutas absolutas de tu máquina en `prefect.yaml` (el pre-commit del curso lo
  bloquea, y por algo).
