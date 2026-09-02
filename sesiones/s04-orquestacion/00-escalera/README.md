# 00 · La escalera: script → cron → orquestador

> Se abre **antes** de [`00-intro-prefect/`](../00-intro-prefect/). Es la sección
> 1 del [README de la sesión](../README.md) —"el dolor"— convertida en tres
> archivos que se ejecutan. Sirve para responder, con números en pantalla, la
> pregunta que siempre aparece: *"¿por qué no simplemente pongo un cron?"*

```
SCRIPT                                                         1-script.py
"ejecuta código"
        │
        │  + lo ejecuta a cierta hora, sin nadie delante
        ↓
CRON                                                              2-cron/
"ejecuta código a cierta hora"
        │
        │  + reintenta, deja historia, tiene estado por paso, acepta parámetros
        ↓
ORQUESTADOR                                                3-orquestador.py
"administra todo el workflow"
```

Cada peldaño es un archivo. Los tres ejecutan **el mismo pipeline de tres pasos**,
que vive en [`pasos.py`](pasos.py) y no cambia entre peldaños. Eso es lo que hay
que ver: el código que hace el trabajo es idéntico; lo que cambia es **quién lo
ejecuta y qué queda registrado cuando termina**.

## Los archivos

| Archivo | Peldaño | Qué agrega |
|---|---|---|
| [`pasos.py`](pasos.py) | — | los tres pasos: descargar, preparar, resumir. Compartido por los tres peldaños |
| [`1-script.py`](1-script.py) | SCRIPT | tres llamadas a función, en orden. Python puro |
| [`2-cron/`](2-cron/) | CRON | el envoltorio y la línea de crontab que hacen falta para que corra solo, más [`programar.sh`](2-cron/programar.sh), que la programa para dentro de cuatro minutos |
| [`3-orquestador.py`](3-orquestador.py) | ORQUESTADOR | `@flow`, `@task` y `retries` sobre las mismas tres funciones |

El pipeline de `pasos.py` **no entrena nada**: genera, filtra y agrega un CSV de
dos millones de filas. Tiene tres pasos, un costo real medible y un fallo
inyectable, que es todo lo que la demo necesita. El pipeline de ML de verdad es
[`src/taxi/flows/training.py`](../../../src/taxi/flows/training.py), y llega en
[`01-pipeline-ml/`](../01-pipeline-ml/).

## La demo

Desde esta carpeta. Nada necesita red.

### Peldaño 1 — el script

```bash
uv run python 1-script.py
```

Funciona. Cuatro segundos, tres líneas de `print`, y nada más.

```bash
ESCALERA_FALLAR_EN=3 uv run python 1-script.py
```

El paso 3 falla con un `ConnectionError`. Sale un traceback y el proceso muere con
código 1. Los pasos 1 y 2 habían terminado bien, y ese trabajo se perdió: para
completar el pipeline hay que relanzarlo entero.

### Peldaño 2 — cron, corriendo solo en cuatro minutos

```bash
2-cron/programar.sh --instalar
tail -f "$HOME/escalera-cron.log"
```

(Sin `cd`: el script resuelve su propia ubicacion y funciona desde cualquier
directorio. Si ya estas dentro de `2-cron/`, es `./programar.sh --instalar`.)

`programar.sh` calcula la hora de dentro de cuatro minutos, arma la línea del
crontab con tu ruta absoluta y la instala. Los cuatro minutos son para explicar la
tabla de fallos de [`2-cron/README.md`](2-cron/README.md): cuando llegue la hora, el
bloque aparece solo en el `tail -f`, sin que nadie toque el teclado.

Al terminar, `./programar.sh --quitar`. Un crontab no tiene disparo único y esa
línea volvería a disparar mañana a la misma hora.

