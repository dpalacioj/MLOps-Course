#!/usr/bin/env python
"""Genera los dos notebooks de esta carpeta con nbformat, sin outputs.

Un .ipynb es JSON con metadatos y outputs embebidos: editarlo a mano produce diffs
ilegibles y publica salidas con rutas del disco de quien lo ejecuto. Este archivo es
la fuente de verdad de los dos notebooks y del `pipeline_bicis.py` que el segundo
escribe en su ultima celda de codigo.

Los notebooks trabajan sobre un dataset publico pequeno (alquiler de bicicletas por
hora) y llevan todo el codigo en las celdas a proposito: el objetivo es ver la
mecanica de Prefect sin ningun paquete propio en medio.

Uso:
    uv run python sesiones/s04-orquestacion/notebooks/_generar_notebooks.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

AQUI = Path(__file__).resolve().parent


def md(texto: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(texto.strip("\n"))


def code(texto: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(texto.strip("\n"))


def notebook(celdas: list[nbf.NotebookNode], titulo: str) -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    nb.cells = celdas
    # Ids secuenciales, como los deja nbstripout: asi el hook no reescribe el archivo.
    for i, celda in enumerate(nb.cells):
        celda.id = str(i)
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
        "titulo": titulo,
    }
    return nb


# =============================================================================
# Fragmentos compartidos por los dos notebooks
# =============================================================================
CHEQUEO_SERVIDOR = """
import httpx
from prefect.settings import get_current_settings

api = get_current_settings().api.url
if not api:
    raise RuntimeError(
        "PREFECT_API_URL no esta configurada. En una terminal, una sola vez:\\n"
        "    uv run prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api"
    )
try:
    httpx.get(f"{api}/health", timeout=3).raise_for_status()
except httpx.HTTPError as exc:
    raise RuntimeError(
        f"El servidor de Prefect no responde en {api}. "
        "Hay que levantarlo en otra terminal con `uv run prefect server start` "
        "y volver a ejecutar esta celda."
    ) from exc

print("API de Prefect:", api)
print("Interfaz web:  ", api.removesuffix("/api"))
"""

CONSTANTES = """
from pathlib import Path

# La raiz del repositorio se busca hacia arriba hasta encontrar pyproject.toml. Asi no
# hay rutas absolutas: el notebook corre desde su carpeta y el .py desde cualquier sitio.
_inicio = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
RAIZ = _inicio
while not (RAIZ / "pyproject.toml").exists() and RAIZ.parent != RAIZ:
    RAIZ = RAIZ.parent

# Bike Sharing (UCI): una fila por hora, Washington DC, 2011-2012. Pesa 1,2 MB.
URL_HF = "https://huggingface.co/datasets/t22000t/bike-sharing-tabular/resolve/main/hour.csv"
# La fuente original, por si Hugging Face no responde. El zip trae `hour.csv`.
URL_UCI = "https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip"
# Cache local. `data/external/` esta en .gitignore: el repositorio no guarda datos.
CACHE_CSV = RAIZ / "data" / "external" / "bicis-por-hora.csv"

# Traduccion de los nombres originales del CSV. Se aplica al leer y no se vuelve a
# pensar en ingles.
COLUMNAS = {
    "instant": "indice",
    "dteday": "fecha",
    "season": "estacion",
    "yr": "anio",
    "mnth": "mes",
    "hr": "hora",
    "holiday": "festivo",
    "weekday": "dia_semana",
    "workingday": "dia_laboral",
    "weathersit": "clima",
    "temp": "temperatura",
    "atemp": "sensacion_termica",
    "hum": "humedad",
    "windspeed": "viento",
    "casual": "casuales",
    "registered": "registrados",
    "cnt": "total",
}
"""

LEER_FUENTE = '''
import io
import zipfile

import pandas as pd


def leer_fuente() -> pd.DataFrame:
    """Lee el CSV crudo desde Hugging Face y, si falla, desde UCI."""
    try:
        crudo = pd.read_csv(URL_HF)
    except Exception as exc:  # cualquier fallo de red cae al respaldo
        print(f"Hugging Face no respondio ({type(exc).__name__}); usando el zip de UCI")
        respuesta = httpx.get(URL_UCI, timeout=60, follow_redirects=True)
        respuesta.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(respuesta.content)) as zf:
            crudo = pd.read_csv(zf.open("hour.csv"))
    return crudo.rename(columns=COLUMNAS)
'''


# =============================================================================
# 01 — Prefect paso a paso
# =============================================================================
NB1 = [
    md(
        """
# Prefect paso a paso, con datos reales

## De qué trata este notebook

Un *pipeline* de datos es una secuencia de pasos que se ejecutan en orden: descargar,
limpiar, calcular, guardar. Escribirlo como un script de Python funciona hasta que
hay que responder preguntas operativas: ¿qué paso falló?, ¿con qué datos?, ¿cuánto
tardó cada uno?, ¿se puede repetir sin volver a descargar todo?, ¿cómo se programa
para que corra solo cada noche?

Un **orquestador** es la herramienta que responde esas preguntas. **Prefect** es un
orquestador escrito en Python: se instala como una biblioteca (`pip install prefect`),
se usa con dos decoradores (`@flow` y `@task`) y guarda el historial de cada ejecución
en un **servidor** con una interfaz web. Este notebook recorre sus piezas una por una,
cada una sobre datos reales, y mide lo que promete en vez de afirmarlo.

**Los datos:** alquiler de bicicletas públicas por hora en Washington DC durante 2011 y
2012 (17.379 filas, 17 columnas, 1,2 MB), un dataset clásico de UCI publicado también
en Hugging Face. Se descarga la primera vez y se guarda en `data/external/`, que el
repositorio ignora: el código viaja, los datos no.

**El código vive en las celdas.** Es una decisión deliberada de este notebook: se
trata de ver el mecanismo completo, sin importar funciones de un paquete que oculten
la mitad. El segundo notebook de esta carpeta toma el mismo código y lo convierte en
un archivo `.py` que corre sin Jupyter.

## Mapa del recorrido

| # | Pieza | Qué resuelve |
|---|---|---|
| 1 | una función normal de Python | el punto de partida, sin Prefect |
| 2 | `@flow` | cada ejecución queda registrada: nombre, duración, estado, logs |
| 3 | `@task` | saber **cuál** paso falló, no solo que algo falló |
| 4 | `get_run_logger` | logs que se guardan en el servidor, no solo en pantalla |
| 5 | `retries` | un fallo pasajero de red no tira toda la ejecución |
| 6 | `cache_policy` | no repetir un cálculo caro si nada cambió, medido en segundos |
| 7 | artifacts | resultados publicados que se consultan después |
| 8 | parámetros | validación de tipos **antes** de ejecutar nada |
| 9 | `.submit()` | dos pasos independientes corriendo a la vez |
| 10 | estados | leer el resultado de una ejecución sin que reviente el notebook |

## Requisitos

Hacen falta **dos terminales** además de este notebook, ambas en la raíz del
repositorio:

