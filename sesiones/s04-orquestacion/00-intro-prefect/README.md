# 00 · Introducción a Prefect 3 — progresión escalonada

Nueve archivos, en orden. Cada uno agrega **una** cosa al anterior. La idea es
que en ningún paso haya que aprender dos conceptos a la vez.

| # | Archivo | Qué agrega | Bloquea la terminal |
|---|---|---|---|
| 1 | `pasos/01-flow.py` | `@flow` sobre una función normal | no |
| 1b | `pasos/01b-flow-entrypoint.py` | variante `@flow()`; es el entrypoint de `prefect.yaml` | no |
| 2 | `pasos/02-task.py` | `@task`, grafo por dependencias de datos, artifact | no |
| 3 | `pasos/03-reintentos.py` | `retries` + backoff, fallo local y determinista | no |
| 4 | `pasos/04-serve.py` | `serve()`: deployment y dashboard | **sí** |
| 5 | `pasos/05-serve-schedule.py` | `schedules=[Cron(...)]` con timezone | **sí** |
| 6 | `pasos/06-serve-parametros.py` | parámetros editables desde la UI | **sí** |
| 7 | `pasos/07-dos-flows.py` | `to_deployment()` + `serve()` con varios flows | **sí** |
| 7b | `pasos/07b-dos-flows-schedule.py` | dos flows, dos schedules, un proceso | **sí** |
| 8 | `pasos/08-deploy.py` | `deploy()` + work pool + worker | no (persiste) |
| 9 | `prefect.yaml` | deployments declarativos, `prefect deploy --all` | no |

Complementos que no forman parte de la escalera pero sí de la sesión:

- `extras/simple-artifacts.py` — artifacts de tabla y markdown en el dashboard.
- `extras/runtime_context.py` — `prefect.runtime`: nombre del run, intento, deployment.
- `extras/get_variable.py` — `Variable`: configuración sin volver a desplegar.
- `extras/create_secret.py` — bloque `Secret`: credenciales fuera del repositorio.
- `extras/openai_with_secret.py` — usar el secreto en una llamada real.
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

Y el segundo error más común es su consecuencia: **el `config set` es permanente**,
queda en el perfil. A partir de ahí *todos* los flows exigen el servidor —incluido
`00-escalera/3-orquestador.py`, que sin la variable correría contra una API
efímera—. Si la Terminal 1 no está arriba, el traceback termina así:

```
RuntimeError: Failed to reach API at http://127.0.0.1:4200/api/
```

Se lee la última línea y se ignoran las sesenta anteriores: son `httpx` contando
cómo intentó conectarse. El arreglo es levantar el servidor, no tocar el código.
Para volver al modo sin servidor:

```bash
uv run prefect config unset PREFECT_API_URL
```

Para los pasos 8 y 9 hace falta, además, un work pool y un worker:

```bash
uv run prefect work-pool create curso-mlops --type process
uv run prefect worker start --pool curso-mlops        # otra terminal
```

## Cinco trampas de este material, y por qué se evitan

Son los cinco errores más comunes al escribir Prefect, y cada archivo de la
progresión está construido para no cometerlos. Vale mostrarlos: se reconocen
fácil en el código de cualquiera.

| Trampa | Cómo se ve | Por qué es un problema |
|---|---|---|
| Rutas absolutas en `prefect.yaml` | `set_working_directory: /Users/<usuario>/…` | Es la ruta del disco de quien lo escribió: `prefect deploy --all` falla en cualquier otra máquina |
| `schedule:` singular | un mapa `cron`/`timezone` estilo Prefect 2 | La clave canónica es `schedules:` (plural, una lista). Si aparecen las dos, el deploy falla |
| `.deploy()` sin `work_pool_name` | falta el argumento | En Prefect 3 es obligatorio: sin work pool no hay quién ejecute |
| Un secreto en el código | `Secret(value="shhh!-it's-a-secret")` | Deja de ser secreto, y borrar la línea no basta: queda en el historial y hay que rotar la credencial |
| Simular fallos contra un tercero | un endpoint público que devuelve 500 | Enseñar resiliencia dependiendo de un servicio frágil, con salida no reproducible. Aquí el fallo es local y determinista, controlado por `task_run.run_count` |

Y una decisión sobre los artifacts: los de esta carpeta muestran **mecánica**
(cómo se crea una tabla, cómo se crea un markdown), con datos de juguete y sin
fingir que son métricas de un modelo. Los artifacts de ML de verdad los produce
el flow del caso guía (`src/taxi/flows/training.py`), con las métricas reales de
esa corrida. Inventar métricas en un ejemplo enseña a no confiar en ninguna.
