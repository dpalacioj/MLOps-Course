#!/usr/bin/env python
"""Genera el notebook de esta carpeta con nbformat, sin outputs.

El .ipynb se publica sin outputs y este archivo es la fuente de verdad. El notebook
escribe `contenedor-bicis/` —el Dockerfile, el pyproject.toml y el .dockerignore— y
copia ahi el `pipeline_bicis.py` de `sesiones/s04-orquestacion/notebooks/` para
construir la imagen.

Uso:
    uv run python sesiones/s05-deployment/notebooks/_generar_notebooks.py
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


# Los tres archivos que el notebook escribe. Estan aqui como texto para que el
# notebook los muestre completos en la celda que los escribe.
PYPROJECT = """
# Proyecto minimo e INDEPENDIENTE del paquete de la raiz del repositorio: la imagen
# instala solo lo que `pipeline_bicis.py` importa. Restricciones `>=`, no versiones
# exactas: la version exacta la fija `uv.lock`, que es la unica fuente de verdad.
[project]
name = "bicis-pipeline"
version = "1.0.0"
description = "Pipeline de entrenamiento e inferencia sobre el dataset de bicis, empaquetado."
requires-python = ">=3.11"
dependencies = [
    "prefect>=3.4.12",
    "pandas>=2.3.1",
    "pyarrow>=21.0.0",
    "pandera>=0.22.1",
    "scikit-learn>=1.6.1",
    "httpx>=0.27.0",
]

# Sin [build-system]: es un script, no un paquete que construir.
[tool.uv]
package = false
"""

DOCKERIGNORE = """
# Lo que NO entra al build context. Aqui el contexto es diminuto y la regla esta por
# el habito: en un repositorio real es lo que evita mandar datos, entornos virtuales
# y secretos al demonio de Docker en cada build (y, peor, dentro de una capa de la
# imagen, de donde ya no salen).
.venv/
__pycache__/
*.py[cod]
.env
.env.*
Dockerfile
.dockerignore
"""

DOCKERFILE = """
# syntax=docker/dockerfile:1
# Imagen del pipeline de bicis, en una sola etapa. Cinco decisiones:
#   1. imagen base "slim" y con version fija (nunca `python:latest`)
#   2. dependencias antes que codigo, para aprovechar la cache de capas
#   3. instalacion desde el LOCKFILE, no desde versiones escritas a mano
#   4. usuario sin privilegios, con un HOME escribible
#   5. un proceso que termina solo: es un job, no un servidor (por eso no hay HEALTHCHECK)

FROM python:3.11-slim-bookworm

# El binario de uv se copia de su imagen oficial, con version fija, en vez de
# instalarlo con pip: la imagen no arrastra pip ni caches de descarga.
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv

# El entorno virtual fuera del arbol del proyecto y con el interprete de la imagen.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PYTHON=/usr/local/bin/python3
ENV UV_LINK_MODE=copy
# Los logs salen a stdout en el momento: sin esto, `docker logs` de un contenedor
# que acaba de fallar sale vacio.
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Capa 1: solo manifiesto y lock. Cambian poco; el codigo cambia en cada edicion.
# `--locked` falla si uv.lock no esta al dia con pyproject.toml, en vez de
# re-resolver en silencio.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# Capa 2: el codigo.
COPY pipeline_bicis.py ./

# Usuario sin privilegios. `--create-home` importa: Prefect guarda su configuracion,
# la base de datos del servidor efimero y los resultados cacheados en ~/.prefect, y
# un usuario sin HOME escribible no puede crear ese directorio.
RUN groupadd --system --gid 1001 bicis \\
    && useradd --system --uid 1001 --gid bicis --create-home bicis \\
    && chown -R bicis:bicis /app
USER bicis

# Forma exec (lista, sin shell): el proceso es PID 1 y recibe las senales directo.
CMD ["python", "pipeline_bicis.py"]
"""

NB1 = [
    md(
        """
# El pipeline dentro de un contenedor

## De qué trata este notebook

