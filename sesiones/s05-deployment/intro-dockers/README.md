# Primer contacto con contenedores — la misma app, local y en Docker

> Pregunta que responde: **¿qué cambia exactamente cuando mi código pasa a
> ejecutarse dentro de un contenedor?**

Es el primer paso de la [sesión 5](../README.md). Aquí no hay modelo, ni MLflow,
ni registry: solo una app de FastAPI que muestra un gato. La razón es
metodológica — si aprendes Docker y *serving* de modelos al mismo tiempo, cuando
algo falle no sabrás si el problema es el `docker run`, el artefacto o el
`@champion`. Primero se aísla la mecánica.

**Tiempo:** 15 minutos. **Requisitos:** Docker en marcha, `uv` instalado.

## Objetivos

Al terminar puedes:

1. **Ejecutar** la misma aplicación en local y en un contenedor, y **nombrar** las
   tres diferencias observables (`hostname`, puerto publicado, cómo se instalaron
   las dependencias).
2. **Explicar** por qué el `Dockerfile` copia `pyproject.toml` y `uv.lock` antes
   del código, y **predecir** qué capas se reconstruyen al editar `app.py`.
3. **Justificar** por qué `0.0.0.0` es correcto dentro del contenedor y peligroso
   en un proceso local.
4. **Verificar** que el contenedor no corre como `root` y que su `HEALTHCHECK`
   reporta `healthy`.

## Archivos

| Archivo | Qué es |
|---|---|
| [`app.py`](app.py) | La app. **Una sola**, para los dos entornos |
| [`templates/index.html`](templates/index.html) | Un solo template, el color lo decide una clase CSS |
| [`pyproject.toml`](pyproject.toml) | Dependencias declaradas con rangos |
| `uv.lock` | Las versiones resueltas, con hashes. Es la fuente de verdad |
| [`Dockerfile`](Dockerfile) | La versión **mínima correcta**: una etapa, lock, no-root, healthcheck |
| [`.dockerignore`](.dockerignore) | Qué no entra al build context |

---

## Parte 1 — Local, sin Docker

```bash
cd sesiones/s05-deployment/intro-dockers
uv run app.py
```

`uv run` lee `uv.lock`, crea el entorno si no existe y ejecuta. No hay que
activar nada ni recordar un `pip install`.

Abre <http://127.0.0.1:5000>. Anota el `hostname` que muestra la página: es el
nombre de tu equipo.

Para detener: `Ctrl+C`.

### Lo que duele en esta versión

| Problema | Por qué importa en producción |
|---|---|
| Necesitas el Python correcto en el host | El servidor de despliegue puede traer otro |
| Necesitas `uv` instalado | Una dependencia más del entorno de ejecución |
| El proceso ve todo tu sistema de archivos | Sin aislamiento entre servicios |
| "En mi máquina funciona" | El entorno no es parte del artefacto |

El contenedor convierte **el entorno completo** en el artefacto que se despliega.
Eso es todo lo que hace, y es suficiente.

---

## Parte 2 — En Docker

```bash
docker build -t gatitos-app .
docker run -d -p 8080:5000 --name gatitos gatitos-app
```

Abre <http://localhost:8080>. Misma página, otro color, **otro `hostname`**: el id
corto del contenedor.

Tres verificaciones que en un servicio real son obligatorias:

```bash
# 1. No corre como root. Debe imprimir un UID distinto de 0.
docker run --rm --entrypoint sh gatitos-app -c 'id -u'

# 2. El healthcheck funciona de verdad. Espera unos segundos y mira STATUS:
#    debe decir (healthy), no (unhealthy) ni quedarse en (health: starting).
docker ps

# 3. Los logs salen. Si esto sale vacío, falta PYTHONUNBUFFERED=1.
docker logs gatitos
```

El punto 2 no es decorativo: el `docker-compose.yml` anterior de este curso
declaraba `test: ["CMD", "curl", "-f", ...]` sobre una imagen `python:3.11-slim`,
que **no trae `curl`**. El comando fallaba siempre, el contenedor quedaba
permanentemente `unhealthy` y cualquier servicio con `depends_on:
service_healthy` se colgaba esperando. Lee el `HEALTHCHECK` del
[`Dockerfile`](Dockerfile) y compara.

### La medición del cache de capas

No creas el orden de las capas: mídelo.

```bash
# Build en frío, para tener una línea base
docker build --no-cache -t gatitos-app .

# Cambia una línea de app.py (por ejemplo, agrega una URL a GATITOS) y reconstruye
docker build -t gatitos-app .
```

Compara los dos tiempos y mira qué pasos dicen `CACHED`. Después, para ver el
contraste, edita `pyproject.toml` y reconstruye: ahí sí se reinstala todo.

**Mide y compara en tu equipo.** Este material no trae cifras de segundos a
propósito: dependen de tu red, tu disco y de si la capa base ya está descargada,
y un número inventado en un README es peor que ningún número.

### Limpieza

```bash
docker stop gatitos && docker rm gatitos
```

---

## Local vs Docker, lo que de verdad cambia

| Aspecto | Local | Docker |
|---|---|---|
| Unidad que se despliega | tu código, y ojalá el mismo entorno | la imagen: código + entorno |
| Instalación de dependencias | `uv run` en tu host | `uv sync --locked` en el build |
| Interfaz de escucha | `127.0.0.1` (no expuesta a la red) | `0.0.0.0` + mapeo de puertos |
| `hostname` | tu equipo | el id del contenedor |
| Aislamiento | ninguno | namespaces de proceso, red y filesystem |
| Reproducibilidad | depende del host | la misma imagen en cualquier host |

Sobre `0.0.0.0`: **es correcto dentro del contenedor y solo ahí**. El aislamiento
lo da Docker, no el bind; sin `0.0.0.0` el `-p` no llega al proceso. En un proceso
local, en cambio, `0.0.0.0` publica el servicio en toda la red del salón sin que
nadie lo haya pedido. Por eso `app.py` usa `127.0.0.1` por defecto y el `CMD` del
`Dockerfile` pasa `0.0.0.0` explícitamente.

## Qué NO usar

| No usar | Usar | Motivo |
|---|---|---|
| `FROM python:latest` | `FROM python:3.11-slim-bookworm` | `latest` cambia bajo tus pies; el build deja de ser reproducible |
| `pip install fastapi==...` en el `Dockerfile` | `uv sync --locked` | un pin a mano cubre las dependencias directas y deja libres las transitivas |
| `COPY . .` antes de instalar | copiar `pyproject.toml`/`uv.lock` primero | cualquier cambio de código invalida la capa de dependencias |
| Sin `USER` (todo como `root`) | usuario del sistema sin privilegios | reduce el margen de una ejecución de código en el proceso |
| `HEALTHCHECK CMD curl -f ...` sobre `python:slim` | el intérprete de la imagen | `curl` no existe en esa base: el contenedor queda `unhealthy` para siempre |
| Dos copias del código, una "para Docker" | un artefacto + variables de entorno | las dos copias se desincronizan en el primer cambio |

## Siguiente paso

El [`Dockerfile` de la raíz](../../../Dockerfile) hace lo mismo que este y además:
multi-stage (el compilador no viaja a la imagen final), `ARG` de versiones, cache
mounts de BuildKit y una etapa separada para el servidor de MLflow. Ábrelos en dos
paneles: la diferencia es el contenido del [bloque A](../README.md) de la sesión.

Referencia opcional de comandos de Docker:
[`referencia/docker-comandos.md`](../../../referencia/docker-comandos.md).