**Si estás en macOS y el repo está en `~/Documents`, `~/Desktop` o `~/Downloads`,
esto falla** con `Operation not permitted`, y falla en silencio: no se crea
ningún log, porque el redirect vive dentro de `correr.sh` y el script no llega a
ejecutarse. Se arregla de dos formas —mover el repo fuera de esas carpetas, o
darle Acceso total al disco a `/usr/sbin/cron` y reiniciarlo—, y ambas están
paso a paso en [`2-cron/README.md`](2-cron/README.md). `programar.sh` detecta el
caso y `./programar.sh --ver` te dice si quedó bien.

### Peldaño 3 — el orquestador

```bash
ESCALERA_FALLAR_EN=3 uv run python 3-orquestador.py
```

El mismo fallo, en el mismo paso. Prefect lo reintenta al segundo, el segundo
intento pasa, **los pasos 1 y 2 no se vuelven a ejecutar**, y el flow termina en
`Completed`.

### Salida esperada del peldaño 3

```
Beginning flow run 'tireless-pelican' for flow 'escalera-peldano-3'
View at http://127.0.0.1:4200/runs/flow-run/0135e5f2-...
Task run 'descargar-96c' -   paso 1: 2000000 filas -> crudo.csv
Task run 'descargar-96c' - Finished in state Completed()
Task run 'preparar-48c' -   paso 2: 1174856 filas conservadas -> limpio.csv
Task run 'preparar-48c' - Finished in state Completed()
Task run 'resumir-6c1' - Task run failed with exception: ConnectionError(...) - Retry 1/2 will start 1 second(s) from now
Task run 'resumir-6c1' -   (el fallo del paso 3 era transitorio; intento 2 pasa)
Task run 'resumir-6c1' -   paso 3: {'filas': 1174856, ...} -> resumen.json
Task run 'resumir-6c1' - Finished in state Completed()
Flow run 'tireless-pelican' - Finished in state Completed()
```

Los nombres de las corridas (`tireless-pelican`) los inventa Prefect y cambian en
cada ejecución. Los números no: el pipeline es determinista, así que
`1174856 filas` y `velocidad_media_kmh: 26.56` deben salir iguales en cualquier
máquina.

Si en vez de eso sale `RuntimeError: Failed to reach API at
http://127.0.0.1:4200/api/`, es que ya se corrió el `prefect config set` del
[README de `00-intro-prefect/`](../00-intro-prefect/README.md) y el cliente está
apuntando a un servidor que no está arriba. Se arregla levantándolo con
`make prefect`. Sin ese `config set`, Prefect arranca un servidor temporal él solo
y el flow corre igual.

## La medición

En un MacBook con chip M, y el resto de la máquina en reposo. Los tiempos
absolutos varían; lo que no varía es qué pasos se ejecutaron.

| Peldaño | Comando | Tiempo | Pasos ejecutados | Estado final |
|---|---|---|---|---|
| 1 | `ESCALERA_FALLAR_EN=3 … 1-script.py` | 3,4 s | 1, 2, y 3 muere | traceback, código 1 |
| 1 | relanzarlo para completar | + 4,0 s | 1, 2, 3 **otra vez** | termina, con 3,4 s de trabajo repetido |
| 3 | `ESCALERA_FALLAR_EN=3 … 3-orquestador.py` (servidor temporal) | 12,7 s | 1, 2, 3, 3 | `Completed` |
| 3 | lo mismo, con el servidor ya arriba | 6,6 s | 1, 2, 3, 3 | `Completed`, con URL de la corrida |

**Y aquí está la parte honesta: en esta maqueta el orquestador es más lento.** De
los 12,7 segundos, unos 9 son arrancar el servidor temporal; con el servidor ya
levantado bajan a 6,6. El overhead es aproximadamente fijo, y el ahorro es
proporcional a lo que cuestan los pasos que no se repiten. Con pasos de cuatro
segundos, no vale la pena. Con los ocho minutos de descarga del Acto 1 del bloque
"El dolor", la cuenta se invierte y no está cerca.

