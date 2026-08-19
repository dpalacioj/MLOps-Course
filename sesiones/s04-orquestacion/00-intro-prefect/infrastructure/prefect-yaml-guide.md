# Guía de `prefect.yaml` (Prefect 3)

`prefect.yaml` declara **deployments**: qué flow, con qué parámetros, en qué work
pool y con qué schedule. Es la alternativa declarativa a llamar `.deploy()` desde
Python, y su ventaja real es que el archivo se revisa en un pull request: un
cambio de schedule o de parámetros deja de ser un comando que alguien ejecutó una
vez en su portátil.

> Verificado contra Prefect **3.8.3**.

## Estructura mínima

```yaml
name: nombre-del-proyecto
prefect-version: 3.8.3

deployments:
  - name: mi-deployment
    entrypoint: ruta/al/archivo.py:mi_flow    # relativa a este archivo
    work_pool:
      name: curso-mlops
    schedules:
      - cron: "0 3 5 * *"
        timezone: America/Bogota
    parameters:
      particion: "2023-01"
```

Dos reglas que evitan el 90 % de los problemas:

1. **`schedules:` en plural, y es una lista.** El `schedule:` singular con un mapa
   `cron`/`timezone` es la forma heredada de Prefect 2. Está deprecada, y si el
   deployment declara las dos claves, `prefect deploy` falla.
2. **Nada de rutas absolutas.** Un `pull` con `set_working_directory:
   /Users/<alguien>/…` hace que el archivo solo funcione en la máquina de quien
   lo escribió. Ese error estaba en este mismo curso; el hook
   `scripts/hooks/sin_rutas_absolutas.py` ahora lo bloquea antes del commit.

## Trabajo con work pools

`prefect deploy` requiere un work pool porque quien ejecuta el flow es un
**worker**, no el proceso que hizo el deploy. Los work pools son parte del
producto open source (la versión anterior de esta guía decía "requires paid
plan", que es falso):

```bash
prefect work-pool create curso-mlops --type process   # o docker, kubernetes, …
prefect worker start --pool curso-mlops
```

Los **agents** (`prefect agent start`) fueron eliminados en Prefect 3. Si un
tutorial los menciona, está escrito para Prefect 2.

## Tipos de schedule

```yaml
schedules:
  - cron: "0 2 * * *"          # diario a las 02:00
    timezone: America/Bogota
  - interval: 3600             # cada hora, en segundos
    timezone: America/Bogota
  - rrule: "FREQ=WEEKLY;BYDAY=MO,WE,FR"
    timezone: America/Bogota
```

Un deployment puede tener varios schedules, y cada uno puede llevar sus propios
`parameters` y un `slug` para identificarlo. Sin `timezone`, el cron se
interpreta en UTC: es el motivo habitual de "el pipeline corrió cinco horas
antes de lo que dice el enunciado".

## Pasos `build`, `push` y `pull`

Son los tres ganchos del ciclo de despliegue, y solo hacen falta cuando el worker
**no** comparte disco con el código:

| Sección | Cuándo se usa | Ejemplo típico |
|---|---|---|
| `build` | construir la imagen del contenedor | `prefect_docker.deployments.steps.build_docker_image` |
| `push` | publicarla en un registry | `prefect_docker.deployments.steps.push_docker_image` |
| `pull` | que el worker consiga el código | `prefect.deployments.steps.git_clone` |

En local, con un work pool de tipo `process`, las tres se pueden omitir.

## Ejemplo completo del caso guía

```yaml
name: caso-guia-taxi
prefect-version: 3.8.3

deployments:
  - name: entrenamiento-mensual
    entrypoint: src/taxi/flows/training.py:entrenamiento_flow
    description: Reentrena y registra el candidato. No promueve.
    work_pool:
      name: curso-mlops
    schedules:
      - cron: "0 3 5 * *"          # día 5, 03:00 — margen tras la publicación
        timezone: America/Bogota
    parameters:
      registrar: true

  - name: batch-mensual
    entrypoint: src/taxi/flows/batch.py:batch_flow
    work_pool:
      name: curso-mlops
    schedules:
      - cron: "0 4 6 * *"
        timezone: America/Bogota
    parameters:
      particion: "2023-07"
```

## Comandos

```bash
prefect deploy --all                       # todos los deployments del archivo
prefect deploy -n entrenamiento-mensual    # uno solo
prefect deployment ls
prefect deployment inspect 'entrenamiento-taxi/entrenamiento-mensual'
prefect deployment run 'entrenamiento-taxi/entrenamiento-mensual'
prefect deployment run 'entrenamiento-taxi/entrenamiento-mensual' --param registrar=false
prefect deployment delete 'entrenamiento-taxi/entrenamiento-mensual'
```

Validar el YAML antes de desplegar (el pre-commit del repo hace esto):

```bash
uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('prefect.yaml').read_text())"
```

## Cuándo `prefect.yaml` y cuándo Python

| Situación | Mejor opción |
|---|---|
| Clase, laboratorio, una carga en una máquina | `flow.serve(...)` |
| Varios deployments del mismo flow, revisados en PR | `prefect.yaml` |
| Deployments generados dinámicamente (uno por cliente, por región) | `flow.deploy(...)` en Python |
| Necesitas construir y publicar una imagen por corrida | `prefect.yaml` con `build`/`push` |

## Documentación oficial

- Deployments: <https://docs.prefect.io/v3/concepts/deployments>
- `prefect.yaml`: <https://docs.prefect.io/v3/how-to-guides/deployments/prefect-yaml>
- Work pools y workers: <https://docs.prefect.io/v3/concepts/work-pools>
- Schedules: <https://docs.prefect.io/v3/concepts/schedules>