```bash
# Terminal 1 — el servidor de Prefect. Queda ocupada mientras corre; no se cierra.
uv run prefect server start

# Terminal 2 — una sola vez: decirle al cliente de Prefect dónde está ese servidor.
uv run prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
```

- **`uv`** es el gestor de entornos y dependencias del repositorio: `uv run <comando>`
  ejecuta el comando dentro del entorno virtual del proyecto, con las versiones
  exactas del archivo `uv.lock`. Equivale a activar el entorno y ejecutar el comando.
- La **interfaz web** del servidor queda en <http://127.0.0.1:4200>. Conviene tenerla
  abierta en otra pestaña: cada celda que ejecute un flow deja algo allí, y el texto
  indica qué mirar.
- Sin el `config set`, Prefect levanta un servidor temporal propio para cada
  ejecución y nada aparece en la interfaz. Es el error más frecuente al empezar.

> Este notebook se publica **sin outputs**: los resultados se describen en el texto
> y se reproducen al ejecutarlo. Las salidas dependen de la hora y de la red, y no
> tienen sentido congeladas en un archivo.
"""
    ),
    md(
        """
## 0. Comprobar el servidor

Cuando el servidor no está arriba, el error aparece varias celdas más abajo, al final
de un traceback largo de `httpx`. Esta celda lo detecta primero y lo dice en una
línea. `httpx` es la biblioteca HTTP que Prefect usa internamente; aquí sirve para
hacer una petición al endpoint `/health` del servidor.
"""
    ),
    code(CHEQUEO_SERVIDOR),
    md(
        """
## 1. Los datos, sin Prefect

Antes del primer decorador, la función que se va a orquestar: descarga el CSV, traduce
las columnas al español y lo guarda en disco para no volver a bajarlo. Es Python
corriente con **pandas**, la biblioteca estándar para tablas en memoria (`DataFrame`).

Tres decisiones visibles en el código:

- **Dos fuentes.** Hugging Face es un repositorio público de modelos y datasets; la
  URL apunta directamente al archivo `hour.csv` de uno de ellos. Si no responde, se
  lee el zip original del repositorio de UCI. Depender de un solo servicio externo
  para un ejemplo que se ejecuta muchas veces es una fragilidad innecesaria.
- **Una cache en disco**, `CACHE_CSV`: la segunda ejecución no toca la red. Es una
  cache escrita a mano, distinta de la que Prefect ofrece más adelante.
- **Ninguna ruta absoluta.** La raíz del repositorio se busca hacia arriba desde la
  carpeta actual, así el mismo código funciona en cualquier máquina.
"""
    ),
    code(CONSTANTES),
    code(LEER_FUENTE),
    code(
        '''
def descargar_bicis(destino: Path = CACHE_CSV) -> pd.DataFrame:
    """Devuelve el dataset con columnas en espanol, bajandolo solo la primera vez."""
    if destino.exists():
        return pd.read_csv(destino)
    df = leer_fuente()
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False)
    return df


bicis = descargar_bicis()
print(bicis.shape, "filas x columnas")
print("desde", bicis["fecha"].min(), "hasta", bicis["fecha"].max())
bicis.head()
'''
    ),
    md(
        """
Diecisiete columnas. Las que importan en lo que sigue:

| Columna | Significado |
|---|---|
| `fecha`, `anio`, `mes`, `hora`, `dia_semana` | cuándo. `anio` vale 0 para 2011 y 1 para 2012 |
| `festivo`, `dia_laboral` | calendario (1 = sí) |
| `clima` | 1 despejado, 2 nublado, 3 lluvia ligera, 4 tormenta |
| `temperatura`, `sensacion_termica`, `humedad`, `viento` | condiciones meteorológicas, normalizadas entre 0 y 1 |
| `casuales`, `registrados` | alquileres de usuarios ocasionales y de abonados en esa hora |
| `total` | alquileres en esa hora: exactamente `casuales + registrados` |

Esa última igualdad importa en el segundo notebook, donde `total` es la variable a
predecir: `casuales` y `registrados` no pueden ser variables de entrada del modelo,
porque juntas *son* la respuesta.
"""
    ),
    md(
        """
## 2. `@flow`: la misma función, observada

Un **flow** es la unidad de trabajo de Prefect: una función de Python marcada con el
decorador `@flow`. La función sigue siendo llamable igual y devuelve lo mismo. Lo que
cambia es que cada llamada pasa a ser una **ejecución** (*flow run*) con nombre,
hora de inicio, duración, estado final y logs, todo registrado en el servidor.
"""
    ),
    code(
        '''
from prefect import flow


@flow
def resumen_bicis() -> dict:
    """Total de alquileres por anio."""
    df = descargar_bicis()
    por_anio = df.groupby("anio")["total"].sum()
    return {"2011": int(por_anio[0]), "2012": int(por_anio[1])}


resumen_bicis()
'''
    ),
    md(
        """
Las líneas que aparecen sobre el resultado son el log de la ejecución: un nombre
generado al azar (dos palabras, del estilo `wine-cobra`), la hora y el estado final
`Completed()`. En la interfaz web, en **Runs**, está esa misma ejecución con su
duración.

Un dato que conviene conocer desde el principio: una ejecución vacía contra el
servidor cuesta alrededor de **un segundo** de sobrecarga, que es lo que tarda
registrar la ejecución y sus estados. Es el precio de tener historial, reintentos y
caché; para un script que corre en milisegundos y nunca falla, ese precio no compensa.
"""
    ),
    md(
        """
## 3. `@task`: saber cuál paso falló

Una **task** es un paso dentro de un flow, marcado con `@task`. Un flow sin tasks
falla como un bloque —"el flow falló"—. Partido en tasks, cada paso tiene estado,
duración y logs propios.

El orden de ejecución no se declara: Prefect lo deduce de los **datos**. `resumir`
recibe lo que devuelve `descargar`, así que va después. Ese encadenamiento de
entradas y salidas es el grafo de dependencias, y basta con escribir Python normal
para construirlo.
"""
    ),
    code(
        '''
from prefect import task


@task
def descargar() -> pd.DataFrame:
    return descargar_bicis()


@task
def resumir(df: pd.DataFrame, columna: str) -> dict:
    """Promedio de `columna` por hora del dia, redondeado."""
    return df.groupby("hora")[columna].mean().round(1).to_dict()


@flow
def resumen_por_hora(columna: str = "total") -> dict:
    df = descargar()
    return resumir(df, columna)  # depende de `df`: de ahi sale el grafo


por_hora = resumen_por_hora()
print("hora 8:", por_hora[8], "| hora 17:", por_hora[17], "| hora 3:", por_hora[3])
'''
    ),
    md(
        """
Ahora el mismo flow con **un error real**: el nombre de una columna que no existe.
Se ejecuta con `return_state=True`, que hace que el flow devuelva su **estado** en
lugar de propagar la excepción y cortar la celda (la sección 10 vuelve sobre esto).

El traceback que aparece igualmente no es la celda fallando: es el **log** de la task
que falló, tal como quedó guardado en el servidor.
"""
    ),
    code(
        """
