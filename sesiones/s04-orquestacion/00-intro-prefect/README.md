# 00 · Introducción a Prefect 3 — progresión escalonada

Nueve archivos, en orden. Cada uno agrega **una** cosa al anterior. La idea es
que en ningún paso haya que aprender dos conceptos a la vez.

| # | Archivo | Qué agrega | Bloquea la terminal |
|---|---|---|---|
| 1 | `flows/weather1-bare.py` | `@flow` sobre una función normal | no |
| 1b | `flows/weather1-flow.py` | variante `@flow()`; es el entrypoint de `prefect.yaml` | no |
| 2 | `workflows/my-first-task.py` | `@task`, grafo por dependencias de datos, artifact | no |
| 3 | `workflows/retries.py` | `retries` + backoff, fallo local y determinista | no |
| 4 | `flows/weather1-serve.py` | `serve()`: deployment y dashboard | **sí** |
| 5 | `flows/weather1-serve-schedule.py` | `schedules=[Cron(...)]` con timezone | **sí** |
| 6 | `flows/weather1-serve-params.py` | parámetros editables desde la UI | **sí** |
| 7 | `flows/serve-two-flows.py` | `to_deployment()` + `serve()` con varios flows | **sí** |
| 7b | `flows/serve-two-flows-scheduled.py` | dos flows, dos schedules, un proceso | **sí** |
| 8 | `flows/weather1-deploy.py` | `deploy()` + work pool + worker | no (persiste) |
| 9 | `prefect.yaml` | deployments declarativos, `prefect deploy --all` | no |

Complementos que no forman parte de la escalera pero sí de la sesión:

- `workflows/simple-artifacts.py` — artifacts de tabla y markdown en el dashboard.
- `workflows/runtime_context.py` — `prefect.runtime`: nombre del run, intento, deployment.
- `workflows/get_variable.py` — `Variable`: configuración sin volver a desplegar.
- `workflows/create_secret.py` — bloque `Secret`: credenciales fuera del repositorio.
- `workflows/openai_with_secret.py` — usar el secreto en una llamada real.
- `infrastructure/prefect-yaml-guide.md` — referencia de `prefect.yaml`.

## Puesta en marcha

```bash
# Terminal 1 — el servidor. Queda ocupada; no la cierres.
uv run prefect server start

# Terminal 2 — una sola vez: apuntar el cliente al servidor
uv run prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
```

Sin ese `config set`, cada `.serve()` levanta un servidor temporal propio y **no
aparece nada** en `http://localhost:4200`. Es el error más común de la sesión.

Para los pasos 8 y 9 hace falta, además, un work pool y un worker:

```bash
uv run prefect work-pool create curso-mlops --type process
uv run prefect worker start --pool curso-mlops        # otra terminal
```

## Qué se corrigió respecto a la versión anterior

Los cinco arreglos son material de clase: se muestran, no se esconden.

| Archivo | Estaba | Por qué era un problema |
|---|---|---|
| `prefect.yaml` | `set_working_directory: /Users/<usuario>/…` y `schedule:` singular | La ruta es del disco de quien lo escribió: `prefect deploy --all` falla en cualquier otra máquina. Y la clave canónica es `schedules:` (plural) |
| `flows/weather1-deploy.py` | `.deploy()` sin `work_pool_name` | En Prefect 3 es obligatorio: sin work pool no hay quién ejecute |
| `workflows/create_secret.py` | `Secret(value="shhh!-it's-a-secret")` | Un secreto commiteado deja de ser secreto, y borrar la línea no basta: queda en el historial y hay que rotar la credencial |
| `workflows/openai_with_secret.py` | `model="gpt-3.5-turbo"` | Modelo legacy. Los nombres de modelo se leen de configuración, no se hardcodean |
| `workflows/retries.py` | dependía de `tools-httpstatus.pickup-services.com` y de `random` | Enseñar resiliencia dependiendo de un tercero frágil, con salida no reproducible. Ahora el fallo es local, determinista y controlado por `task_run.run_count` |

También se eliminó `workflows/artifacts-ml.py`: eran siete artifacts con métricas
inventadas. Los artifacts de ML de verdad los produce el flow del caso guía
(`src/taxi/flows/training.py`), con las métricas de esa corrida.
