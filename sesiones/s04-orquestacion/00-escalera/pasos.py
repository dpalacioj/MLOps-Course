"""Los tres pasos del pipeline, compartidos por los tres peldanos de la escalera.

Este archivo **no cambia** entre `1-script.py`, `2-cron/` y `3-orquestador.py`, y
eso es justamente el punto de la escalera: el codigo que hace el trabajo es el
mismo en los tres peldanos. Lo que cambia es *quien lo ejecuta* y *que queda
registrado cuando termina*.

Tres decisiones de diseno, para que la demo no dependa de nada fragil:

1. **Trabajo real, no `time.sleep`.** Los pasos generan, filtran y agregan un CSV
   de unos cientos de miles de filas. El costo de repetir un paso se puede medir
   con `time`, en vez de afirmarlo.
2. **Sin red y sin terceros.** La misma razon por la que
   `00-intro-prefect/pasos/03-reintentos.py` dejo de llamar a un endpoint publico:
   una demo de resiliencia que depende de un servicio ajeno falla en clase por el
   motivo equivocado.
3. **Sin metricas inventadas.** Aqui no se entrena nada. El pipeline de verdad
   esta en `src/taxi/flows/training.py`; esto es la maqueta minima que hace falta
   para tener tres pasos, un costo medible y un fallo. Los nombres dicen a que
   paso real corresponde cada uno.

El fallo se inyecta con la variable de entorno `ESCALERA_FALLAR_EN`:

    ESCALERA_FALLAR_EN=3   ->  el paso 3 falla

y es **transitorio**: falla en el primer intento y pasa en el segundo. Ningun
peldano puede aprovechar eso salvo el tercero, y ver esa diferencia es el
objetivo de la carpeta.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
import time
from pathlib import Path

#: Filas del CSV sintetico. Ajustable con ESCALERA_FILAS si la maquina de clase
#: es muy lenta o muy rapida: lo que importa es que un paso se sienta.
FILAS = int(os.environ.get("ESCALERA_FILAS", "2000000"))

#: Umbral del filtro del paso 2. Sin significado de negocio: es una maqueta.
UMBRAL_DURACION = 30.0

#: Momento en que se importo el modulo, para `cronometrar`.
_ARRANQUE = time.perf_counter()


def directorio_de_trabajo() -> Path:
    """Devuelve la carpeta donde los pasos dejan sus archivos intermedios.

    Va al directorio temporal del sistema, no al repositorio, por dos razones:
    no hay nada que agregar al `.gitignore`, y funciona igual cuando `cron` lo
    ejecuta con otro directorio de trabajo (ver `2-cron/`).
    """
    destino = Path(tempfile.gettempdir()) / "escalera-mlops"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def fallar_si_toca(paso: int, intento: int = 1) -> None:
    """Falla de forma determinista en `paso`, y solo en el primer intento.

    El numero de intento lo pasa quien llama. Un script pelado no tiene forma de
    saberlo y siempre pasa `1`, asi que siempre falla; un orquestador lee el
    contador de reintentos y en el segundo intento pasa de largo. La funcion es
    la misma: la diferencia esta en quien la llama.
    """
    objetivo = os.environ.get("ESCALERA_FALLAR_EN")
    if objetivo is None or objetivo.strip() != str(paso):
        return
    if intento > 1:
        print(f"  (el fallo del paso {paso} era transitorio; intento {intento} pasa)")
        return
    # ConnectionError y no Exception: el tipo de la excepcion es informacion
    # para quien lee el log a las 3 a.m.
    raise ConnectionError(
        f"fallo de red simulado en el paso {paso} (ESCALERA_FALLAR_EN={objetivo})"
    )


def paso_1_descargar(intento: int = 1) -> Path:
    """Paso 1 — hace de "descargar las particiones". Escribe el CSV crudo."""
    fallar_si_toca(1, intento)
    destino = directorio_de_trabajo() / "crudo.csv"
    with destino.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["viaje_id", "distancia_km", "duracion_min"])
        for i in range(FILAS):
            # Determinista a proposito: sin `random`, dos corridas producen el
            # mismo archivo y se pueden comparar. La duracion se deriva de la
            # distancia y de una velocidad entre 15 y 35 km/h, para que los
            # numeros del paso 3 sean plausibles y no distraigan en clase.
            distancia = round(0.8 + (i % 250) * 0.08, 2)
            velocidad = 15 + (i % 21)
            duracion = round(distancia / velocidad * 60, 2)
            escritor.writerow([i, distancia, duracion])
    print(f"  paso 1: {FILAS} filas -> {destino.name}")
    return destino


def paso_2_preparar(origen: Path, intento: int = 1) -> Path:
    """Paso 2 — hace de "construir las features". Filtra y escribe el CSV limpio."""
    fallar_si_toca(2, intento)
    destino = directorio_de_trabajo() / "limpio.csv"
    conservadas = 0
    with (
        origen.open(encoding="utf-8") as entrada,
        destino.open("w", newline="", encoding="utf-8") as salida,
    ):
        lector = csv.DictReader(entrada)
        escritor = csv.writer(salida)
        escritor.writerow(["viaje_id", "distancia_km", "duracion_min", "velocidad_kmh"])
        for fila in lector:
            duracion = float(fila["duracion_min"])
            if duracion > UMBRAL_DURACION:
                continue
            distancia = float(fila["distancia_km"])
            escritor.writerow(
                [fila["viaje_id"], distancia, duracion, round(distancia / (duracion / 60), 2)]
            )
            conservadas += 1
    print(f"  paso 2: {conservadas} filas conservadas -> {destino.name}")
    return destino


def paso_3_resumir(origen: Path, intento: int = 1) -> Path:
    """Paso 3 — hace de "entrenar y registrar". Escribe el resumen en JSON.

    No entrena un modelo. Calcula tres agregados sobre el CSV limpio, que son
    verificables a mano: eso es lo contrario de las metricas inventadas que se
    eliminaron de `workflows/artifacts-ml.py` (eliminado).
    """
    fallar_si_toca(3, intento)
    velocidades: list[float] = []
    with origen.open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            velocidades.append(float(fila["velocidad_kmh"]))

    resumen = {
        "filas": len(velocidades),
        "velocidad_media_kmh": round(sum(velocidades) / len(velocidades), 3),
        "velocidad_maxima_kmh": max(velocidades),
    }
    destino = directorio_de_trabajo() / "resumen.json"
    destino.write_text(json.dumps(resumen, indent=2) + "\n", encoding="utf-8")
    print(f"  paso 3: {resumen} -> {destino.name}")
    return destino


def cronometrar(etiqueta: str) -> None:
    """Imprime el tiempo transcurrido desde el arranque del proceso."""
    print(f"{etiqueta} en {time.perf_counter() - _ARRANQUE:.1f} s")