estado = resumen_por_hora(columna="totl", return_state=True)
print("estado final del flow:", estado.name)
print("que paso:", estado.message)
"""
    ),
    md(
        """
En la interfaz web, dentro de esa ejecución, `descargar` aparece en **Completed** y
`resumir` en **Failed**, con el `KeyError` en su log. Eso compra `@task`: cuando algo
falle a las tres de la mañana, el registro dice *qué* paso falló y con *qué* entrada,
no solo "el pipeline falló".
"""
    ),
    md(
        """
## 4. Logs que se conservan

`print` escribe en la terminal donde corre el proceso, y esa terminal puede haberse
cerrado cuando alguien necesite leer el mensaje. `get_run_logger()` devuelve un
*logger* —el mecanismo estándar de registro de Python— conectado a la ejecución
actual: lo que se escribe con él viaja al servidor y se lee desde la interfaz días
después, junto con la ejecución a la que pertenece.

`log_prints=True` en el decorador captura además los `print` de la función y los
convierte en logs. Sirve para no reescribir código que ya existe.
"""
    ),
    code(
        """
from prefect import get_run_logger


@task
def contar_por_clima(df: pd.DataFrame) -> dict:
    logger = get_run_logger()
    conteo = df["clima"].value_counts().sort_index().to_dict()
    logger.info("horas por tipo de clima: %s", conteo)
    if conteo.get(4, 0) < 10:
        logger.warning("clima 4 (tormenta) tiene solo %d horas: poca senal", conteo.get(4, 0))
    return conteo


@flow(log_prints=True)
def revisar_clima() -> dict:
    print("este print tambien queda en el log del run")
    return contar_por_clima(descargar())


revisar_clima()
"""
    ),
    md(
        """
## 5. Reintentos: un fallo pasajero no cuesta la ejecución

Una descarga puede fallar por un corte de red de dos segundos. Sin reintentos, ese
corte tira toda la ejecución y obliga a repetirla desde cero. Con `retries=3`, Prefect
vuelve a intentar la task hasta tres veces antes de darla por fallida.

Dos argumentos acompañan a `retries`:

- `retry_delay_seconds` es la espera entre intentos. Con una **lista** —`[1, 2, 4]`—
  la espera crece en cada intento; esto se llama *backoff* y da tiempo a que el
  problema del otro lado se resuelva, en vez de insistir en la misma ventana de
  degradación.
- `retry_jitter_factor` añade una variación aleatoria a esas esperas. Si cien tasks
  fallan a la vez y todas reintentan en el mismo segundo, el servicio que se estaba
  recuperando vuelve a caerse (*thundering herd*); el *jitter* las desincroniza.

**Cómo se simula el fallo aquí.** La task falla exactamente las primeras
`fallos_simulados` veces y después funciona. Para saber en qué intento está, lee
`prefect.runtime.task_run.run_count`, un contador que Prefect incrementa en cada
reintento. El fallo es local y determinista a propósito: un ejemplo que dependiera de
un servicio externo que "a veces" falla no se comportaría igual dos veces seguidas.
"""
    ),
    code(
        """
from prefect.runtime import task_run


@task(retries=3, retry_delay_seconds=[1, 2, 4], retry_jitter_factor=0.2)
def descarga_inestable(fallos_simulados: int) -> pd.DataFrame:
    intento = task_run.run_count
    print(f"intento {intento}")
    if intento <= fallos_simulados:
        # ConnectionError y no Exception: el tipo es informacion para quien lee el log.
        raise ConnectionError(f"fallo de red simulado en el intento {intento}")
    return descargar_bicis()


@flow(log_prints=True)
def descarga_con_reintentos(fallos_simulados: int = 2) -> int:
    return len(descarga_inestable(fallos_simulados))


print("filas:", descarga_con_reintentos())
"""
    ),
    md(
        """
En la interfaz, la task pasa por **Retrying → Retrying → Completed** y el flow termina
en `Completed`. Con `fallos_simulados=9` los tres reintentos se agotan y el flow queda
en `Failed` (se puede probar cambiando el argumento). En Prefect 3 el estado final del
flow se deriva de lo que la función devuelve o de la excepción que propaga, no de los
estados de sus tasks.

¿Dónde van los reintentos en un pipeline real? En las tasks que hablan con la **red**:
descargas, APIs, bases de datos. Reintentar un error de programación —un `KeyError`—
solo hace que falle tres veces más despacio.
"""
    ),
    md(
        """
## 6. Caché: no repetir trabajo caro, medido

Prefect puede guardar el **resultado** de una task y, la próxima vez que se la llame
con las mismas entradas, devolverlo sin ejecutarla. La política de caché decide qué
cuenta como "las mismas entradas":

- `INPUTS`: los argumentos de la task, incluidos DataFrames completos (se calcula un
  *hash* de su contenido; si cambia una celda, cambia la clave).
- `TASK_SOURCE`: el código fuente de la task. Si se edita la función, la caché
  anterior deja de valer.
- `INPUTS + TASK_SOURCE`, la combinación que se usa aquí, es la política habitual
  para cachear **entre ejecuciones distintas**. La política por defecto incluye además
  el identificador de la ejecución, así que solo evita repeticiones dentro de una misma
  ejecución.

`cache_expiration` pone fecha de caducidad al resultado guardado.

Dos caches conviven en este notebook y conviene distinguirlas:

| | `CACHE_CSV` (escrita a mano) | La de Prefect (`cache_policy`) |
|---|---|---|
| Qué guarda | un archivo que el código decide | el resultado de una task |
| Clave | "¿existe el archivo?" | hash de entradas + código fuente |
| Caduca | cuando se borra el archivo | `cache_expiration` |
| Se ve | en el disco | en la interfaz, como estado **Cached** |
| Se invalida sola si cambian los datos | no | sí, porque el DataFrame es parte de la clave |

Sobre la celda que sigue:

- El trabajo "caro" se simula con dos segundos de `time.sleep`. Lo caro real en un
  pipeline es descargar o entrenar, y se cachea exactamente igual (el segundo notebook
  cachea un entrenamiento).
- La task recibe un argumento extra, `sesion`, que cambia cada vez que arranca el
  kernel de Jupyter. Existe solo por la demostración: la caché de Prefect vive en
  disco (`~/.prefect/storage/`) y sobrevive al kernel, así que sin ese argumento, al
  reabrir el notebook otro día, las tres ejecuciones saldrían `Cached` y no habría
  nada que comparar. En un pipeline real ese argumento no se pone: ahí el acierto de
  caché entre ejecuciones es precisamente lo que se busca.
"""
    ),
    code(
        """
import time
from datetime import datetime, timedelta

from prefect.cache_policies import INPUTS, TASK_SOURCE

# Cambia en cada arranque del kernel. Solo para que la demostracion empiece sin cache.
SESION = datetime.now().strftime("%H%M%S")


