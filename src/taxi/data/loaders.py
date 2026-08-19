"""Descarga, verificacion y preparacion de datos.

Cambios respecto al repo anterior:

1. **Particiones fijas** (`config.py`), no `datetime.now()`. El pipeline pedia
   2025-01, un parquet que puede no estar publicado todavia.
2. **Verificacion por hash**. Se registra el SHA-256 de cada archivo en
   `data/raw/metadata.json`. Ese archivo estaba gitignorado por la regla global
   `*.json`, asi que la buena practica existia y era invisible.
3. **Muestreo determinista** a un tamano fijo, para que entrenar tome segundos
   en clase.
4. **El casteo de zonas a string ocurre en `features/contract.py`**, no aqui.
   Castear el parquet crudo era la causa del `KeyError` original.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pandas as pd
import requests

from taxi.config import (
    DURACION_MAX_MIN,
    DURACION_MIN_MIN,
    FILAS_POR_PARTICION,
    PROCESSED_DIR,
    RAW_DIR,
    SEMILLA,
    UMBRAL_VIAJE_LARGO_MIN,
    Particion,
)
from taxi.data import contract as dc
from taxi.features import contract as fc

logger = logging.getLogger(__name__)

METADATA_PATH = RAW_DIR / "metadata.json"
_CHUNK = 1 << 20  # 1 MiB


def _sha256(path: Path) -> str:
    """SHA-256 del archivo, leido por bloques para no cargarlo en memoria."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _leer_metadata() -> dict[str, dict]:
    if not METADATA_PATH.exists():
        return {}
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("metadata.json corrupto; se regenera")
        return {}


