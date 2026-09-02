"""Fixtures compartidas de la suite.

Por que los datos de prueba se GENERAN en codigo y no se leen de un CSV
commiteado: un CSV de mil filas en el repositorio es opaco (nadie sabe que
propiedad tiene), se desactualiza cuando el contrato cambia y no explica por que
cada fixture roto esta roto. Generarlo con una semilla fija da lo mismo que un
archivo —reproducibilidad bit a bit— y ademas documenta la intencion.

Los tres fixtures rotos no son ruido aleatorio: cada uno reproduce un fallo que
NO lanza excepciones, que es la unica clase de fallo de datos que hace falta
testear.

1. `df_crudo_en_kilometros` — datos en km alimentando un modelo entrenado en
   millas. El pipeline entrena sin quejarse.
2. `df_crudo_zona_invalida` — una zona fuera del rango 1-265 de la TLC. Aparece
   cuando alguien inventa datos de prueba sin leer el diccionario de datos.
3. `df_crudo_con_nulos` — nulos en una columna obligatoria. Es lo que llega
   cuando una descarga se corta a medias.

Ninguno de los tres lanza una excepcion por si mismo: los tres entrenan un
modelo y producen un RMSE plausible. Ese es exactamente el punto del contrato.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from taxi.features import contract as fc

#: Semilla de los datos de prueba. Distinta de config.SEMILLA a proposito: si
#: fueran la misma, un test podria pasar por coincidencia entre el muestreo del
#: pipeline y la generacion del fixture.
SEMILLA_FIXTURES = 20_260_819

#: Factor de conversion millas -> kilometros, para el fixture de unidades.
MILLAS_A_KM = 1.609_34

#: Grupos del generador: (nombre, proporcion, dist_min, dist_max, min_por_milla,
#: espera_min, espera_max). Las velocidades implicitas son distintas por grupo
#: para que ningun viaje quede fuera del rango valido de duracion y para que
#: cada subgrupo del modulo evaluate tenga suficientes filas.
_GRUPOS: tuple[tuple[str, float, float, float, float, float, float], ...] = (
    ("corta", 0.15, 0.2, 0.99, 8.0, 1.0, 4.0),
    ("media", 0.33, 1.0, 2.99, 6.0, 1.0, 5.0),
    ("larga", 0.35, 3.0, 9.99, 3.5, 2.0, 8.0),
    ("muy_larga", 0.16, 10.0, 25.0, 1.6, 3.0, 10.0),
    # Cola de viajes largos legitimos (aeropuerto, afueras). El contrato los
    # acepta porque el limite es 100 millas. Son los que hacen detectable el
    # cambio de unidades: en km se salen del rango.
    ("cola_larga", 0.01, 70.0, 95.0, 0.55, 2.0, 6.0),
)


def generar_crudos(filas: int = 1_200, semilla: int = SEMILLA_FIXTURES) -> pd.DataFrame:
    """Genera un parquet crudo sintetico que cumple el contrato ViajesCrudos.

    Propiedades garantizadas, porque hay tests que dependen de ellas:

    - al menos 1000 filas (el check ``volumen_minimo`` del contrato),
    - todas las duraciones dentro de [1, 60] minutos,
    - las dos clases de ``viaje_largo`` presentes (``target_no_constante``),
    - al menos 50 filas en cada franja horaria y en cada rango de distancia,
      para que las metricas por subgrupo se calculen,
    - una cola de viajes de 70-95 millas, validos en millas y fuera de rango en
      kilometros.
    """
    generador = np.random.default_rng(semilla)

    distancias: list[np.ndarray] = []
    duraciones: list[np.ndarray] = []
    for _, proporcion, d_min, d_max, min_por_milla, esp_min, esp_max in _GRUPOS:
        n = max(round(filas * proporcion), 12)
        dist = generador.uniform(d_min, d_max, n)
        dur = dist * min_por_milla + generador.uniform(esp_min, esp_max, n)
        distancias.append(dist)
        duraciones.append(dur)

    distancia = np.concatenate(distancias)
    duracion = np.concatenate(duraciones)
    total = len(distancia)

    # Horas repartidas de forma ciclica y no aleatoria: garantiza que las cuatro
    # franjas horarias tengan filas suficientes sin depender de la suerte.
    horas = np.arange(total) % 24
    dias = (np.arange(total) // 24) % 28

    pickup = (
        pd.Timestamp("2023-05-01")
        + pd.to_timedelta(dias, unit="D")
        + pd.to_timedelta(horas, unit="h")
        + pd.to_timedelta(generador.integers(0, 60, total), unit="m")
    )

    df = pd.DataFrame(
        {
            fc.COL_PICKUP: pickup,
            fc.COL_DROPOFF: pickup + pd.to_timedelta(duracion, unit="m"),
            "PULocationID": generador.integers(1, 266, total),
            "DOLocationID": generador.integers(1, 266, total),
            "trip_distance": distancia,
            # Columnas extra del parquet real: el contrato usa strict=False, y
            # este fixture verifica que de verdad las tolera.
            "passenger_count": generador.integers(1, 5, total).astype("float64"),
            "total_amount": np.round(3.0 + distancia * 2.75, 2),
        }
    )
    return df.sample(frac=1.0, random_state=semilla).reset_index(drop=True)


@pytest.fixture
def df_crudo_valido() -> pd.DataFrame:
    """Parquet crudo sintetico que el contrato debe aceptar."""
    return generar_crudos()


@pytest.fixture
def df_crudo_en_kilometros(df_crudo_valido: pd.DataFrame) -> pd.DataFrame:
    """FIXTURE ROTO (a): trip_distance en kilometros en lugar de millas.

    El fallo silencioso canonico. Ningun tipo cambia, ningun nulo aparece, nada
    lanza. El modelo entrena y reporta un RMSE creible sobre features que
    significan otra cosa. Solo el rango lo delata.
    """
    df = df_crudo_valido.copy()
    df["trip_distance"] = df["trip_distance"] * MILLAS_A_KM
    return df


@pytest.fixture
def df_crudo_zona_invalida(df_crudo_valido: pd.DataFrame) -> pd.DataFrame:
    """FIXTURE ROTO (b): una zona fuera del rango 1-265 de la TLC."""
    df = df_crudo_valido.copy()
    df.loc[df.index[:3], "DOLocationID"] = 999
    return df


@pytest.fixture
def df_crudo_con_nulos(df_crudo_valido: pd.DataFrame) -> pd.DataFrame:
    """FIXTURE ROTO (c): nulos en una columna obligatoria.

    Es el sintoma de una descarga cortada o de un join que no encontro pareja.
    ``trip_distance`` es float, asi que el nulo se representa sin cambiar el
    dtype: el fallo es unicamente el nulo, no una coercion de tipo.
    """
    df = df_crudo_valido.copy()
    df.loc[df.index[:5], "trip_distance"] = np.nan
    return df


@pytest.fixture
def df_crudo_con_duraciones_extremas(df_crudo_valido: pd.DataFrame) -> pd.DataFrame:
    """Crudo valido mas viajes de 0.5 y 90 minutos.

    El contrato del crudo los ACEPTA (solo exige que el dropoff sea posterior al
    pickup); es el filtro de negocio del loader el que debe eliminarlos. Separar
    las dos responsabilidades es intencional: el contrato dice que es un dato
    bien formado, el filtro dice que es un viaje.
    """
    df = df_crudo_valido.copy()
    extremos = df.head(4).copy()
    minutos = [0.5, 0.9, 75.0, 90.0]
    extremos[fc.COL_DROPOFF] = extremos[fc.COL_PICKUP] + pd.to_timedelta(minutos, unit="m")
    extremos["trip_distance"] = [0.1, 0.2, 30.0, 35.0]
    return pd.concat([df, extremos], ignore_index=True)


@pytest.fixture
def parquet_crudo(tmp_path: Path, df_crudo_valido: pd.DataFrame) -> Path:
    """Escribe el crudo valido como parquet en un directorio temporal.

    Permite ejercitar ``preparar_particion`` completo —contratos, filtro,
    muestreo, features— sin tocar la red: se parchea solo la descarga.
    """
    destino = tmp_path / "green_tripdata_2023-05.parquet"
    df_crudo_valido.to_parquet(destino, index=False)
    return destino


@pytest.fixture
def df_procesado_valido(df_crudo_valido: pd.DataFrame) -> pd.DataFrame:
    """Dataframe con features derivadas y ambos targets, listo para el modelo.

    Replica el orden de ``loaders.preparar_particion`` sin descargar nada.
    """
    from taxi.config import DURACION_MAX_MIN, DURACION_MIN_MIN, UMBRAL_VIAJE_LARGO_MIN

    df = df_crudo_valido.copy()
    delta = df[fc.COL_DROPOFF] - df[fc.COL_PICKUP]
    df[fc.TARGET_REGRESION] = delta.dt.total_seconds() / 60.0
    df = df[df[fc.TARGET_REGRESION].between(DURACION_MIN_MIN, DURACION_MAX_MIN)].reset_index(
        drop=True
    )
    df[fc.TARGET_CLASIFICACION] = (df[fc.TARGET_REGRESION] > UMBRAL_VIAJE_LARGO_MIN).astype("int8")
    df = fc.construir_features(df)
    return df[[*fc.FEATURES, fc.TARGET_REGRESION, fc.TARGET_CLASIFICACION, fc.COL_PICKUP]]


# =============================================================================
# Fixtures del gate
# =============================================================================
@pytest.fixture
def subgrupos_base() -> dict[str, float]:
    """Metricas por subgrupo de un champion ficticio."""
    return {
        "rmse_hora_madrugada": 4.0,
        "rmse_hora_manana": 5.0,
        "rmse_hora_tarde": 5.5,
        "rmse_hora_noche": 4.5,
        "rmse_dist_corta": 2.0,
        "rmse_dist_media": 3.0,
        "rmse_dist_larga": 6.0,
        "rmse_dist_muy_larga": 9.0,
        "n_hora_madrugada": 300.0,
        "n_dist_corta": 180.0,
    }