@task(cache_policy=INPUTS + TASK_SOURCE, cache_expiration=timedelta(hours=1))
def agregar_por_mes(df: pd.DataFrame, anio: int, sesion: str) -> pd.DataFrame:
    time.sleep(2)  # simula un calculo caro
    del_anio = df[df["anio"] == anio]
    return del_anio.groupby("mes")["total"].sum().rename("alquileres").reset_index()


@flow
def totales_mensuales(anio: int = 0) -> pd.DataFrame:
    return agregar_por_mes(descargar(), anio, SESION)


def cronometrar(fn, *args):
    inicio = time.perf_counter()
    salida = fn(*args)
    return salida, time.perf_counter() - inicio


_, primera = cronometrar(totales_mensuales, 0)
_, segunda = cronometrar(totales_mensuales, 0)
_, otro_anio = cronometrar(totales_mensuales, 1)
print(f"1a corrida (calcula):        {primera:5.2f}s")
print(f"2a corrida (mismos inputs):  {segunda:5.2f}s  <- Cached")
print(f"otro anio (input distinto):  {otro_anio:5.2f}s  <- vuelve a calcular")
"""
    ),
    md(
        """
La segunda ejecución se ahorra los dos segundos: en la interfaz la task aparece en
estado **Cached** y el resultado se lee de `~/.prefect/storage/`. La tercera vuelve a
calcular porque `anio` cambió y con él la clave. Si se ejecuta la celda otra vez, las
tres salen `Cached`, porque `sesion` sigue siendo la misma.

Cuando la diferencia entre la primera y la segunda **no** es de unos dos segundos, la
causa es una de tres: la política no incluye `TASK_SOURCE` y se editó el código; el
`cache_expiration` venció; o alguna entrada cambia en cada llamada (pasar
`datetime.now()` como argumento es el caso clásico).
"""
    ),
    md(
        """
## 7. Artifacts: lo que queda publicado después de ejecutar

Un log se lee línea a línea; un **artifact** se consulta. Es un resultado —una tabla,
un texto en Markdown, un enlace— publicado en el servidor bajo una **clave** estable.
Con la misma clave en cada ejecución, la interfaz muestra la historia de ese artifact:
cómo cambió la tabla de un día al siguiente. Es la forma de dejar un resumen legible
para alguien que no va a abrir el código.
"""
    ),
    code(
        """
from prefect.artifacts import create_markdown_artifact, create_table_artifact


@task
def publicar_resumen(mensual: pd.DataFrame, anio: int) -> None:
    etiqueta = 2011 + anio
    create_table_artifact(
        key=f"bicis-mensual-{etiqueta}",
        table=mensual.to_dict("records"),
        description=f"Alquileres por mes en {etiqueta}.",
    )
    pico = mensual.loc[mensual["alquileres"].idxmax()]
    create_markdown_artifact(
        key=f"bicis-resumen-{etiqueta}",
        markdown=(
            f"# Bicis {etiqueta}\\n\\n"
            f"- total del anio: **{int(mensual['alquileres'].sum()):,}**\\n"
            f"- mes pico: **{int(pico['mes'])}** con {int(pico['alquileres']):,} alquileres\\n"
        ),
    )


@flow
def informe_anual(anio: int = 0) -> None:
    mensual = agregar_por_mes(descargar(), anio, SESION)  # Cached: ya corrio con estos inputs
    publicar_resumen(mensual, anio)


informe_anual(0)
informe_anual(1)
print("Interfaz -> Artifacts: bicis-mensual-2011, bicis-mensual-2012 y los dos resumenes")
"""
    ),
    md(
        """
## 8. Parámetros: validación antes de ejecutar

Los argumentos de un flow son sus **parámetros**, y las anotaciones de tipo
(`anio: int`) no son decorativas: Prefect las valida con **Pydantic** —la biblioteca
de validación de datos más usada en Python— **antes de crear la ejecución**. Un
`anio="dos mil once"` no llega a ejecutar nada: se rechaza en la puerta, con un
mensaje que dice qué parámetro y por qué.

Esto es lo que hace seguros los parámetros cuando el flow se programa para correr
solo y alguien cambia un valor desde la interfaz web.
"""
    ),
    code(
        """
from prefect.exceptions import ParameterTypeError


@flow
def horas_pico(anio: int = 0, cuantas: int = 3) -> list[int]:
    df = descargar()
    por_hora = df[df["anio"] == anio].groupby("hora")["total"].mean()
    return por_hora.nlargest(cuantas).index.tolist()


print("horas pico 2012:", horas_pico(anio=1))

try:
    horas_pico(anio="dos mil once")
except ParameterTypeError as exc:
    print("rechazado antes de ejecutar ->", str(exc).splitlines()[0])
"""
    ),
    md(
        """
## 9. `.submit()`: dos tasks independientes, a la vez

Llamar una task como una función normal la ejecuta y espera su resultado. Con
`.submit()` la task se **envía** a un *task runner* —el componente que decide dónde y
cómo ejecutar tasks— y devuelve de inmediato un *future*, una promesa de resultado; el
flow continúa, y `.result()` espera solo cuando el valor hace falta.

`ThreadPoolTaskRunner` ejecuta las tasks enviadas en hilos paralelos. Dos tasks que
no dependen entre sí corren a la vez, y el tiempo total baja. La ganancia es real solo
si las tasks tardan algo: por eso cada una simula un segundo de trabajo, y por eso se
mide en vez de suponerlo.
"""
    ),
    code(
        """
from prefect.task_runners import ThreadPoolTaskRunner


@task
def promedio_por(df: pd.DataFrame, columna: str) -> dict:
    time.sleep(1)  # simula trabajo
    return df.groupby(columna)["total"].mean().round(1).to_dict()


@flow
def perfiles_secuencial() -> tuple[dict, dict]:
    df = descargar()
    return promedio_por(df, "dia_semana"), promedio_por(df, "clima")


@flow(task_runner=ThreadPoolTaskRunner(max_workers=4))
def perfiles_paralelo() -> tuple[dict, dict]:
    df = descargar()
    f1 = promedio_por.submit(df, "dia_semana")
    f2 = promedio_por.submit(df, "clima")
    return f1.result(), f2.result()


_, t_sec = cronometrar(perfiles_secuencial)
(por_dia, por_clima), t_par = cronometrar(perfiles_paralelo)
print(f"secuencial: {t_sec:4.2f}s | paralelo: {t_par:4.2f}s")
print("por clima:", por_clima)
"""
    ),
    md(
        """
## 10. Estados: leer el resultado sin que reviente el notebook

Hasta aquí los flows devolvían valores. Con `return_state=True` devuelven su
**estado**, que es el vocabulario completo del orquestador: `Completed`, `Failed`,
`Cached`, `Retrying`, `Pending`... Es lo que consulta cualquier sistema externo —un
proceso de integración continua, otro flow— para decidir qué hacer después.

Un detalle de Jupyter, no de Prefect: el notebook ya tiene un *event loop* (el
mecanismo de ejecución asíncrona de Python) en marcha, y `State.result()` lo detecta
y devuelve una corrutina. Por eso aquí lleva `await`. En un script corriente —como el
`pipeline_bicis.py` del segundo notebook— se llama sin `await`.
"""
    ),
    code(
        """