def _escribir_metadata(meta: dict[str, dict]) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def descargar_particion(particion: Particion, *, forzar: bool = False) -> Path:
    """Descarga una particion mensual y registra su hash.

    Si el archivo ya existe y su hash coincide con el registrado, no se vuelve a
    descargar. Si existe pero el hash NO coincide, se avisa fuerte: significa
    que el proveedor republico el archivo, y eso invalida cualquier metrica
    reportada contra la version anterior.

    Args:
        particion: el mes a descargar.
        forzar: re-descarga aunque el archivo exista.

    Returns:
        Ruta local del parquet.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = RAW_DIR / particion.nombre_archivo
    meta = _leer_metadata()
    registrado = meta.get(particion.nombre_archivo, {})

    if destino.exists() and not forzar:
        actual = _sha256(destino)
        esperado = registrado.get("sha256")
        if esperado and actual != esperado:
            logger.warning(
                "HASH DISTINTO para %s.\n"
                "  registrado: %s\n  actual:     %s\n"
                "El proveedor republico el archivo. Las metricas calculadas con "
                "la version anterior ya no son comparables.",
                particion.nombre_archivo,
                esperado,
                actual,
            )
        else:
            logger.info("%s ya esta descargado (hash verificado)", particion)
            return destino

    logger.info("Descargando %s ...", particion.url)
    respuesta = requests.get(particion.url, stream=True, timeout=120)
    respuesta.raise_for_status()
    tmp = destino.with_suffix(".parquet.part")
    with tmp.open("wb") as fh:
        for chunk in respuesta.iter_content(chunk_size=_CHUNK):
            fh.write(chunk)
    tmp.replace(destino)

    meta[particion.nombre_archivo] = {
        "url": particion.url,
        "sha256": _sha256(destino),
        "bytes": destino.stat().st_size,
        "particion": particion.etiqueta,
        "fuente": "NYC Taxi and Limousine Commission (TLC) Trip Record Data",
        "licencia": "Datos publicos de la NYC TLC — uso libre con atribucion",
    }
    _escribir_metadata(meta)
    logger.info("Guardado en %s", destino)
    return destino


def preparar_particion(
    particion: Particion,
    *,
    filas: int | None = FILAS_POR_PARTICION,
    validar: bool = True,
) -> pd.DataFrame:
    """Descarga, valida, filtra, muestrea y deriva features de una particion.

    El orden importa y es deliberado:

    1. leer el crudo
    2. **validar el contrato del crudo** (falla temprano)
    3. calcular el target y filtrar viajes imposibles
    4. muestrear (determinista)
    5. derivar features
    6. **validar el contrato del procesado**

    Args:
        particion: mes a preparar.
        filas: tamano de la muestra. ``None`` para usar la particion completa.
        validar: desactivarlo solo tiene sentido para demostrar en clase que
            pasa sin contrato.

    Returns:
        DataFrame listo para entrenar.
    """
    ruta = descargar_particion(particion)
    df = pd.read_parquet(ruta, columns=None)

    if validar:
        df = dc.validar_crudos(df)

    df = df.copy()
    delta = df[fc.COL_DROPOFF] - df[fc.COL_PICKUP]
    df[fc.TARGET_REGRESION] = delta.dt.total_seconds() / 60.0

    # Limpieza explicita y contabilizada. El contrato del crudo acepta outliers
    # individuales a proposito (ver ViajesCrudos): rechazar la particion entera
    # por 34 filas corruptas de 68.211 seria un contrato que el equipo desactiva.
    # Aqui se filtran, y se registra CUANTAS se descartaron. Un filtro silencioso
    # es tan peligroso como no tener filtro: si manana se descarta el 40% de los
    # datos, alguien tiene que enterarse.
    antes = len(df)
    en_rango_duracion = df[fc.TARGET_REGRESION].between(DURACION_MIN_MIN, DURACION_MAX_MIN)
    en_rango_distancia = df[fc.CRUDAS_NUMERICAS[0]].le(dc.MAX_MILLAS_PLAUSIBLE)
    df = df[en_rango_duracion & en_rango_distancia].reset_index(drop=True)

    descartadas = antes - len(df)
    logger.info(
        "%s: %d filas -> %d (descartadas %d, %.3f%%): duracion fuera de [%.0f, %.0f] min o "
        "distancia > %.0f millas",
        particion,
        antes,
        len(df),
        descartadas,
        100.0 * descartadas / antes if antes else 0.0,
        DURACION_MIN_MIN,
        DURACION_MAX_MIN,
        dc.MAX_MILLAS_PLAUSIBLE,
    )
    if antes and descartadas / antes > 0.35:
        logger.warning(
            "%s: se descarto el %.1f%% de las filas. Eso ya no es limpieza, es un "
            "sintoma. Revisa la particion antes de entrenar con ella.",
            particion,
            100.0 * descartadas / antes,
        )

    if filas is not None and len(df) > filas:
        df = df.sample(n=filas, random_state=SEMILLA).reset_index(drop=True)

    df[fc.TARGET_CLASIFICACION] = (df[fc.TARGET_REGRESION] > UMBRAL_VIAJE_LARGO_MIN).astype("int8")

    df = fc.construir_features(df)

    columnas = [
        *fc.FEATURES,
        fc.TARGET_REGRESION,
        fc.TARGET_CLASIFICACION,
        fc.COL_PICKUP,
    ]
    df = df[columnas]

    if validar:
        df = dc.validar_procesados(df)
    return df


def preparar_particiones(
    particiones: tuple[Particion, ...] | list[Particion],
    **kwargs: object,
) -> pd.DataFrame:
    """Concatena varias particiones preparadas, en orden temporal."""
    marcos = [preparar_particion(p, **kwargs) for p in particiones]  # type: ignore[arg-type]
    return pd.concat(marcos, ignore_index=True).sort_values(fc.COL_PICKUP).reset_index(drop=True)


def cachear(df: pd.DataFrame, nombre: str) -> Path:
    """Guarda un dataframe procesado en ``data/processed/``."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    destino = PROCESSED_DIR / f"{nombre}.parquet"
    df.to_parquet(destino, index=False)
    logger.info("Cacheado %d filas en %s", len(df), destino)
    return destino


def cargar_cache(nombre: str) -> pd.DataFrame | None:
    """Lee un dataframe procesado del cache, o ``None`` si no existe."""
    ruta = PROCESSED_DIR / f"{nombre}.parquet"
    return pd.read_parquet(ruta) if ruta.exists() else None
