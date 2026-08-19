"""Descarga, verificacion por hash y preparacion de datos.

Cuatro decisiones que conviene copiar tal cual:

1. **Particiones fijas** (``config.py``), nunca ``datetime.now()``. Un pipeline
   que pide "el mes actual" deja de funcionar el dia que el proveedor se retrasa,
   y el fallo aparece en clase o en la demo, no en desarrollo.
2. **Verificacion por hash**. Se registra el SHA-256 de cada archivo en
   ``data/raw/metadata.json``. Si el proveedor republica un archivo, la metrica
   que reportaste contra la version anterior deja de ser comparable, y quieres
   enterarte por un aviso y no por un resultado raro tres semanas despues.
3. **Muestreo determinista** a un tamano fijo, para que entrenar tome segundos.
4. El casteo de categoricas a string ocurre en ``features/contract.py``, no aqui.
   Castear el dataframe crudo completo convierte tambien las numericas.

TODO(estudiante) 11: implementa ``leer_particion`` para tu fuente real. El resto
del modulo deberia funcionar sin cambios si tu fuente entrega un archivo por
particion.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pandas as pd

from miproyecto.config import (
    FILAS_POR_PARTICION,
    PROCESSED_DIR,
    RAW_DIR,
    SEMILLA,
    Particion,
)
from miproyecto.data import contract as dc
from miproyecto.features import contract as fc

logger = logging.getLogger(__name__)

METADATA_PATH = RAW_DIR / "metadata.json"
_CHUNK = 1 << 20  # 1 MiB


def sha256(path: Path) -> str:
    """SHA-256 del archivo, leido por bloques para no cargarlo en memoria."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def leer_metadata() -> dict[str, dict]:
    """Lee ``data/raw/metadata.json``, o ``{}`` si no existe o esta corrupto."""
    if not METADATA_PATH.exists():
        return {}
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("metadata.json corrupto; se regenera")
        return {}