ok = horas_pico(anio=1, return_state=True)
print(ok.name, "| completado:", ok.is_completed(), "| resultado:", await ok.result())

roto = descarga_con_reintentos(fallos_simulados=9, return_state=True)
print(roto.name, "| fallido:", roto.is_failed())
excepcion = await roto.result(raise_on_failure=False)
print("la excepcion, sin relanzarla:", type(excepcion).__name__, "-", excepcion)
"""
    ),
    md(
        """
## Resumen

| Pieza | Qué garantiza | Cómo se comprobó |
|---|---|---|
| `@flow` | cada ejecución registrada con nombre, duración y estado | la ejecución aparece en **Runs** |
| `@task` | se sabe cuál paso falló | `descargar` en Completed, `resumir` en Failed |
| `get_run_logger` | logs que sobreviven a la terminal | el log en la interfaz |
| `retries` + backoff + jitter | un fallo pasajero no tira la ejecución | Retrying → Retrying → Completed |
| `cache_policy` | no repetir trabajo caro | ~3 s → ~1 s → ~3 s, medido |
| artifacts | resultados consultables con historia | **Artifacts** en la interfaz |
| parámetros | tipos validados antes de ejecutar | `ParameterTypeError` en la puerta |
| `.submit()` | paralelismo sin escribir hilos | ~3 s → ~2 s, medido |
| estados | el resultado como dato, no como excepción | `Completed` / `Failed` leídos |

Lo que **no** aparece aquí, a propósito, son `serve()` y `deploy()`: las dos formas de
dejar un flow programado para que corra solo. Ambas dejan un proceso escuchando de
forma indefinida y bloquearían el kernel de Jupyter; se hacen desde una terminal. La
carpeta `00-intro-prefect/`, junto a esta, las recorre archivo por archivo.

Siguiente: [`02-pipeline-ml-con-prefect.ipynb`](02-pipeline-ml-con-prefect.ipynb), las
mismas piezas ordenadas como un pipeline de entrenamiento e inferencia que termina en
un archivo `.py` listo para programar.
"""
    ),
]


# =============================================================================
# 02 — El pipeline de ML con Prefect
# =============================================================================
# Cada fragmento es una celda del notebook Y un trozo de `pipeline_bicis.py`. El
# archivo se compone concatenandolos, asi el notebook y el .py no pueden divergir.
P_CABECERA = '''
"""Pipeline de entrenamiento e inferencia sobre el dataset de bicis, con Prefect.

Generado por `02-pipeline-ml-con-prefect.ipynb`: el notebook construye estas tasks
celda por celda y al final escribe este archivo. Para cambiarlo se edita el notebook
(o `_generar_notebooks.py`) y se vuelve a ejecutar.

Uso, desde esta carpeta:
    uv run python pipeline_bicis.py
"""

import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pandera.pandas as pa
from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact
from prefect.cache_policies import INPUTS, TASK_SOURCE
from prefect.runtime import flow_run
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
'''

P_CONSTANTES = """
# La raiz del repositorio se busca hacia arriba hasta encontrar pyproject.toml. Sin
# rutas absolutas: el notebook corre desde su carpeta y este archivo desde cualquier
# sitio (incluido /app dentro de un contenedor).
_inicio = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
RAIZ = _inicio
while not (RAIZ / "pyproject.toml").exists() and RAIZ.parent != RAIZ:
    RAIZ = RAIZ.parent

URL_HF = "https://huggingface.co/datasets/t22000t/bike-sharing-tabular/resolve/main/hour.csv"
URL_UCI = "https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip"
CACHE_CSV = RAIZ / "data" / "external" / "bicis-por-hora.csv"
PREDICCIONES = RAIZ / "data" / "processed" / "predicciones-bicis.parquet"

COLUMNAS = {
    "instant": "indice",
    "dteday": "fecha",
    "season": "estacion",
    "yr": "anio",
    "mnth": "mes",
    "hr": "hora",
    "holiday": "festivo",
    "weekday": "dia_semana",
    "workingday": "dia_laboral",
    "weathersit": "clima",
    "temp": "temperatura",
    "atemp": "sensacion_termica",
    "hum": "humedad",
    "windspeed": "viento",
    "casual": "casuales",
    "registered": "registrados",
    "cnt": "total",
}

