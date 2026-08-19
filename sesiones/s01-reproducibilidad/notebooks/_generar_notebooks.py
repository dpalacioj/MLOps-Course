#!/usr/bin/env python
"""Genera el notebook de la sesion 1 con nbformat, sin outputs.

Por que un generador y no un .ipynb editado a mano: un notebook es JSON con
metadatos y outputs embebidos. Editarlo a mano produce diffs ilegibles, conflictos
de merge en cada cohorte y, sobre todo, el riesgo de publicar outputs con rutas
absolutas del disco de quien lo ejecuto (que es exactamente lo que le paso al
notebook anterior de esta sesion, 175 KB de los cuales ~82 KB eran una imagen en
base64 en el campo `attachments`).

Este archivo es texto plano revisable en un PR y garantiza que el .ipynb se publica
sin outputs y sin attachments.

Uso:
    uv run python sesiones/s01-reproducibilidad/notebooks/_generar_notebooks.py
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
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
        "titulo": titulo,
    }
    return nb


# =============================================================================
# 01 — Del notebook al paquete
# =============================================================================
NB1 = [
    md(
        """
# S01 · 01 — Del notebook al paquete: el mismo análisis, tres veces

**Este es "el dolor" de la sesión 1.** No se abre `uv` hasta el bloque A.

**Objetivo.** Calcular una métrica trivial —la duración media de un viaje de taxi
verde en 2023-01— de **tres** maneras, y comprobar que el número es el mismo. Lo que
cambia no es el resultado: es quién puede reproducirlo.

| Estado | Cómo se ejecuta | Qué garantiza |
|---|---|---|
| 1. Caótico | celdas fuera de orden, `!pip install` a mitad, constantes reescritas | nada |
| 2. Script | `python analisis.py` | reproducible en esta carpeta |
| 3. Paquete | `from taxi.data import loaders` | reproducible en cualquier máquina, y testeable |

**Requisito.** Haber corrido `uv run taxi data` (o `make data`) al menos una vez, para
que las particiones estén en `data/raw/`. Si no las tienes, la primera celda te lo
dice y el notebook sigue funcionando en modo degradado.

> **Regla del notebook:** este archivo se publica **sin outputs**. Si un resultado
> importa, se escribe en una celda de markdown o se guarda en `reports/`. El `hook`
> de `nbstripout` te va a limpiar los outputs al commitear, así que no los uses como
> memoria.
"""
    ),
    code(
        """
# Punto de partida comun a los tres estados. Esto NO es parte de la demostracion:
# es solo localizar el parquet y avisar si falta.
from pathlib import Path

RAIZ = Path.cwd()
while not (RAIZ / "pyproject.toml").exists() and RAIZ != RAIZ.parent:
    RAIZ = RAIZ.parent

PARQUET = RAIZ / "data" / "raw" / "green_tripdata_2023-01.parquet"
print("raiz del repositorio:", RAIZ.name)
print("parquet presente:", PARQUET.exists())
if not PARQUET.exists():
    print()
    print("Corre `uv run taxi data` (o `make data`) y vuelve a ejecutar esta celda.")
    print("Las particiones son fijas (ver docs/adr/001-caso-guia-y-particiones.md):")
    print("no dependen del mes en que estemos, asi que se descargan una sola vez.")
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## Estado 1 — El notebook caótico

Lo que viene es una reconstrucción fiel de un notebook real. Tiene cuatro problemas,
y **ninguno de los cuatro produce un error**. Antes de ejecutar nada, busca los
cuatro:

1. una dependencia instalada a mitad del notebook, que no queda declarada en ningún
   archivo;
2. constantes de negocio (los límites de duración válida) escritas a mano, con dos
   valores distintos en dos celdas;
3. una celda que **depende del estado del kernel** dejado por otra celda que puede no
   haberse ejecutado;
4. el resultado guardado en una variable global que las celdas siguientes
   sobrescriben.

**Instrucción para la clase:** ejecuta estas celdas **en desorden** —la 3, luego la
1, luego la 2— y compara el número. Después haz `Kernel → Restart & Run All`.
"""
    ),
    code(
        """