`pipeline_bicis.py` —el archivo que produce el segundo notebook de
`sesiones/s04-orquestacion/notebooks/`— corre en la máquina donde se escribió, con
el entorno virtual de ese repositorio y los datos que hay en ese disco. Para que corra
en cualquier otra máquina igual que aquí, se **empaqueta** en una imagen de Docker.
Este notebook hace ese empaquetado paso a paso, y después ejecuta el pipeline tres
veces dentro de un contenedor, cada una añadiendo lo que la anterior demostró que
faltaba.

## Vocabulario mínimo de Docker

- Un **contenedor** es un proceso normal del sistema operativo al que Docker le
  muestra un sistema de archivos propio, una red propia y una lista de procesos propia.
  No es una máquina virtual: no hay otro núcleo de sistema operativo, y por eso arranca
  en milisegundos.
- Una **imagen** es la plantilla de la que se crean contenedores: el código, sus
  dependencias y el intérprete de Python, congelados en capas. De una imagen pueden
  correr muchos contenedores idénticos.
- Un **Dockerfile** es la receta para construir la imagen, instrucción por instrucción.
  Cada instrucción produce una **capa**, y Docker reutiliza las capas que no cambiaron
  entre un build y el siguiente.
- El **build context** es la carpeta que se le entrega a `docker build`. Solo lo que
  está dentro de ella puede copiarse a la imagen.

## Las tres ejecuciones

| Ejecución | Qué se añade al `docker run` | Qué demuestra |
|---|---|---|
| 1 | nada | el contenedor está **aislado**: otro hostname, sin los datos locales, sin el servidor de Prefect local |
| 2 | `-e PREFECT_API_URL=...host.docker.internal...` | la **red**: cómo un contenedor llega a un servicio de la máquina anfitriona |
| 3 | `-v .../data:/app/data` | los **volúmenes**: cómo los archivos sobreviven al contenedor |

Docker se maneja desde una terminal. Aquí cada comando va en una celda de Python que
lo ejecuta y muestra su salida, para intercalar la explicación; el resultado es el
mismo que teclearlo en la terminal, y al terminar conviene repetir las tres
ejecuciones a mano.

## Requisitos

- **Docker Desktop** abierto (o el demonio de Docker corriendo). La primera celda lo
  comprueba.
- El servidor de Prefect corriendo en una terminal (`uv run prefect server start`),
  para las ejecuciones 2 y 3.
- Haber ejecutado el notebook `02-pipeline-ml-con-prefect.ipynb` de la carpeta
  `sesiones/s04-orquestacion/notebooks/`, que escribe el `pipeline_bicis.py` que aquí
  se empaqueta.

**Tiempo:** el `docker build` tarda entre dos y cinco minutos la primera vez (descarga
la imagen base e instala scikit-learn). Las siguientes, segundos.
"""
    ),
    md(
        """
## 0. Un ayudante, y comprobar Docker

`sh()` ejecuta un comando, imprime la línea tal como se escribiría en la terminal y
debajo su salida. Usa `subprocess`, el módulo estándar de Python para lanzar
programas externos. Todo lo que sigue pasa por aquí, así que lo que se ve es
exactamente lo que Docker respondió.
"""
    ),
    code(
        '''
import shutil
import socket
import subprocess
from pathlib import Path


def sh(*comando: str, cwd: Path | None = None, mostrar: int = 40) -> None:
    """Ejecuta un comando y muestra las ultimas `mostrar` lineas de su salida."""
    print("$", " ".join(comando))
    proceso = subprocess.run(comando, capture_output=True, text=True, cwd=cwd)
    salida = (proceso.stdout + proceso.stderr).strip()
    lineas = salida.splitlines()
    if len(lineas) > mostrar:
        print(f"  ... ({len(lineas) - mostrar} lineas omitidas)")
        lineas = lineas[-mostrar:]
    print("\\n".join(lineas))
    if proceso.returncode != 0:
        raise RuntimeError(f"el comando termino con codigo {proceso.returncode}")


try:
    sh("docker", "info", "--format", "Docker {{.ServerVersion}} en {{.OperatingSystem}}")
except (FileNotFoundError, RuntimeError) as exc:
    raise RuntimeError("Docker no responde. Hay que abrir Docker Desktop y volver a ejecutar esta celda.") from exc
'''
    ),
    md(
        """
## 1. El build context: lo que Docker puede ver