TARGET = "total"
# `casuales` y `registrados` NO estan: suman exactamente `total`. Incluirlas seria
# predecir el target con el target (fuga de informacion), y el contrato lo verifica.
FEATURES = [
    "estacion",
    "anio",
    "mes",
    "hora",
    "festivo",
    "dia_semana",
    "dia_laboral",
    "clima",
    "temperatura",
    "sensacion_termica",
    "humedad",
    "viento",
]
"""

P_DESCARGAR = '''
@task(retries=3, retry_delay_seconds=[2, 5, 10], retry_jitter_factor=0.2)
def descargar(destino: Path = CACHE_CSV) -> pd.DataFrame:
    """Baja el CSV una vez y lo guarda en disco. Los reintentos cubren la red."""
    logger = get_run_logger()
    if destino.exists():
        logger.info("cache en disco: %s", destino.relative_to(RAIZ))
        return pd.read_csv(destino)
    try:
        crudo = pd.read_csv(URL_HF)
        logger.info("descargado de Hugging Face")
    except Exception as exc:  # cualquier fallo de red cae al respaldo
        logger.warning("Hugging Face no respondio (%s); usando UCI", type(exc).__name__)
        respuesta = httpx.get(URL_UCI, timeout=60, follow_redirects=True)
        respuesta.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(respuesta.content)) as zf:
            crudo = pd.read_csv(zf.open("hour.csv"))
    df = crudo.rename(columns=COLUMNAS)
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False)
    return df
'''

P_VALIDAR = '''
CONTRATO = pa.DataFrameSchema(
    {
        "fecha": pa.Column(str),
        "anio": pa.Column(int, pa.Check.isin([0, 1])),
        "mes": pa.Column(int, pa.Check.in_range(1, 12)),
        "hora": pa.Column(int, pa.Check.in_range(0, 23)),
        "clima": pa.Column(int, pa.Check.in_range(1, 4)),
        "temperatura": pa.Column(float, pa.Check.in_range(0, 1)),
        "humedad": pa.Column(float, pa.Check.in_range(0, 1)),
        "viento": pa.Column(float, pa.Check.ge(0)),
        "casuales": pa.Column(int, pa.Check.ge(0)),
        "registrados": pa.Column(int, pa.Check.ge(0)),
        "total": pa.Column(int, pa.Check.ge(0)),
    },
    checks=[
        # La regla que justifica excluir dos columnas de FEATURES, verificada y no supuesta.
        pa.Check(lambda d: d["casuales"] + d["registrados"] == d["total"], name="total_es_la_suma"),
    ],
    strict=False,  # las columnas que no se nombran pasan sin revisarse
)


@task
def validar(df: pd.DataFrame) -> pd.DataFrame:
    """Detiene la ejecucion si los datos no cumplen el contrato. Reporta todos los errores."""
    validado = CONTRATO.validate(df, lazy=True)
    get_run_logger().info("contrato OK: %d filas, %d columnas", *validado.shape)
    return validado
'''

P_FEATURES = '''
@task
def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    """Se queda con FEATURES + TARGET + fecha. Lo demas no entra al modelo."""
    return df[["fecha", *FEATURES, TARGET]].copy()


@task
def dividir_temporal(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """2011 entrena, 2012 valida. Nunca un split aleatorio: es una serie en el tiempo."""
    entrena = df[df["anio"] == 0]
    valida = df[df["anio"] == 1]
    get_run_logger().info(
        "entrena %d filas (2011) | valida %d filas (2012)", len(entrena), len(valida)
    )
    return entrena, valida
'''

P_ENTRENAR = '''
@task(cache_policy=INPUTS + TASK_SOURCE, cache_expiration=timedelta(days=1))
def entrenar(entrena: pd.DataFrame, n_iteraciones: int, tasa_aprendizaje: float):
    """Entrena el regresor. Cacheado: mismos datos + mismos hiperparametros = mismo modelo.

    Es seguro cachear porque `random_state` esta fijo y el DataFrame de entrada es parte
    de la clave: si los datos cambian, se reentrena solo. Sin `random_state`, cachear
    seria servir un modelo que nadie evaluo.
    """
    modelo = HistGradientBoostingRegressor(
        max_iter=n_iteraciones, learning_rate=tasa_aprendizaje, random_state=42
    )
    modelo.fit(entrena[FEATURES], entrena[TARGET])
    return modelo
'''

P_EVALUAR = '''
@task
def evaluar(modelo, entrena: pd.DataFrame, valida: pd.DataFrame) -> dict:
    """RMSE y MAE del modelo contra el baseline de predecir la media de 2011."""
    y = valida[TARGET]
    baseline = np.full(len(valida), entrena[TARGET].mean())
    pred = modelo.predict(valida[FEATURES])
    metricas = {
        "rmse_baseline": round(float(root_mean_squared_error(y, baseline)), 1),
        "rmse_modelo": round(float(root_mean_squared_error(y, pred)), 1),
        "mae_modelo": round(float(mean_absolute_error(y, pred)), 1),
    }
    filas = "\\n".join(f"| {k} | {v} |" for k, v in metricas.items())
    create_markdown_artifact(
        key="bicis-metricas",
        markdown=f"# Metricas en 2012\\n\\n| metrica | valor |\\n|---|---|\\n{filas}\\n",
        description="Validacion temporal: entrena 2011, evalua 2012.",
    )
    get_run_logger().info("metricas: %s", metricas)
    return metricas
'''

P_PREDECIR = '''
@task
def predecir_lote(modelo, valida: pd.DataFrame, mes: int, destino: Path = PREDICCIONES) -> Path:
    """Predice un mes completo y guarda cada fila con el id de la ejecucion que la produjo."""
    lote = valida[valida["mes"] == mes].copy()
    lote["prediccion"] = modelo.predict(lote[FEATURES]).round(0)
    # Trazabilidad por fila: de que ejecucion salio cada prediccion y cuando.
    lote["flow_run_id"] = flow_run.id
    lote["flow_run_name"] = flow_run.name
    lote["generado_en"] = datetime.now(UTC).isoformat(timespec="seconds")
    destino.parent.mkdir(parents=True, exist_ok=True)
    lote.to_parquet(destino, index=False)
    get_run_logger().info("%d predicciones en %s", len(lote), destino.relative_to(RAIZ))
    return destino
'''

P_FLOW = '''
@flow(log_prints=True)
def pipeline_bicis(
    n_iteraciones: int = 300, tasa_aprendizaje: float = 0.1, mes_a_predecir: int = 12
) -> dict:
    """Descarga -> valida -> features -> split temporal -> entrena -> evalua -> predice."""
    crudo = descargar()
    limpio = validar(crudo)
    tabla = construir_features(limpio)
    entrena, valida = dividir_temporal(tabla)
    modelo = entrenar(entrena, n_iteraciones, tasa_aprendizaje)
    metricas = evaluar(modelo, entrena, valida)
    predecir_lote(modelo, valida, mes_a_predecir)
    return metricas
'''

P_MAIN = """
if __name__ == "__main__":
    print(pipeline_bicis())
"""

# Una linea en blanco entre imports y constantes; dos entre el resto de bloques (ruff).
ARCHIVO_PIPELINE = (
    P_CABECERA.strip("\n")
    + "\n\n"
    + "\n\n\n".join(
        f.strip("\n")
        for f in [
            P_CONSTANTES,
            P_DESCARGAR,
            P_VALIDAR,
            P_FEATURES,
            P_ENTRENAR,
            P_EVALUAR,
            P_PREDECIR,
            P_FLOW,
            P_MAIN,
        ]
    )
    + "\n"
)

# La cabecera del archivo, como comentario, para la celda de imports del notebook.
CELDA_IMPORTS = (
    P_CABECERA.replace('"""Pipeline', "# Pipeline")
    .replace('    uv run python pipeline_bicis.py\n"""', "#     uv run python pipeline_bicis.py")
    .replace("\nGenerado por", "\n# Generado por")
    .replace("\ncelda por celda", "\n# celda por celda")
    .replace("\n(o `_generar_notebooks.py`)", "\n# (o `_generar_notebooks.py`)")
    .replace("\n\nUso, desde", "\n#\n# Uso, desde")
)