# --- CELDA "12" del notebook original: pip install a mitad del analisis ---
# ANTI-PATRON. Se deja aqui a proposito, comentado, porque ejecutarlo modificaria
# tu entorno del curso.
#
#   !pip install pandas==1.5.3
#
# Tres preguntas que nadie puede responder mirando este notebook:
#   - en QUE entorno instalo (el del kernel? otro?)
#   - por que 1.5.3, y quien lo decidio
#   - donde queda registrado, para que la siguiente persona instale lo mismo
#
# Y la peor: con pandas 1.5.3 este mismo notebook da otro numero, porque cambio el
# comportamiento por defecto de varias operaciones entre 1.x y 2.x.
print("celda de pip install: no ejecutada (a proposito)")
"""
    ),
    code(
        """
# --- Celda A: cargar ---
import pandas as pd

df = pd.read_parquet(PARQUET)  # noqa: F821  (depende de una celda anterior)
print(len(df), "filas")
"""
    ),
    code(
        """
# --- Celda B: "limpiar". Constantes escritas a mano, version 1 ---
df["duration"] = (df.lpep_dropoff_datetime - df.lpep_pickup_datetime).dt.total_seconds() / 60
df = df[(df.duration >= 1) & (df.duration <= 60)]
print("media:", round(df.duration.mean(), 4))
"""
    ),
    code(
        """
# --- Celda C: la misma "limpieza", con OTRO limite. Version 2 ---
# Aqui esta el bug real: alguien probo con 90 minutos, no lo revirtio, y esta celda
# sobrescribe `df`. Ejecutar B->C, C->B o solo C da TRES numeros distintos.
df = pd.read_parquet(PARQUET)
df["duration"] = (df.lpep_dropoff_datetime - df.lpep_pickup_datetime).dt.total_seconds() / 60
df = df[(df.duration >= 1) & (df.duration <= 90)]  # <-- 90, no 60
print("media:", round(df.duration.mean(), 4))
"""
    ),
    md(
        """
### Lo que acaba de pasar

Las celdas B y C hacen "lo mismo" y dan números distintos, porque el límite superior
de duración válida —una **decisión de negocio**— está escrito a mano en dos sitios.
No hay un error en pantalla. Hay dos verdades.

Y el problema estructural es el orden: en un notebook, el resultado depende del
**estado del kernel**, no del archivo. El archivo que commiteas no contiene la
información necesaria para reproducir su propia salida.

**Prueba diagnóstica, 5 segundos:** `Kernel → Restart & Run All`. Si tu notebook no
pasa esa prueba, no es reproducible, y da igual lo bonitos que sean los gráficos.

Y todavía queda lo que no se ve: si este notebook se hubiera commiteado con sus
`outputs`, el diff del PR sería ilegible y los `outputs` llevarían la ruta absoluta
del disco de quien lo ejecutó.
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## Estado 2 — El script

Mismo cálculo, en un archivo que se ejecuta de arriba abajo. Es una mejora **real**,
no cosmética:

- el orden de ejecución es el orden del archivo. Ya no hay estado oculto;
- las constantes están arriba, en un solo sitio;
- se puede correr en CI: `python analisis.py`.

Lo que **todavía** no se puede hacer:

- importar una parte para probarla por separado (`from analisis import limpiar`
  ejecutaría todo el script si no está protegido con `if __name__`);
- reutilizarlo desde otro script sin copiar y pegar;
- garantizar que quien lo ejecute tenga las mismas versiones de librerías.
"""
    ),
    code(
        """
# Escribimos el script en un temporal y lo ejecutamos como lo haria un CI.
# No se commitea: es un paso intermedio de la demostracion.
import subprocess
import sys
import tempfile
import textwrap