Ese es el criterio para subir de peldaño: **cuánto cuesta repetir lo que ya
estaba hecho**. No "el orquestador es mejor".

## Peldaño 1 y peldaño 3, lado a lado

Es la misma secuencia de llamadas. Lo único que se agrega son los decoradores y
el número de intento.

Peldaño 1 — `1-script.py`:

```text
def main() -> int:
    crudo  = paso_1_descargar()
    limpio = paso_2_preparar(crudo)
             paso_3_resumir(limpio)
```

Peldaño 3 — `3-orquestador.py`:

```text
@task(retries=2, retry_delay_seconds=[1, 3])
def descargar() -> Path:
    return paso_1_descargar(intento=task_run.run_count)      # <- lo único nuevo

@flow(name="escalera-peldano-3", log_prints=True)
def pipeline() -> str:
    crudo  = descargar()
    limpio = preparar(crudo)
    resumen = resumir(limpio)
```

`task_run.run_count` es el contador de intentos que Prefect incrementa en cada
reintento. Es lo único que le permite al peldaño 3 distinguir "primer intento" de
"segundo intento", y por eso el fallo transitorio de `pasos.py` solo lo sobrevive
él.

## La tabla completa

Lo que cada peldaño da, y lo que no.

| | SCRIPT | CRON | ORQUESTADOR |
|---|---|---|---|
| Ejecuta el código | sí | sí | sí |
| Corre sin nadie delante | no | **sí** | sí |
| Sobrevive un fallo transitorio | no | no | **sí** (`retries` + backoff) |
| Sabe *cuál* paso falló | no (un traceback) | no | **sí** (estado por task) |
| No repite los pasos que ya terminaron | no | no | **sí** |
| Deja historia de las corridas | no | no (solo el log que escribas tú) | **sí** (corridas, duración, estado) |
| Avisa cuando falla | no | no | **sí** (automations) |
| Acepta parámetros por corrida | sí, a mano | no | **sí**, editables desde la UI |
| Se puede relanzar una corrida vieja | no | no | **sí** |
| Evita que dos corridas se pisen | no | no (hay que usar `flock`) | **sí** |
| Igual en Linux, macOS y Windows | sí | **no** | sí |
| Piezas que hay que mantener | 0 | 1 crontab + 1 envoltorio | servidor, worker, deployment |

La última fila es la que se olvida. El orquestador no es gratis: agrega un
servidor, un worker y un deployment que también se caen, también se actualizan y
también hay que monitorear. La sección "Cuándo `cron` es la respuesta correcta"
del [README de `2-cron/`](2-cron/README.md) tiene las cuatro condiciones bajo las
cuales quedarse en el peldaño 2 es la decisión correcta.

## Lo que ningún peldaño resuelve

Ninguno de los tres mejora el modelo, valida los datos ni decide si algo va a
producción. Subir de peldaño cambia **quién ejecuta y qué queda registrado**, no
la calidad de lo que se ejecuta.

Un pipeline orquestado que entrena sobre datos malos entrena sobre datos malos,
con más puntualidad. La validación de datos es el contrato de
[S02](../../s02-datos/), y la decisión de promover es el gate de
[S06](../../s06-cloud-cicd/).

## Limpieza

Los archivos intermedios van al directorio temporal del sistema, así que no hay
nada que sacar del repositorio. Si quieres borrarlos:

```bash
rm -rf "${TMPDIR:-/tmp}/escalera-mlops"
```

Y si instalaste la línea de cron del peldaño 2, **bórrala** antes de cerrar el
portátil:

```bash
2-cron/programar.sh --quitar
```

---

Siguiente: [`../00-intro-prefect/`](../00-intro-prefect/) — la progresión de nueve
pasos que convierte el peldaño 3 en algo que se despliega: `serve()`, schedules,
parámetros, artifacts, work pools y `prefect.yaml`.