`docker build` recibe **una carpeta** y solo puede copiar a la imagen archivos que
estén dentro de ella. `pipeline_bicis.py` vive en otra carpeta del repositorio, así que
se copia aquí antes de construir. La copia no se versiona (está en `.gitignore`): la
fuente de verdad sigue siendo el notebook que lo genera.
"""
    ),
    code(
        """
RAIZ = Path.cwd()
while not (RAIZ / "pyproject.toml").exists() and RAIZ.parent != RAIZ:
    RAIZ = RAIZ.parent

ORIGEN = RAIZ / "sesiones" / "s04-orquestacion" / "notebooks" / "pipeline_bicis.py"
CONTEXTO = RAIZ / "sesiones" / "s05-deployment" / "notebooks" / "contenedor-bicis"

if not ORIGEN.exists():
    raise FileNotFoundError(
        f"no existe {ORIGEN.relative_to(RAIZ)}: hay que ejecutar antes el notebook 02 de s04-orquestacion"
    )
CONTEXTO.mkdir(exist_ok=True)
shutil.copy(ORIGEN, CONTEXTO / "pipeline_bicis.py")
print("build context:", CONTEXTO.relative_to(RAIZ))
print("contiene:", sorted(p.name for p in CONTEXTO.iterdir()))
"""
    ),
    md(
        """
## 2. Tres archivos: `pyproject.toml`, `.dockerignore`, `Dockerfile`

**`pyproject.toml`** es el archivo estándar de Python para describir un proyecto y sus
dependencias. Este declara **solo** lo que `pipeline_bicis.py` importa. No hereda del
`pyproject.toml` de la raíz del repositorio a propósito: la imagen no necesita MLflow,
FastAPI ni el resto de herramientas del repositorio, y cada dependencia que sobra es
tamaño, tiempo de build y superficie de ataque.