SCRIPT = textwrap.dedent('''
    # Duracion media de un viaje de taxi verde. Estado 2: script.
    import sys
    from pathlib import Path

    import pandas as pd

    # Las constantes, en UN solo sitio. Es la mejora de este estado.
    DURACION_MIN_MIN = 1.0
    DURACION_MAX_MIN = 60.0


    def main(ruta: str) -> float:
        df = pd.read_parquet(ruta)
        delta = df["lpep_dropoff_datetime"] - df["lpep_pickup_datetime"]
        df["duration"] = delta.dt.total_seconds() / 60.0
        df = df[df["duration"].between(DURACION_MIN_MIN, DURACION_MAX_MIN)]
        media = float(df["duration"].mean())
        print(f"{len(df)} filas | media {media:.4f} min")
        return media


    if __name__ == "__main__":
        main(sys.argv[1])
''')

with tempfile.TemporaryDirectory() as tmp:
    ruta_script = Path(tmp) / "analisis.py"
    ruta_script.write_text(SCRIPT, encoding="utf-8")
    salida = subprocess.run(
        [sys.executable, str(ruta_script), str(PARQUET)],
        capture_output=True,
        text=True,
        check=False,
    )
    print(salida.stdout or salida.stderr)
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## Estado 3 — El paquete instalable

Ahora el mismo cálculo usando el paquete del curso. Fíjate en lo que **no** hay en
la celda siguiente: ni la ruta del parquet, ni los límites de duración, ni la
semilla. Todo eso vive en un solo sitio,
[`src/taxi/config.py`](../../../src/taxi/config.py), y el resto del repositorio lo
importa.

Eso no es elegancia: es la condición para que el número de la sesión 3 sea
comparable con el de la sesión 7.
"""
    ),
    code(
        """
from taxi.config import DURACION_MAX_MIN, DURACION_MIN_MIN, PARTICIONES_TRAIN, RAW_DIR
from taxi.features import contract as fc

print("particiones de entrenamiento:", [p.etiqueta for p in PARTICIONES_TRAIN])
print("duracion valida:", DURACION_MIN_MIN, "-", DURACION_MAX_MIN, "min")
print("features del modelo:", fc.FEATURES)
print("datos crudos en:", RAW_DIR.relative_to(RAW_DIR.parents[1]))
"""
    ),
    code(
        """
import pandas as pd

from taxi.config import DURACION_MAX_MIN, DURACION_MIN_MIN, PARTICIONES_TRAIN, RAW_DIR
from taxi.features import contract as fc

particion = PARTICIONES_TRAIN[0]  # 2023-01, FIJA. Nunca datetime.now()
crudo = pd.read_parquet(RAW_DIR / particion.nombre_archivo)

delta = crudo[fc.COL_DROPOFF] - crudo[fc.COL_PICKUP]
crudo["duration"] = delta.dt.total_seconds() / 60.0
limpio = crudo[crudo["duration"].between(DURACION_MIN_MIN, DURACION_MAX_MIN)]

print(f"{particion}: {len(limpio)} filas | media {limpio['duration'].mean():.4f} min")
"""
    ),
    md(
        """
### El mismo número, y tres propiedades nuevas

El resultado coincide con el del estado 2 (y con la celda B del estado 1). Lo que ha
cambiado es todo lo demás:

1. **Los límites son una decisión, no una constante suelta.** Están en `config.py`
   con un comentario que dice por qué: *"fuera de ese rango son errores de captura
   (viajes de 0 min o de 8 horas), no viajes"*. Cambiarlos es un commit revisable.
2. **La partición es fija.** `PARTICIONES_TRAIN[0]` es siempre 2023-01. El
   `pipeline` anterior del curso calculaba el periodo con `datetime.now()` y pedía
   `green_tripdata_2025-01.parquet`, un archivo que la NYC TLC puede no haber
   publicado. Un curso no puede depender del calendario de un tercero
   ([ADR 001](../../../docs/adr/001-caso-guia-y-particiones.md)).
3. **Es testeable.** `pytest tests/` ejercita este código sin red, con `fixtures`
   sintéticos deterministas.

Y una cuarta, que es la de esta sesión: el paquete se instala desde `uv.lock`, así
que las versiones con las que salió este número están **declaradas**.
"""
    ),
    code(
        """
