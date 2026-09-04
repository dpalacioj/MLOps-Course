# Primer contacto con contenedores — la misma app, local y en Docker

> Pregunta que responde: **¿qué cambia exactamente cuando mi código pasa a
> ejecutarse dentro de un contenedor?**

Es el paso 2 del [recorrido de la sesión 5](../README.md#el-recorrido). Aquí no
hay modelo, ni MLflow, ni registry: solo una app web que muestra la foto de un
gato. La razón es metodológica: si aprendes Docker y *serving* de modelos al mismo
tiempo, cuando algo falle no sabrás si el problema es el `docker run`, el artefacto
o el `@champion`. Primero se aísla la mecánica.

**Tiempo:** 15 minutos. **Requisitos:** Docker Desktop abierto, `uv` instalado.
**Terminal:** una sola, y todos los comandos se corren **desde esta carpeta**.

## Qué es un contenedor, en una frase

Un contenedor es un proceso normal de tu sistema operativo al que Docker le
muestra un sistema de archivos propio, una red propia y una lista de procesos
propia. No es una máquina virtual: no hay otro kernel, por eso arranca en
milisegundos. La analogía útil es un **departamento amoblado**: llegas, ya está
todo lo que necesitas dentro, y lo que hagas ahí no toca el resto del edificio.

La **imagen** es el plano del departamento (código + dependencias + intérprete,
congelados). El **contenedor** es un departamento construido a partir de ese plano
y en uso. De una imagen puedes correr diez contenedores idénticos.

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
5. **Diagnosticar** un contenedor que reporta `(healthy)` y no responde, y
   **nombrar** por qué el tag de una imagen no dice qué hay dentro.

## Archivos

No hay orden entre ellos: son las piezas de una sola app.

| Archivo | Qué es |
|---|---|
| [`app.py`](app.py) | La app. **Una sola**, para los dos entornos |
| [`templates/index.html`](templates/index.html) | Un solo template; el color lo decide una clase CSS |
| [`pyproject.toml`](pyproject.toml) | Dependencias declaradas con rangos |
| `uv.lock` | Las versiones resueltas, con hashes. Es la fuente de verdad |
| [`Dockerfile`](Dockerfile) | La versión **mínima correcta**: una etapa, lock, no-root, healthcheck |
| [`.dockerignore`](.dockerignore) | Qué no entra al *build context* |

---

## Parte 1 — Local, sin Docker

```bash
cd sesiones/s05-deployment/intro-dockers
uv run app.py
```

`uv run` lee `uv.lock`, crea el entorno si no existe (la primera vez tarda unos
segundos e imprime `Creating virtual environment at: .venv` e `Installed 21
packages`) y ejecuta. No hay que activar nada ni recordar un `pip install`.

**Qué debes ver en esta terminal.** El proceso se queda esperando; eso es lo
correcto, es un servidor:

```
Gatitos App en http://127.0.0.1:5000  (entorno=local)
INFO:     Started server process [20445]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:5000 (Press CTRL+C to quit)
```

Abre <http://127.0.0.1:5000>. Anota el `hostname` que muestra la página: es el
nombre de tu equipo. Y en otra pestaña, <http://127.0.0.1:5000/health> devuelve:

```json
{"status":"ok","entorno":"local","hostname":"Mac.lan"}
```

Para detener: `Ctrl+C`.

> **En macOS, el puerto 5000 ya lo usa AirPlay Receiver** (escucha en todas las
> interfaces). La app arranca de todos modos porque escucha solo en `127.0.0.1`.
> Si aun así ves `ERROR: [Errno 48] Address already in use`, elige otro puerto:
> `PUERTO=5050 uv run app.py` y abre <http://127.0.0.1:5050>.

### Lo que duele en esta versión

| Problema | Por qué importa en producción |
|---|---|
| Necesitas el Python correcto en el host | El servidor de despliegue puede traer otro |
| Necesitas `uv` instalado | Una dependencia más del entorno de ejecución |
| El proceso ve todo tu sistema de archivos | Sin aislamiento entre servicios |
| "En mi máquina funciona" | El entorno no es parte del artefacto |

El contenedor convierte **el entorno completo** en el artefacto que se despliega.
Eso es todo lo que hace, y es suficiente.

**Cuándo no hace falta.** Si el único consumidor eres tú, en tu máquina, un
`uv run` alcanza. El contenedor se paga con un build de minutos, una imagen de
cientos de MB y un demonio que tiene que estar corriendo; vale la pena cuando el
código tiene que correr en una máquina que no controlas.

---

## Parte 2 — En Docker

### Antes de construir: comprueba dónde estás

El punto final de `docker build -t gatitos-app .` significa **"usa este
directorio"**. No es decoración: es lo que decide qué `Dockerfile` se lee. Este
repositorio tiene dos, y construir el equivocado es el error más común de todo el
paso. Dos segundos de comprobación:

```bash
pwd                    # debe terminar en sesiones/s05-deployment/intro-dockers
ls Dockerfile app.py   # los dos archivos tienen que estar AQUÍ
```

```
.../MLOps-Course/sesiones/s05-deployment/intro-dockers
Dockerfile	app.py
```

Tu `pwd` imprime la ruta completa desde la raíz de tu disco; lo que importa son
los tres últimos tramos.

Si `pwd` te devuelve la raíz del repositorio, vuelve con
`cd sesiones/s05-deployment/intro-dockers`.

### El error, hecho a propósito

Antes de construir bien, constrúyelo mal. Cuesta cinco segundos y es la única
forma de reconocerlo cuando te pase de verdad. **Desde la raíz del
repositorio:**

```bash
cd ../../..            # a la raíz del repositorio
docker build -t gatitos-app .
```

**Mira las primeras líneas y cancela con `Ctrl+C` en cuanto las leas.** No hace
falta esperar: el error ya está a la vista.

| Build correcto, desde `intro-dockers` | Build equivocado, desde la raíz |
|---|---|
| `#8 [stage-0 1/8] FROM python:3.11-slim` | `#7 [builder 1/8] FROM python:3.11-slim` |
| — | `#8 [uv-bin 1/1] FROM ghcr.io/astral-sh/uv` |
| ocho pasos, una sola etapa sin nombre | veinte pasos y etapas con nombre |

**La señal que lo delata:** las etiquetas entre corchetes. `stage-0` es la única
etapa de este ejemplo. `builder` y `uv-bin` son etapas del `Dockerfile` de la
raíz, que construye la API del curso. Si ves un nombre de etapa que no
reconoces, estás construyendo otra cosa.

**Y si no lo cancelas**, esto es exactamente lo que pasa, y es lo que hay que
aprender a reconocer:

```bash
docker run -d -p 8080:5000 --name gatitos gatitos-app
docker ps
curl -sS http://localhost:8080
```

```
NAMES     IMAGE         STATUS                   PORTS
gatitos   gatitos-app   Up 8 seconds (healthy)   0.0.0.0:8080->5000/tcp

curl: (56) Recv failure: Connection reset by peer
```

**Léelo dos veces: el contenedor dice `(healthy)` y no sirve nada.** Es el
momento más útil de este ejemplo. El `HEALTHCHECK` que trae esa imagen consulta
el puerto 8000 *por dentro*, donde sí hay un servidor, así que reporta salud con
toda honestidad. Lo que no puede saber es que tú publicaste el 5000, donde no hay
nadie escuchando. **Un healthcheck solo prueba lo que le pediste probar.**

Los logs son los que cantan la verdad:

```bash
docker logs gatitos
```

```
INFO:     Started server process [1]
2026-09-03 14:21:05,650 INFO taxi.api.main Arrancando API version=1.0.0 uri_modelo=ninguno
2026-09-03 14:21:05,650 WARNING taxi.api.modelo Arranque SIN modelo (TAXI_MODELO_URI=ninguno).
```

Ni una palabra de gatos: dice `taxi.api.main` y `uri_modelo`. Esa es la
confirmación. Y para verlo sin ambigüedad, pregúntale a la imagen qué es:

```bash
docker image inspect gatitos-app   --format 'titulo={{index .Config.Labels "org.opencontainers.image.title"}} cmd={{.Config.Cmd}}'
docker images gatitos-app --format '{{.Size}}'
```

```
titulo=nyc-taxi-duration-api cmd=[uvicorn taxi.api.main:app --host 0.0.0.0 --port 8000]
3.33GB
```

La app de gatitos pesa unos 370 MB, arranca `uvicorn app:app` y escucha en el
5000. Nada de eso coincide. **El tag `gatitos-app` es un nombre que le pusiste
tú; no dice nada de lo que hay dentro.** Es la misma idea que la sesión trabaja
con `:latest` frente al digest, en miniatura y en tu propia terminal.

### La corrección

Si cancelaste el build con `Ctrl+C`, no quedó ninguna imagen y basta con volver a
la carpeta correcta:

```bash
cd sesiones/s05-deployment/intro-dockers    # desde la raíz del repositorio
docker build -t gatitos-app .
docker images gatitos-app --format '{{.Size}}'    # ~370 MB, no 3.33 GB
```

Si lo dejaste terminar, primero se retira lo que quedó mal etiquetado. Los dos
`|| true` están porque cada comando falla si eso ya no existe, y aquí da igual:

```bash
docker rm -f gatitos || true       # el contenedor equivocado
docker rmi gatitos-app || true     # la imagen con el nombre de otra cosa
cd sesiones/s05-deployment/intro-dockers
docker build -t gatitos-app .
docker run -d -p 8080:5000 --name gatitos gatitos-app
```

Con la imagen correcta, `curl -s http://127.0.0.1:8080/health` responde
`{"status":"ok","entorno":"docker",...}` y el tamaño baja a unos 370 MB. Ese es el
estado desde el que sigue el resto de la parte 2.

### Qué hace cada comando

`docker build` lee el `Dockerfile` **de este directorio** y produce una imagen
llamada `gatitos-app`. La primera vez descarga la imagen base de Python (unos 50 MB) y tarda un par de
minutos; imprime una línea por paso, todos con la etiqueta `stage-0`
(`[4/8] COPY pyproject.toml uv.lock ./`, `[5/8] RUN uv sync --locked --no-dev`…)
y termina con `naming to docker.io/library/gatitos-app:latest`.

`docker run -d` arranca un contenedor **en segundo plano** (por eso la terminal
no se bloquea, a diferencia de la parte 1) e imprime solo su id, una línea de 64
caracteres hexadecimales. `-p 8080:5000` conecta el puerto 8080 de tu equipo con
el 5000 de adentro del contenedor.

Abre <http://localhost:8080>. Misma página, otro color, **otro `hostname`**: los
12 primeros caracteres del id del contenedor.

```bash
curl -s http://127.0.0.1:8080/health
```

```json
{"status":"ok","entorno":"docker","hostname":"5b431b54e07f"}
```

Si la foto del gato no carga, es porque viene de un servicio público
(`cataas.com`) y no hay red. La página muestra un recuadro gris en su lugar y
todo lo demás sigue funcionando: la demo es sobre el contenedor, no sobre el gato.

### Tres verificaciones que en un servicio real son obligatorias

```bash
# 1. No corre como root. Debe imprimir un UID distinto de 0.
docker run --rm --entrypoint sh gatitos-app -c 'id -u'

# 2. El healthcheck funciona de verdad. Mira la columna STATUS.
docker ps

# 3. Los logs salen. Si esto sale vacío, falta PYTHONUNBUFFERED=1.
docker logs gatitos
```

**Qué debes ver:**

```
1001
```

```
NAMES     IMAGE         STATUS                    PORTS
gatitos   gatitos-app   Up 12 seconds (healthy)   0.0.0.0:8080->5000/tcp
```

```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:5000 (Press CTRL+C to quit)
INFO:     127.0.0.1:51230 - "GET /health HTTP/1.1" 200 OK
```

Durante los primeros 10 segundos `docker ps` dice `(health: starting)`: es el
`--start-period` del `HEALTHCHECK`, el tiempo de gracia antes de la primera
comprobación. Después tiene que decir `(healthy)`. Si dice `(unhealthy)`, el
comando del healthcheck está fallando; la forma de verlo:

```bash
docker inspect --format '{{json .State.Health.Log}}' gatitos | jq
```

La línea `GET /health` del log que ves **sin haberla pedido tú** es el propio
healthcheck consultando al proceso cada 15 segundos. Fíjate también en `Started
server process [1]`: dentro del contenedor, uvicorn es el proceso número 1. No
hay nada más corriendo.

**El atajo tentador del healthcheck** es `HEALTHCHECK CMD curl -f http://...`.
Sobre una imagen `python:*-slim`, que **no trae `curl`**, ese comando falla
siempre: el contenedor queda permanentemente `unhealthy` y cualquier otro servicio
que dependa de él con `depends_on: service_healthy` se queda esperando para
siempre. Compruébalo: `docker run --rm --entrypoint sh gatitos-app -c 'command -v
curl || echo sin curl'` imprime `sin curl`. Por eso el `HEALTHCHECK` del
[`Dockerfile`](Dockerfile) usa el intérprete de Python que ya está en la imagen.

### La medición del cache de capas

Una imagen se construye por **capas**: cada instrucción del `Dockerfile` produce
una, y Docker reutiliza las capas cuyas entradas no cambiaron. Es como una
receta guardada por pasos: si solo cambias el paso 5, los pasos 1 a 4 ya están
hechos. No creas el orden de las capas: mídelo.

```bash
# Build en frío, para tener una línea base
docker build --no-cache -t gatitos-app .

# Cambia una línea de app.py (por ejemplo, agrega una URL a GATITOS) y reconstruye
docker build -t gatitos-app .
```

En el segundo build, los pasos que dicen `CACHED` son los que no se rehicieron.
Tiene que verse así: `CACHED [4/8] COPY pyproject.toml uv.lock ./`, `CACHED [5/8]
RUN uv sync --locked --no-dev`, y a partir de `[6/8] COPY app.py ./` todo se
reconstruye. Es decir: **cambiar código no reinstala dependencias.** Después,
para ver el contraste, edita `pyproject.toml` (basta un comentario) y
reconstruye: ahí sí se reinstala todo, porque la capa 4 cambió y todas las
siguientes dependen de ella.

**Mide y compara en tu equipo.** Este material no trae cifras de segundos a
propósito: dependen de tu red, tu disco y de si la capa base ya está descargada,
y un número inventado en un README es peor que ningún número.

### Limpieza

Un contenedor con `-d` sigue corriendo aunque cierres la terminal, y una imagen
ocupa disco hasta que la borres. Nada de esto se va solo:

```bash
docker stop gatitos && docker rm gatitos   # el contenedor
docker rmi gatitos-app                     # la imagen (opcional; pesa ~370 MB)
```

---

## Local vs Docker, lo que de verdad cambia

| Aspecto | Local | Docker |
|---|---|---|
| Unidad que se despliega | tu código, y ojalá el mismo entorno | la imagen: código + entorno |
| Instalación de dependencias | `uv run` en tu host | `uv sync --locked` en el build |
| Interfaz de escucha | `127.0.0.1` (no expuesta a la red) | `0.0.0.0` + mapeo de puertos |
| `hostname` | tu equipo | el id del contenedor |
| Aislamiento | ninguno | *namespaces* de proceso, red y sistema de archivos |
| Reproducibilidad | depende del host | la misma imagen en cualquier host |

Sobre `0.0.0.0`: es la forma de decir "escucha en todas las interfaces de red".
**Es correcto dentro del contenedor y solo ahí**: el aislamiento lo da Docker, no
el bind, y sin `0.0.0.0` el `-p` no llega al proceso. En un proceso local, en
cambio, `0.0.0.0` publica el servicio en toda la red del salón sin que nadie lo
haya pedido. Por eso `app.py` usa `127.0.0.1` por defecto y el `CMD` del
`Dockerfile` pasa `0.0.0.0` explícitamente.

## Errores que vas a ver, y qué significan

| Mensaje | Causa | Arreglo |
|---|---|---|
| `Cannot connect to the Docker daemon at unix:///.../docker.sock` | Docker Desktop no está abierto | ábrelo y espera a que el ícono deje de animarse |
| `Bind for 0.0.0.0:8080 failed: port is already allocated` | otro contenedor o proceso usa el 8080 | `docker ps` para ver quién, o usa `-p 8081:5000` |
| `Conflict. The container name "/gatitos" is already in use` | quedó un contenedor de una corrida anterior | `docker rm -f gatitos` y vuelve a correr |
| `ERROR: [Errno 48] Address already in use` (local) | el 5000 está ocupado en tu equipo | `PUERTO=5050 uv run app.py` |
| `docker ps` dice `(unhealthy)` | el comando del `HEALTHCHECK` falla | `docker inspect --format '{{json .State.Health.Log}}' gatitos \| jq` |
| `curl: (56) Recv failure: Connection reset by peer`, con el contenedor en `(healthy)` | construiste el `Dockerfile` de la raíz: la imagen escucha en otro puerto | ver [El error, hecho a propósito](#el-error-hecho-a-propósito) |
| El build imprime pasos `[builder ...]` o `[uv-bin ...]` | estás en la raíz del repositorio, no en esta carpeta | `Ctrl+C` y `cd sesiones/s05-deployment/intro-dockers` |
| `docker logs gatitos` habla de `taxi.api.main` | el tag dice `gatitos-app` pero la imagen es otra | `docker rmi gatitos-app` y reconstruye desde esta carpeta |

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
*multi-stage* (el compilador no viaja a la imagen final), `ARG` de versiones,
*cache mounts* de BuildKit y una etapa separada para el servidor de MLflow. Ábrelos
en dos paneles: la diferencia es el contenido del paso 3 del
[recorrido](../README.md#el-recorrido).

Referencia opcional de comandos de Docker:
[`referencia/docker-comandos.md`](../../../referencia/docker-comandos.md).