Las versiones van con `>=` y no con `==`: la versión exacta de cada paquete la fija
el *lockfile* de la sección 3. Escribir `==` aquí y tener además un lockfile es
mantener la misma decisión en dos archivos que se desincronizan.
"""
    ),
    code(
        'PYPROJECT = """'
        + PYPROJECT
        + '"""\n\n'
        + '(CONTEXTO / "pyproject.toml").write_text(PYPROJECT.lstrip("\\n"), encoding="utf-8")\n'
        + "print(PYPROJECT.strip())\n"
    ),
    md(
        """
**`.dockerignore`** lista lo que no debe entrar al build context. Todo lo que entra lo
empaqueta y transfiere el demonio de Docker en cada build, y puede acabar dentro de
una capa de la imagen; una capa no se "borra" con un `RUN rm` posterior, sigue ahí y es
pública si la imagen se publica. No reemplaza al `.gitignore`: son dos listas con dos
propósitos —qué no se versiona, qué no se construye—.
"""
    ),
    code(
        'DOCKERIGNORE = """'
        + DOCKERIGNORE
        + '"""\n\n'
        + '(CONTEXTO / ".dockerignore").write_text(DOCKERIGNORE.lstrip("\\n"), encoding="utf-8")\n'
        + "print(DOCKERIGNORE.strip())\n"
    ),
    md(
        """
**`Dockerfile`**, la receta. Se lee de arriba abajo:

- `FROM python:3.11-slim-bookworm`: la imagen base. *slim* es la variante mínima de
  Debian con Python; la versión va fija porque `latest` cambia bajo los pies.
- `COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv`: trae el binario de `uv` desde
  su imagen oficial, con versión fija, sin instalar pip.
- Las variables `ENV` configuran `uv` para instalar en `/opt/venv` con el intérprete de
  la imagen, y `PYTHONUNBUFFERED=1` hace que los logs salgan al momento.
- `COPY pyproject.toml uv.lock` y `RUN uv sync --locked` **antes** de `COPY
  pipeline_bicis.py`: las dependencias cambian poco y el código cambia en cada
  edición. Con este orden, editar el código reutiliza la capa de dependencias en vez de
  reinstalar todo. Invertirlo es el error de caché de capas más común.
- `useradd ... --create-home` y `USER bicis`: el proceso no corre como `root`. Si
  alguien lograra ejecutar código dentro del contenedor, con `root` tendría mucho más
  margen. El `--create-home` no es cosmético: Prefect guarda su configuración, la base
  de datos de su servidor efímero y los resultados cacheados en `~/.prefect`, y sin un
  HOME escribible la caché falla en silencio dentro del contenedor.
- `CMD ["python", "pipeline_bicis.py"]`: lo que se ejecuta al arrancar. En forma de
  lista, sin shell intermedia, para que el proceso reciba las señales del sistema
  directamente.
"""
    ),
    code(
        'DOCKERFILE = r"""'
        + DOCKERFILE
        + '"""\n\n'
        + '(CONTEXTO / "Dockerfile").write_text(DOCKERFILE.lstrip("\\n"), encoding="utf-8")\n'
        + "print(DOCKERFILE.strip())\n"
    ),
    md(
        """
## 3. El lockfile

`uv lock` resuelve el árbol **completo** de dependencias —las declaradas y las que
estas arrastran— y lo congela en `uv.lock`, con versiones exactas y sumas de
verificación. Es lo que hace que el build de hoy y el de dentro de tres meses instalen
exactamente lo mismo. Un `requirements.txt` con tres líneas no lo garantiza: fija las
dependencias directas y deja libres las decenas de transitivas.

El `Dockerfile` usa `--locked` para **fallar** si el lock no está al día con
`pyproject.toml`, en lugar de re-resolver en silencio.

En un proyecto real el `uv.lock` se versiona junto al código: es la garantía de
reproducibilidad. Aquí no se versiona porque esta celda lo regenera en cada ejecución
y el repositorio limita el tamaño de los archivos que acepta.
"""
    ),
    code(
        """
sh("uv", "lock", cwd=CONTEXTO)
print("\\nlock:", round((CONTEXTO / "uv.lock").stat().st_size / 1024), "KB")
"""
    ),
    md(
        """
## 4. Construir la imagen

La primera vez tarda minutos: descarga `python:3.11-slim-bookworm` e instala
scikit-learn y pandas. En la salida se ve cada capa (`#5`, `#6`, ...) con su tiempo. Si
después se edita `pipeline_bicis.py` y se reconstruye, todo hasta `uv sync` sale como
`CACHED` y el build tarda segundos: ese es el motivo del orden de las capas.

`-t bicis-pipeline:dev` le pone a la imagen un nombre y una etiqueta (*tag*). La
etiqueta es un alias que puede moverse a otra imagen; el identificador estable es el
`id=` que imprime `docker images`, un hash del contenido.
"""
    ),
    code(
        """
IMAGEN = "bicis-pipeline:dev"
sh("docker", "build", "-t", IMAGEN, str(CONTEXTO), mostrar=15)
sh("docker", "images", IMAGEN, "--format", "{{.Repository}}:{{.Tag}}  {{.Size}}  id={{.ID}}")
"""
    ),
    md(
        """
## 5. Ejecución 1: el contenedor está aislado

Primero la diferencia más visible. `docker run --rm IMAGEN hostname` arranca un
contenedor, ejecuta `hostname` en vez del `CMD` de la imagen, y lo borra al terminar
(`--rm`). El nombre de máquina que devuelve no es el de la máquina anfitriona.
"""
    ),
    code(
        """
print("maquina anfitriona:", socket.gethostname())
sh("docker", "run", "--rm", IMAGEN, "hostname")
"""
    ),
    md(
        """
Ahora el pipeline, tal cual, sin decirle nada al contenedor. Tres cosas para observar
en la salida:

1. **Descarga el CSV** aunque en la máquina anfitriona ya esté en `data/external/`:
   dentro del contenedor ese directorio no existe.
2. Al terminar, el Parquet de predicciones **desaparece** con el contenedor (`--rm`).
3. En la interfaz web de Prefect de la máquina anfitriona no aparece ninguna
   ejecución: sin `PREFECT_API_URL`, Prefect levanta un servidor **efímero dentro del
   contenedor**, que muere con él. Por eso tarda unos segundos más en arrancar.
"""
    ),
    code(
        """
sh("docker", "run", "--rm", IMAGEN, mostrar=25)
"""
    ),
    md(
        """
## 6. Ejecución 2: la red, o cómo llegar al servidor de la máquina anfitriona

Dentro del contenedor, `127.0.0.1` es el contenedor mismo, así que la dirección del
servidor de Prefect configurada en la máquina anfitriona no sirve. Docker Desktop
ofrece el nombre `host.docker.internal`, que desde dentro del contenedor resuelve a la
máquina anfitriona. Con `-e` se pasa una variable de entorno al contenedor, y Prefect
lee `PREFECT_API_URL` de ahí. Con eso, la ejecución se registra en el servidor de la
máquina anfitriona y aparece en su interfaz, con sus siete tasks.

> **En Linux** ese nombre no existe por defecto: hay que añadir
> `--add-host=host.docker.internal:host-gateway` al `docker run`, y el servidor de
> Prefect tiene que escuchar en todas las interfaces de red
> (`prefect server start --host 0.0.0.0`), porque la conexión llega por la red del
> puente de Docker y no por *loopback*.
"""
    ),
    code(
        """
API_DESDE_EL_CONTENEDOR = "http://host.docker.internal:4200/api"
sh(
    "docker", "run", "--rm",
    "-e", f"PREFECT_API_URL={API_DESDE_EL_CONTENEDOR}",
    IMAGEN,
    mostrar=25,
)
print("\\nInterfaz -> Runs: la ultima ejecucion de `pipeline-bicis` vino del contenedor")
"""
    ),
    md(
        """
## 7. Ejecución 3: los volúmenes, o cómo los archivos sobreviven

Un **volumen** (`-v origen:destino`) monta una carpeta de la máquina anfitriona dentro
del contenedor. Con `data/` montada en `/app/data`:

- `descargar` encuentra el CSV en `data/external/` y **no baja nada**;
- `predecir_lote` escribe el Parquet en `data/processed/`, y ahí se queda cuando el
  contenedor termina.

El contenedor sigue siendo efímero. Lo que persiste es lo que se decidió montar.
"""
    ),
    code(
        """
sh(
    "docker", "run", "--rm",
    "-e", f"PREFECT_API_URL={API_DESDE_EL_CONTENEDOR}",
    "-v", f"{RAIZ / 'data'}:/app/data",
    IMAGEN,
    mostrar=25,
)

import pandas as pd

predicciones = pd.read_parquet(RAIZ / "data" / "processed" / "predicciones-bicis.parquet")
print("\\nescrito desde el contenedor, leido desde la maquina anfitriona:")
print(predicciones[["fecha", "hora", "prediccion", "flow_run_name", "generado_en"]].head(3).to_string(index=False))
"""
    ),
    md(
        """
## 8. Qué cambió y qué no

| | En la máquina anfitriona | En el contenedor |
|---|---|---|
| El código | `pipeline_bicis.py` | **el mismo archivo**, copiado en la capa 2 |
| Las dependencias | el `.venv` del repositorio | `/opt/venv`, instalado desde el `uv.lock` de esta carpeta |
| `hostname` | el de la máquina | uno aleatorio por contenedor |
| `data/` | el disco local | no existe, salvo que se monte (`-v`) |
| El servidor de Prefect | `127.0.0.1:4200` | efímero y propio, salvo que se apunte a otro (`-e`) |
| Quién ejecuta | el usuario de la sesión | `bicis`, uid 1001, sin privilegios |

Lo único que no cambió es lo que importa: **el pipeline**. Todo lo demás —red, disco,
identidad— pasó a ser configuración explícita del `docker run`. Eso es lo que compra el
contenedor: que "en mi máquina funciona" deje de ser un argumento, porque la máquina
va dentro.

Para limpiar la imagen al terminar: `docker rmi bicis-pipeline:dev`. La carpeta
`intro-dockers/`, junto a esta, recorre las mismas decisiones del `Dockerfile` sobre
una aplicación web, incluido el `HEALTHCHECK` que un job como este no necesita.
"""
    ),
]


def main() -> None:
    nb = notebook(NB1, "El pipeline dentro de un contenedor")
    nbf.validate(nb)
    with (AQUI / "01-el-flow-en-un-contenedor.ipynb").open("w", encoding="utf-8") as fh:
        nbf.write(nb, fh)
    print(f"01-el-flow-en-un-contenedor.ipynb: {len(nb.cells)} celdas")


if __name__ == "__main__":
    main()