# La forma final: una funcion del paquete que hace las cinco cosas en el orden
# correcto (leer, validar el contrato, filtrar, muestrear, derivar features) y
# vuelve a validar al final. Lo que en el estado 1 estaba repartido en tres celdas
# contradictorias, aqui es una llamada.
from taxi.config import PARTICIONES_TRAIN
from taxi.data.loaders import preparar_particion

listo = preparar_particion(PARTICIONES_TRAIN[0], filas=20_000)
print(listo.shape)
print(listo.columns.tolist())
print(f"media de duration: {listo['duration'].mean():.4f} min")
"""
    ),
    md(
        """
> **Ojo con el número de esta última celda.** No coincide con los anteriores, y eso
> **no es un bug**: `preparar_particion` además muestrea (20.000 filas de forma
> determinista) y filtra por distancia. Es un buen momento para preguntar en clase
> por qué el muestreo determinista con semilla fija sigue siendo reproducible aunque
> el número cambie, y en qué se diferencia eso del desorden del estado 1.
>
> La diferencia es exactamente esta: en el estado 1 no sabías **qué** número tenías.
> Aquí sabes qué transformaciones se aplicaron, en qué orden, con qué semilla, y
> puedes volver a obtenerlo.
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## El resumen que hay que llevarse

| | Caótico | Script | Paquete |
|---|---|---|---|
| El resultado depende del orden en que le diste a Shift+Enter | **sí** | no | no |
| Las constantes están en un solo sitio | no | sí | sí, y compartido por todo el repo |
| Se puede importar una parte para probarla | no | no | **sí** |
| Se puede testear | no | apenas | **sí** (`pytest tests/`) |
| Las versiones de las librerías están declaradas | no | no | **sí** (`uv.lock`) |
| Otra máquina llega al mismo número | por casualidad | quizá | **sí, por construcción** |

**La frase de la sesión:** la reproducibilidad no es una propiedad del resultado, es
una propiedad del proceso. El estado 1 y el estado 3 imprimieron el mismo número; solo
uno de los dos lo puede volver a hacer.

### Y entonces, ¿los notebooks son malos?

No. Son la mejor herramienta que existe para **explorar** y para **explicar**. Este
archivo es un notebook. La sesión 2 usa tres.

La regla que separa el uso legítimo del abuso es una: **el notebook explora, el
paquete decide.** Si un número tiene consecuencias —entra en un `report`, se compara
con un `baseline`, alimenta una decisión de promoción— el código que lo produce vive
en `src/`, con tests, y el notebook lo importa. Es exactamente la política del
repositorio del curso, y el criterio nº 1 del
[taller de la sesión 7](../../s07-monitoreo/taller.md).

---

## Ejercicios (5 min, antes de la pausa)

1. **`Restart & Run All`** en este notebook. ¿Sale todo? ¿Y en el último notebook que
   escribiste tú?
2. Cambia `DURACION_MAX_MIN` en `src/taxi/config.py` a `90` y vuelve a correr la
   celda del estado 3. Un solo cambio, en un solo sitio, y el número se mueve.
   **Deshaz el cambio** (`git checkout src/taxi/config.py`).
3. Corre `uv run pytest tests/unit/test_config_y_convenciones.py -q`. Hay tests que
   protegen esas constantes de cambios accidentales. Lee uno.
4. Busca en `src/taxi/features/contract.py` el comentario que explica por qué
   `PU_DO` se deriva y no llega en el parquet. Ese comentario documenta un
   `KeyError` que tumbaba el `pipeline` estrella del curso anterior.

Siguiente: [`entorno.md`](../entorno.md) — bloque A.
"""
    ),
]


def main() -> None:
    for nombre, celdas, titulo in [
        ("01-del-notebook-al-paquete.ipynb", NB1, "S01 01 - Del notebook al paquete"),
    ]:
        nb = notebook(celdas, titulo)
        nbf.validate(nb)
        destino = AQUI / nombre
        with destino.open("w", encoding="utf-8") as fh:
            nbf.write(nb, fh)
        print(f"{nombre}: {len(nb.cells)} celdas")


if __name__ == "__main__":
    main()