def escribir_metadata(meta: dict[str, dict]) -> None:
    """Escribe el metadata ordenado, para que el diff en git sea legible.

    Ojo con el .gitignore: este archivo SI va al repositorio. Es la procedencia
    de tus datos. Una regla `*.json` global lo excluye en silencio y te deja sin
    evidencia de con que datos entrenaste; el .gitignore de este template tiene
    la excepcion explicita.
    """
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def descargar_particion(particion: Particion, *, forzar: bool = False) -> Path:
    """Descarga una particion y registra su hash, url, tamano y licencia.

    Si el archivo ya existe y su hash coincide con el registrado, no se vuelve a
    descargar. Si existe pero el hash NO coincide, se avisa fuerte.

    Args:
        particion: la particion a descargar.
        forzar: re-descarga aunque el archivo exista.

    Returns:
        Ruta local del archivo descargado.
    """
    import requests  # import local: el resto del modulo no necesita red

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = RAW_DIR / particion.nombre_archivo
    meta = leer_metadata()
    registrado = meta.get(particion.nombre_archivo, {})

    if destino.exists() and not forzar:
        actual = sha256(destino)
        esperado = registrado.get("sha256")
        if esperado and actual != esperado:
            logger.warning(
                "HASH DISTINTO para %s.\n  registrado: %s\n  actual:     %s\n"
                "El proveedor republico el archivo: las metricas calculadas con "
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
    tmp = destino.with_suffix(destino.suffix + ".part")
    with tmp.open("wb") as fh:
        for chunk in respuesta.iter_content(chunk_size=_CHUNK):
            fh.write(chunk)
    tmp.replace(destino)

    meta[particion.nombre_archivo] = {
        "url": particion.url,
        "sha256": sha256(destino),
        "bytes": destino.stat().st_size,
        "particion": particion.etiqueta,
        # TODO(estudiante) 12: fuente y licencia REALES. No son formalidad:
        # sin ellas no puedes publicar la dataset card ni defender el uso.
        "fuente": "TODO: nombre del proveedor",
        "licencia": "TODO: licencia exacta y su URL",
    }
    escribir_metadata(meta)
    logger.info("Guardado en %s", destino)
    return destino


def leer_particion(particion: Particion) -> pd.DataFrame:
    """Lee una particion ya descargada a un DataFrame.

    TODO(estudiante) 11: adapta el formato. Parquet por defecto porque preserva
    tipos y es columnar; si tu fuente es CSV, pasa `dtype=` explicito y
    `parse_dates=` en lugar de dejar que pandas adivine.
    """
    ruta = descargar_particion(particion)
    if ruta.suffix == ".parquet":
        return pd.read_parquet(ruta)
    return pd.read_csv(ruta)


def preparar_particion(
    particion: Particion,
    *,
    filas: int | None = FILAS_POR_PARTICION,
    validar: bool = True,
) -> pd.DataFrame:
    """Descarga, valida, limpia, muestrea y deriva features de una particion.

    El orden importa y es deliberado:

    1. leer el crudo
    2. **validar el contrato del crudo** (falla temprano, con el proveedor)
    3. imputar/filtrar segun la estrategia declarada
    4. muestrear (determinista)
    5. derivar features
    6. **validar el contrato del procesado** (falla tarde, con tu pipeline)

    Args:
        particion: particion a preparar.
        filas: tamano de la muestra. ``None`` usa la particion completa.
        validar: desactivarlo solo tiene sentido para demostrar en clase que
            pasa sin contrato.
    """
    df = leer_particion(particion)
    if validar:
        df = dc.validar_crudos(df)
    df = limpiar(df)
    if filas is not None and len(df) > filas:
        df = df.sample(n=filas, random_state=SEMILLA).reset_index(drop=True)
    df = fc.construir_features(df)
    if validar:
        df = dc.validar_procesados(df)
    return df


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica la estrategia de imputacion y los filtros de negocio.

    TODO(estudiante) 13: `fillna(0)` NO es una estrategia por defecto; es una
    decision con consecuencias (sesga la media, inventa ceros que el modelo
    aprende como reales). Decide por columna, documenta el por que en
    docs/dataset-card.md, y si imputas, considera agregar una columna
    indicadora `<col>_era_nulo` para que el modelo pueda usar la ausencia como
    senal en lugar de confundirla con un cero real.

    Aqui hay una imputacion deliberadamente simple para que el template corra;
    no la copies sin pensarla.
    """
    out = df.copy()
    for col in fc.CRUDAS_NUMERICAS:
        if col in out.columns:
            out[f"{col}_era_nulo"] = out[col].isna().astype("int8")
            out[col] = out[col].astype("float64").fillna(out[col].median())
    for col in fc.CRUDAS_CATEGORICAS:
        if col in out.columns:
            out[col] = out[col].astype("string").fillna("desconocido").astype(str)
    return out.reset_index(drop=True)


def preparar_particiones(
    particiones: tuple[Particion, ...] | list[Particion],
    **kwargs: object,
) -> pd.DataFrame:
    """Concatena varias particiones preparadas, ordenadas por el eje temporal.

    El orden temporal no es cosmetico: es lo que hace que un split por posicion
    sea un split honesto.
    """
    marcos = [preparar_particion(p, **kwargs) for p in particiones]  # type: ignore[arg-type]
    return pd.concat(marcos, ignore_index=True).sort_values(fc.COL_TIEMPO).reset_index(drop=True)


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


def split_temporal(
    df: pd.DataFrame, *, fraccion_train: float = 0.8
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split por posicion sobre datos ya ordenados en el tiempo.

    ``train_test_split(shuffle=True)`` sobre datos con eje temporal es un bug,
    no una simplificacion: mezcla el futuro dentro del entrenamiento y produce
    una metrica optimista que no se sostiene en produccion. El sintoma clasico
    es "en validacion daba 0.95 y en produccion da 0.60".

    Raises:
        ValueError: si el dataframe no esta ordenado por el eje temporal.
    """
    if not df[fc.COL_TIEMPO].is_monotonic_increasing:
        raise ValueError(
            f"El dataframe debe venir ordenado por {fc.COL_TIEMPO} antes de "
            "hacer un split temporal."
        )
    corte = int(len(df) * fraccion_train)
    return df.iloc[:corte].copy(), df.iloc[corte:].copy()