NB2 = [
    md(
        """
# Un pipeline de aprendizaje automático con Prefect

## De qué trata este notebook

El primer notebook de esta carpeta presenta las piezas de Prefect una por una. Este
las usa juntas para construir lo que aparece en cualquier sistema de aprendizaje
automático en producción: un **pipeline de entrenamiento e inferencia** que descarga
datos, los valida, entrena un modelo, lo evalúa y produce predicciones, dejando
registro de cada paso.

El problema es predecir cuántas bicicletas públicas se alquilarán en Washington DC en
una hora dada, a partir de la fecha, la hora y el clima. Los datos son los mismos del
primer notebook (17.379 horas de 2011 y 2012); si ya se ejecutó, el CSV está en
`data/external/` y no se descarga de nuevo.

Todo el código vive en las celdas, y al final se vuelca a un archivo
`pipeline_bicis.py` que corre sin Jupyter. Ese archivo es el punto de partida para
programar el pipeline y para empaquetarlo en un contenedor.

## Bibliotecas que aparecen

| Biblioteca | Para qué se usa aquí |
|---|---|
| **Prefect** | orquestar: tasks, reintentos, caché, artifacts, trazabilidad |
| **pandas** | leer y manipular la tabla de datos (`DataFrame`) |
| **pandera** | declarar un *contrato de datos* —qué debe cumplir cada columna— y verificarlo |
| **scikit-learn** | entrenar el modelo (`HistGradientBoostingRegressor`) y calcular métricas |
| **pyarrow** | escribir las predicciones en formato Parquet (lo usa pandas por debajo) |
| **httpx** | descargar el respaldo de UCI si Hugging Face no responde |

## El pipeline

```
descargar ─► validar ─► construir_features ─► dividir_temporal ─┬─► entrenar ─► evaluar
                                                                 └────────────► predecir_lote
```

| Task | Qué garantiza | Pieza de Prefect |
|---|---|---|
| `descargar` | el dato llega aunque la red falle una vez | `retries` |
| `validar` | el dato cumple el contrato, o la ejecución se detiene **aquí** | `@task` |
| `construir_features` | solo entran al modelo las columnas permitidas | — |
| `dividir_temporal` | 2011 entrena, 2012 valida; nunca al azar | — |
| `entrenar` | no se reentrena si nada cambió | `cache_policy` |
| `evaluar` | la métrica queda publicada, no en un `print` | artifacts |
| `predecir_lote` | cada predicción sabe de qué ejecución salió | `prefect.runtime` |

## Requisitos

Los mismos del primer notebook: el servidor de Prefect en una terminal
(`uv run prefect server start`), `PREFECT_API_URL` configurada y la interfaz web
abierta en <http://127.0.0.1:4200>.
"""
    ),
    md("## 0. Comprobar el servidor"),
    code(CHEQUEO_SERVIDOR),
    md(
        """
## 1. Imports y constantes

Todo lo que el archivo final necesita, junto. Dos listas merecen atención:

- `FEATURES` son las columnas que el modelo puede usar para predecir. No incluye
  `casuales` ni `registrados`: esas dos suman exactamente `total`, la variable a
  predecir, y un modelo que las viera "adivinaría" el resultado copiándolo. Ese error
  se llama **fuga de información** (*leakage*) y es de los más comunes en la práctica,
  porque el modelo parece excelente hasta que se usa con datos nuevos, donde esas
  columnas no existen todavía.
- `TARGET` es la variable a predecir.
"""
    ),
    code(CELDA_IMPORTS),
    code(P_CONSTANTES),
    md(
        """
## 2. `descargar`: la única task que habla con la red

Por eso es la única con reintentos. Y tiene su propia cache en disco (`CACHE_CSV`),
distinta de la de Prefect: la primera evita bajar 1,2 MB otra vez; la segunda, más
abajo, evita **entrenar** otra vez.
"""
    ),
    code(P_DESCARGAR),
    md(
        """
## 3. `validar`: el contrato de datos, con pandera

**pandera** permite escribir, como código, lo que una tabla debe cumplir: qué columnas
tiene, de qué tipo, en qué rango. Ese conjunto de reglas es un **contrato de datos**.
El pipeline no *asume* que `hora` va de 0 a 23 ni que `total` es la suma de las otras
dos columnas: lo **verifica**, y si algo no se cumple, la ejecución falla en esta task
con un mensaje claro, y no dentro del entrenamiento con un error críptico.

Tres detalles del esquema:

- `pa.Column(int, pa.Check.in_range(0, 23))` declara tipo y rango de una columna.
- El check a nivel de tabla (`checks=[...]`) ve varias columnas a la vez; aquí
  verifica la igualdad que justifica excluir dos columnas de `FEATURES`.
- `lazy=True` al validar reporta **todos** los errores juntos, en vez de detenerse
  en el primero.
"""
    ),
    code(P_VALIDAR),
    md(
        """
Antes de seguir, el contrato en acción sobre datos rotos a propósito: una fila con
`hora = 25` y otra con un `total` que no es la suma. Las dos fallas se reportan en
una sola pasada. El check de tabla completa (`total_es_la_suma`) reporta la **fila**
entera —una entrada por columna—, por eso la salida se resume por check en vez de
imprimir `failure_cases` crudo.
"""
    ),
    code(
        """
# Solo pandas, sin Prefect: la task usa get_run_logger() y fuera de una ejecucion no hay logger.
muestra = pd.read_csv(CACHE_CSV) if CACHE_CSV.exists() else pd.read_csv(URL_HF).rename(columns=COLUMNAS)
roto = muestra.head(100).copy()
roto.loc[0, "hora"] = 25
roto.loc[1, "total"] = roto.loc[1, "total"] + 1
try:
    CONTRATO.validate(roto, lazy=True)
except pa.errors.SchemaErrors as exc:
    fallos = exc.failure_cases
    print("filas que fallan, por check:")
    print(fallos.groupby("check")["index"].nunique().to_string(), "\\n")
    print("detalle de los checks de columna:")
    columna = fallos[fallos["schema_context"] == "Column"]
    print(columna[["column", "check", "index", "failure_case"]].to_string(index=False))
"""
    ),
    md(
        """
## 4. Features y división temporal

Dos tasks pequeñas y una regla que no se negocia: **la división entre entrenamiento y
validación es por tiempo**. Lo habitual en un tutorial es `train_test_split`, que
reparte las filas al azar. Con datos ordenados en el tiempo eso es un error: la hora
14 del 3 de marzo caería en entrenamiento y la hora 15 del mismo día en validación, y
el modelo "sabría" lo que pasó una hora antes de lo que tiene que predecir. La
métrica saldría optimista y el modelo decepcionaría al usarse.

Con 2011 para entrenar y 2012 para validar, el modelo se evalúa como se va a usar:
prediciendo lo que aún no ha pasado.
"""
    ),
    code(P_FEATURES),
    md(
        """
## 5. `entrenar`: cacheado, y por qué es seguro

El modelo es un `HistGradientBoostingRegressor` de scikit-learn: un conjunto de
árboles de decisión que se construyen uno tras otro, cada uno corrigiendo los errores
del anterior (*gradient boosting*). Es rápido, funciona bien con datos tabulares sin
mucho preprocesamiento y tiene dos hiperparámetros principales: cuántos árboles
(`max_iter`) y cuánto corrige cada uno (`learning_rate`).

Es la task cara (segundos aquí, horas en un caso real), y por eso lleva caché.
`INPUTS + TASK_SOURCE` significa: mismo DataFrame de entrenamiento, mismos
hiperparámetros y mismo código → mismo modelo, leído de disco sin entrenar. Si
cualquiera de los tres cambia, se reentrena solo.

La condición para que esto no sea una trampa es `random_state=42`: fija la semilla
aleatoria del algoritmo, de modo que dos entrenamientos con las mismas entradas
producen el mismo modelo. Sin ella, cachear sería reutilizar un modelo que nadie
evaluó.
"""
    ),
    code(P_ENTRENAR),
    md(
        """
## 6. `evaluar` y `predecir_lote`

`evaluar` calcula dos métricas de error sobre 2012:

- **RMSE** (raíz del error cuadrático medio): penaliza más los errores grandes. Está
  en las mismas unidades que el target, aquí bicicletas por hora.
- **MAE** (error absoluto medio): el error típico, sin castigar los extremos.

Y compara contra un **baseline**: predecir siempre el promedio de 2011. Si el modelo
no le gana a esa regla trivial, no aprendió nada, por bien que suene su métrica sola.
El resultado va a un artifact con clave fija, `bicis-metricas`, así la interfaz
muestra su historia ejecución tras ejecución.

`predecir_lote` genera las predicciones de un mes completo y escribe cada fila con el
identificador y el nombre de la ejecución que la produjo (`prefect.runtime.flow_run`)
y la hora en que se generó. Es **trazabilidad por fila**: dada cualquier predicción,
se puede llegar a la ejecución, sus logs, sus parámetros y su modelo. Las predicciones
se guardan en **Parquet**, un formato de columnas comprimido, más compacto y rápido
que CSV y que conserva los tipos de dato.
"""
    ),
    code(P_EVALUAR),
    code(P_PREDECIR),
    md(
        """
## 7. El flow: siete tasks, un grafo

El orden lo dan los datos: `validar` necesita lo que devuelve `descargar`, `entrenar`
necesita `entrena`, y así sucesivamente. No hay una sola línea que diga "esto va
después de aquello".
"""
    ),
    code(P_FLOW),
    code(
        """
import time

inicio = time.perf_counter()
metricas = pipeline_bicis()
print(f"\\n{time.perf_counter() - inicio:.1f}s | {metricas}")
"""
    ),
    md(
        """
El modelo supera al baseline con margen amplio: un RMSE cercano a 125 bicicletas por
hora frente a unas 228 del promedio fijo. En la interfaz: la ejecución con sus siete
tasks, el artifact `bicis-metricas`, y en el log de `predecir_lote` la ruta del
Parquet.

Ahora la **segunda ejecución**, sin cambiar nada:
"""
    ),
    code(
        """
inicio = time.perf_counter()
pipeline_bicis()
print(f"\\n{time.perf_counter() - inicio:.1f}s  <- `entrenar` en estado Cached")
"""
    ),
    md(
        """
Más rápida, y en la interfaz `entrenar` aparece como **Cached**. Con otros
hiperparámetros —`pipeline_bicis(n_iteraciones=100)`— vuelve a entrenar, porque
cambió una entrada.

Si este notebook ya se había ejecutado antes, la **primera** ejecución también salió
rápida y con `entrenar` en `Cached`: la caché está en disco (`~/.prefect/storage/`),
no en el kernel, y dura lo que diga `cache_expiration` (aquí, un día). Es el
comportamiento correcto para un pipeline, aunque le quite contraste a la demostración.

Las predicciones, con su procedencia en cada fila:
"""
    ),
    code(
        """
predicciones = pd.read_parquet(PREDICCIONES)
print(predicciones.shape, "| ejecucion:", predicciones["flow_run_name"].iloc[0])
predicciones[["fecha", "hora", "total", "prediccion", "flow_run_id", "generado_en"]].head(8)
"""
    ),
    md(
        """
## 8. Del notebook al archivo

Todo lo anterior, junto, en `pipeline_bicis.py`. Es **el mismo código** de las celdas;
el notebook lo escribe para que no existan dos versiones que mantener. A partir de
aquí, el pipeline ya no necesita Jupyter.
"""
    ),
    code(
        "CODIGO_PIPELINE = r'''\n"
        + ARCHIVO_PIPELINE
        + "'''\n\n"
        + 'destino = Path("pipeline_bicis.py")\n'
        + 'destino.write_text(CODIGO_PIPELINE.lstrip("\\n"), encoding="utf-8")\n'
        + 'print(destino.resolve().relative_to(RAIZ), "-", len(destino.read_text().splitlines()), "lineas")\n'
    ),
    md(
        """
La prueba de que es independiente: ejecutarlo como script, en **otro proceso**, con el
mismo intérprete de Python de este entorno. `subprocess` es el módulo estándar para
lanzar programas externos desde Python.
"""
    ),
    code(
        """
import subprocess
import sys

salida = subprocess.run(
    [sys.executable, "pipeline_bicis.py"], capture_output=True, text=True, check=True
)
print(salida.stdout.strip().splitlines()[-1])
"""
    ),
    md(
        """
## 9. Programarlo: lo que sigue es terminal

Un pipeline que solo corre cuando alguien ejecuta una celda no resuelve el problema
original. Prefect ofrece `serve()`: deja el flow **escuchando** en un proceso y lo
ejecuta según un horario (`cron`) o cuando alguien lo lanza desde la interfaz, con los
parámetros que se le pasen. Ese proceso no termina, así que no se ejecuta desde el
notebook (bloquearía el kernel), sino desde una terminal en esta carpeta:

```bash
# Ejecutarlo una vez
uv run python pipeline_bicis.py

# Servirlo con un horario: todos los dias a las 6:00. Queda en Deployments en la interfaz.
uv run python -c "from pipeline_bicis import pipeline_bicis; pipeline_bicis.serve(name='bicis-diario', cron='0 6 * * *')"
```

La expresión `0 6 * * *` es sintaxis **cron**, el formato estándar de Unix para
horarios: minuto 0, hora 6, cualquier día, mes y día de la semana. Con eso, el
pipeline corre cada mañana sin nadie delante, y desde la interfaz se puede lanzar a
mano con otros parámetros —`n_iteraciones`, `mes_a_predecir`— que Prefect valida antes
de ejecutar.

## Resumen

Siete tasks que juntas forman un pipeline completo:

| Etapa | Concepto | Cómo se protege |
|---|---|---|
| descarga | fuentes externas fallan | `retries` con backoff y una fuente de respaldo |
| validación | los datos pueden venir mal | contrato de datos con pandera, antes de tocar el modelo |
| features | fuga de información | `FEATURES` excluye lo que "es" el target, y el contrato lo verifica |
| división | series de tiempo | por año, nunca al azar |
| entrenamiento | trabajo caro y repetido | caché por entradas + código, con semilla fija |
| evaluación | métricas sin referencia | baseline explícito y artifact con historia |
| inferencia | predicciones sin origen | id de la ejecución en cada fila |

Siguiente: [`../../s05-deployment/notebooks/01-el-flow-en-un-contenedor.ipynb`](../../s05-deployment/notebooks/01-el-flow-en-un-contenedor.ipynb),
donde este mismo `pipeline_bicis.py` se empaqueta en una imagen de Docker y se
ejecuta dentro de un contenedor.
"""
    ),
]


def main() -> None:
    for nombre, celdas, titulo in [
        ("01-prefect-paso-a-paso.ipynb", NB1, "Prefect paso a paso"),
        ("02-pipeline-ml-con-prefect.ipynb", NB2, "Un pipeline de ML con Prefect"),
    ]:
        nb = notebook(celdas, titulo)
        nbf.validate(nb)
        with (AQUI / nombre).open("w", encoding="utf-8") as fh:
            nbf.write(nb, fh)
        print(f"{nombre}: {len(nb.cells)} celdas")
    # El mismo texto que escribe la ultima celda de codigo del notebook 02.
    (AQUI / "pipeline_bicis.py").write_text(ARCHIVO_PIPELINE.lstrip("\n"), encoding="utf-8")
    print("pipeline_bicis.py:", len(ARCHIVO_PIPELINE.splitlines()), "lineas")


if __name__ == "__main__":
    main()
