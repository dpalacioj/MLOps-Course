"""Tests de los flows de Prefect (Sesion 4).

Regla de diseno de estos tests: **no requieren servidor de Prefect, ni MLflow, ni
red.** Un flow es codigo Python; si para testear un paso hace falta levantar
infraestructura, el paso esta haciendo demasiado.

Prefect facilita esto: `mi_task.fn` es la funcion original sin decorar, asi que
se puede llamar directo y afirmar sobre su resultado. Lo que necesita
infraestructura esta marcado con `@pytest.mark.integration` y se salta solo si el
servicio no responde, para que `pytest` siga siendo verde en una maquina limpia.
"""

from __future__ import annotations

import ast
import socket
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import pytest
from prefect import Flow

from taxi.config import MLFLOW_TRACKING_URI, Particion
from taxi.features import contract as fc
from taxi.flows import batch, training

# =============================================================================
# Fixtures
# =============================================================================
FILAS_SINTETICAS = 1_200


def _viajes_crudos(n: int = FILAS_SINTETICAS, *, semilla: int = 7) -> pd.DataFrame:
    """DataFrame que cumple el contrato de crudos, sin tocar la red.

    Se generan datos coherentes con `ViajesCrudos`: zonas en [1, 265], distancias
    en millas dentro de rango, dropoff posterior al pickup y volumen por encima
    del minimo del contrato.
    """
    rng = np.random.default_rng(semilla)
    pickup = pd.Timestamp("2023-01-01") + pd.to_timedelta(rng.integers(0, 30 * 24 * 60, n), "m")
    duracion = rng.integers(2, 45, n)
    return pd.DataFrame(
        {
            fc.COL_PICKUP: pickup,
            fc.COL_DROPOFF: pickup + pd.to_timedelta(duracion, "m"),
            "PULocationID": rng.integers(1, 266, n),
            "DOLocationID": rng.integers(1, 266, n),
            "trip_distance": rng.uniform(0.2, 25.0, n).round(2),
        }
    )


@pytest.fixture
def parquet_crudo(tmp_path: Path) -> Path:
    ruta = tmp_path / "green_tripdata_2023-01.parquet"
    _viajes_crudos().to_parquet(ruta, index=False)
    return ruta


@pytest.fixture
def features_produccion() -> pd.DataFrame:
    """DataFrame con las features derivadas, como lo recibe el batch."""
    df = _viajes_crudos(n=50, semilla=11)
    df = fc.construir_features(df)
    return df.reset_index(drop=True)


def _procesado(n: int = 300, *, semilla: int = 3) -> pd.DataFrame:
    """DataFrame procesado (features + target), como lo produce `preparar`."""
    df = fc.construir_features(_viajes_crudos(n=n, semilla=semilla))
    delta = df[fc.COL_DROPOFF] - df[fc.COL_PICKUP]
    df[fc.TARGET_REGRESION] = delta.dt.total_seconds() / 60.0
    return df.reset_index(drop=True)


def _arbol(modulo: Any) -> ast.Module:
    return ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))


def _nombres_del_codigo(modulo: Any) -> set[str]:
    """Identificadores y atributos que el modulo realmente usa.

    Inspeccionar el AST y no el texto evita falsos positivos: estos modulos
    nombran las APIs prohibidas en sus docstrings para explicar por que lo estan.
    """
    nombres: set[str] = set()
    for nodo in ast.walk(_arbol(modulo)):
        if isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr)
        elif isinstance(nodo, ast.Name):
            nombres.add(nodo.id)
        elif isinstance(nodo, ast.alias):
            nombres.add(nodo.name.split(".")[-1])
    return nombres


def _kwargs_del_codigo(modulo: Any) -> set[str]:
    """Nombres de los argumentos por palabra clave usados en las llamadas."""
    return {
        kw.arg
        for nodo in ast.walk(_arbol(modulo))
        if isinstance(nodo, ast.Call)
        for kw in nodo.keywords
        if kw.arg is not None
    }


def _puerto_abierto(url: str, timeout: float = 0.4) -> bool:
    partes = urlparse(url)
    if not partes.hostname:
        return False
    try:
        with socket.create_connection((partes.hostname, partes.port or 80), timeout=timeout):
            return True
    except OSError:
        return False


# =============================================================================
# Helpers puros: calculo de la particion siguiente
# =============================================================================
class TestParticiones:
    """El salto de diciembre a enero: donde esta funcion se rompe siempre."""

    def test_mes_intermedio(self) -> None:
        assert training.siguiente_particion(Particion(2023, 3)) == Particion(2023, 4)

    def test_salto_de_ano(self) -> None:
        # Diciembre -> enero del ano siguiente. Es el unico caso donde este
        # calculo se rompe, y por eso es el que hay que fijar con un test.
        assert training.siguiente_particion(Particion(2023, 12)) == Particion(2024, 1)

    def test_noviembre_no_salta_de_ano(self) -> None:
        assert training.siguiente_particion(Particion(2023, 11)) == Particion(2023, 12)

    def test_valid_por_defecto_es_el_mes_siguiente_al_ultimo_train(self) -> None:
        from taxi.config import PARTICION_VALID, PARTICIONES_TRAIN

        assert training.siguiente_particion(PARTICIONES_TRAIN[-1]) == PARTICION_VALID

    @pytest.mark.parametrize(
        ("etiqueta", "esperado"),
        [
            ("2023-01", Particion(2023, 1)),
            ("2024-12", Particion(2024, 12)),
            (" 2023-07 ", Particion(2023, 7)),
        ],
    )
    def test_etiqueta_valida(self, etiqueta: str, esperado: Particion) -> None:
        assert training.particion_desde_etiqueta(etiqueta) == esperado

    @pytest.mark.parametrize("etiqueta", ["2023", "2023-13", "2023-00", "enero", "2023/01", ""])
    def test_etiqueta_invalida_falla_temprano(self, etiqueta: str) -> None:
        with pytest.raises(ValueError):
            training.particion_desde_etiqueta(etiqueta)

    def test_nombre_cache_es_estable_y_legible(self) -> None:
        nombre = training.nombre_cache((Particion(2023, 1), Particion(2023, 2)))
        assert nombre == "train-2023-01_2023-02"


# =============================================================================
# Tasks invocables con .fn()
# =============================================================================
class TestTasksDeEntrenamiento:
    def test_validar_acepta_datos_que_cumplen_el_contrato(self, parquet_crudo: Path) -> None:
        resumen = training.validar.fn(parquet_crudo)
        assert resumen["filas"] == FILAS_SINTETICAS
        assert resumen["archivo"] == parquet_crudo.name

    def test_validar_rechaza_dropoff_anterior_al_pickup(self, tmp_path: Path) -> None:
        df = _viajes_crudos()
        # Un viaje que termina antes de empezar. El contrato debe convertir este
        # dato imposible en un fallo ruidoso.
        df.loc[0, fc.COL_DROPOFF] = df.loc[0, fc.COL_PICKUP] - timedelta(minutes=5)
        ruta = tmp_path / "roto.parquet"
        df.to_parquet(ruta, index=False)

        import pandera.errors as pae

        with pytest.raises((pae.SchemaError, pae.SchemaErrors)):
            training.validar.fn(ruta)

    def test_validar_rechaza_descarga_truncada(self, tmp_path: Path) -> None:
        ruta = tmp_path / "truncado.parquet"
        _viajes_crudos(n=10).to_parquet(ruta, index=False)

        import pandera.errors as pae

        with pytest.raises((pae.SchemaError, pae.SchemaErrors)):
            training.validar.fn(ruta)

    def test_configuracion_de_mlflow_no_ocurre_al_importar(self) -> None:
        # El modulo anterior llamaba a setup_mlflow() a nivel de modulo. Si eso
        # volviera a pasar, importar el flow tendria efectos colaterales.
        import mlflow

        assert mlflow.active_run() is None
        assert callable(training._configurar_mlflow)

    def test_url_ui_devuelve_none_si_el_backend_no_es_http(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import mlflow

        monkeypatch.setattr(mlflow, "get_tracking_uri", lambda: "sqlite:///mlflow.db")
        # El bug anterior producia "http://localhost:5000/mlflow.db".
        assert training._url_ui_mlflow() is None

    def test_url_ui_devuelve_la_uri_si_es_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import mlflow

        monkeypatch.setattr(mlflow, "get_tracking_uri", lambda: "http://127.0.0.1:5001")
        assert training._url_ui_mlflow() == "http://127.0.0.1:5001"

    def test_metricas_usan_root_mean_squared_error(self) -> None:
        y = pd.Series([10.0, 20.0, 30.0])
        metricas = training.calcular_metricas(y, np.array([12.0, 18.0, 33.0]))
        assert metricas["rmse"] == pytest.approx(2.3805, abs=1e-3)
        assert metricas["mae"] == pytest.approx(2.3333, abs=1e-3)
        assert set(metricas) == {"rmse", "mae", "r2"}

    def test_estimador_predice_desde_un_dataframe(self) -> None:
        # El contrato de entrada del modelo es un DataFrame: es lo que envian la
        # API (S05) y el batch. Si el estimador esperara listas de diccionarios
        # habria skew entre entrenamiento y serving.
        df_train = _procesado(n=400, semilla=3)
        df_valid = _procesado(n=120, semilla=4)
        estimador = training._construir_estimador({"n_estimators": 5, "max_depth": 2})

        # `_ajustar` delega en taxi.models.train.ajustar, que construye el
        # eval_set del early stopping con `transform` (nunca `fit_transform`).
        training._ajustar(estimador, df_train, df_valid)

        predicciones = estimador.predict(df_valid[fc.FEATURES].head(3))
        assert len(predicciones) == 3

    def test_task_extraer_tiene_backoff_creciente(self) -> None:
        # El backoff es parte del contrato de la task, no un detalle: reintentar
        # de inmediato contra un servicio saturado equivale a no reintentar.
        assert training.extraer.retries == 3
        assert training.extraer.retry_delay_seconds == [10, 30, 60]

    def test_task_preparar_cachea_por_inputs(self) -> None:
        from prefect.tasks import task_input_hash

        assert training.preparar.cache_key_fn is task_input_hash
        assert training.preparar.cache_expiration == timedelta(hours=24)
        # Sin persistencia el cache no sobrevive entre corridas y la mejora de
        # tiempo que el taller pide medir no existiria.
        assert training.preparar.persist_result is True


# =============================================================================
# Batch: la fila persistida es el contrato con quien consulte en SQL
# =============================================================================
class TestFilaPersistida:
    def _filas(self, df: pd.DataFrame) -> pd.DataFrame:
        return batch.construir_filas(
            df,
            np.arange(len(df), dtype=float) + 8.0,
            batch_id="2023-07-abcd1234",
            particion="2023-07",
            model_name="nyc-taxi-duration",
            model_version="7",
            model_alias="champion",
            model_uri="models:/nyc-taxi-duration@champion",
            momento=datetime(2026, 8, 19, 12, 0, tzinfo=UTC),
        )

    def test_columnas_exactas_y_en_orden(self, features_produccion: pd.DataFrame) -> None:
        filas = self._filas(features_produccion)
        assert tuple(filas.columns) == batch.COLUMNAS_FILA

    def test_trazabilidad_de_la_version(self, features_produccion: pd.DataFrame) -> None:
        filas = self._filas(features_produccion)
        assert (filas["model_version"] == "7").all()
        assert (filas["model_alias"] == "champion").all()
        assert (filas["model_uri"] == "models:/nyc-taxi-duration@champion").all()
        assert filas["prediction_timestamp"].iloc[0] == "2026-08-19T12:00:00+00:00"
        assert filas["batch_id"].nunique() == 1

    def test_no_persiste_un_stage_hardcodeado(self, features_produccion: pd.DataFrame) -> None:
        # Un {'stage': 'Production'} literal miente en cuanto el modelo cambia.
        filas = self._filas(features_produccion)
        assert "stage" not in filas.columns
        assert "model_stage" not in filas.columns

    def test_una_fila_por_prediccion(self, features_produccion: pd.DataFrame) -> None:
        filas = self._filas(features_produccion)
        assert len(filas) == len(features_produccion)
        assert filas["prediccion_minutos"].iloc[0] == pytest.approx(8.0)

    def test_desalineamiento_falla_en_lugar_de_persistir_basura(
        self, features_produccion: pd.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="Desalineamiento"):
            batch.construir_filas(
                features_produccion,
                np.zeros(len(features_produccion) - 1),
                batch_id="b",
                particion="2023-07",
                model_name="m",
                model_version="1",
                model_alias="champion",
                model_uri="models:/m@champion",
            )

    def test_el_ddl_declara_las_mismas_columnas_que_la_fila(self) -> None:
        declaradas = {
            linea.strip().split()[0]
            for linea in batch._DDL.splitlines()
            if linea.startswith("    ") and linea.strip()
        }
        assert set(batch.COLUMNAS_FILA) <= declaradas

    def test_escribir_en_sqlite_y_consultar_por_version(
        self, features_produccion: pd.DataFrame, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        destino = tmp_path / "predicciones.db"
        monkeypatch.setenv("PREDICCIONES_DB", str(destino))
        monkeypatch.delenv("DATABASE_URL", raising=False)

        filas = self._filas(features_produccion)
        escritas = batch.escribir(filas)
        assert escritas == len(filas)

        with sqlite3.connect(destino) as conexion:
            total, versiones = conexion.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT model_version) FROM {batch.TABLA}"
            ).fetchone()
        assert total == len(filas)
        assert versiones == 1

    def test_destino_prefiere_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/db")
        assert batch.destino().startswith("postgresql")
        monkeypatch.delenv("DATABASE_URL")
        assert batch.destino().startswith("sqlite:///")


# =============================================================================
# Flows: forma, no ejecucion
# =============================================================================
class TestFormaDeLosFlows:
    def test_son_flows_de_prefect(self) -> None:
        assert isinstance(training.entrenamiento_flow, Flow)
        assert isinstance(batch.batch_flow, Flow)

    def test_los_parametros_del_flow_son_serializables_a_json(self) -> None:
        # Un deployment serializa sus parametros: si el flow pidiera un
        # dataclass o un DataFrame, no se podria lanzar desde la UI.
        import inspect

        firma = inspect.signature(training.entrenamiento_flow.fn)
        anotaciones = {p.annotation for p in firma.parameters.values()}
        assert anotaciones == {
            "list[str] | None",
            "str | None",
            "dict[str, Any] | None",
            "str",
            "bool",
        }

    def test_el_flow_de_entrenamiento_no_promueve(self) -> None:
        # Garantia estructural de la decision de diseno. Se inspecciona el AST y
        # no el texto del archivo: los comentarios y docstrings hablan de las
        # APIs prohibidas justamente para explicar por que estan prohibidas.
        nombres = _nombres_del_codigo(training)
        # El nombre del metodo deprecado no se escribe literal: el propio hook
        # del repo (scripts/hooks/mlflow_sin_stages.py) bloquea esa cadena en
        # los .py, y con razon. Se busca por prefijo.
        assert not any(n.startswith("transition_model_version") for n in nombres)
        assert "ALIAS_PRODUCCION" not in nombres, (
            "El flow de entrenamiento no debe conocer el alias de produccion."
        )
        assert "set_registered_model_alias" in nombres
        assert "ALIAS_CANDIDATO" in nombres

    def test_los_schedules_son_realistas(self) -> None:
        from taxi.flows import deploy

        # Mensual, no cada dos minutos. Ver la justificacion en deploy.py.
        assert deploy.CRON_ENTRENAMIENTO.split() == ["0", "3", "5", "*", "*"]
        assert deploy._schedule(deploy.CRON_ENTRENAMIENTO).timezone == "America/Bogota"

    def test_deploy_usa_schedules_plural_y_work_pool(self) -> None:
        from taxi.flows import deploy

        kwargs = _kwargs_del_codigo(deploy)
        # `schedules=` plural. El kwarg `schedule=` singular es la forma de
        # Prefect 2 y no se usa en ningun punto del curso.
        assert "schedules" in kwargs
        assert "schedule" not in kwargs
        # `deploy()` sin work_pool_name no puede ejecutar nada en Prefect 3.
        assert "work_pool_name" in kwargs
        nombres = _nombres_del_codigo(deploy)
        assert "build_from_flow" not in nombres


# =============================================================================
# Integracion — requiere servicios arriba. Se salta si no responden.
# =============================================================================
@pytest.mark.integration
class TestIntegracion:
    def _exigir_mlflow(self) -> None:
        if not _puerto_abierto(MLFLOW_TRACKING_URI):
            pytest.skip(f"MLflow no responde en {MLFLOW_TRACKING_URI}")

    @pytest.mark.slow
    def test_entrenamiento_end_to_end_registra_candidato_sin_promover(self) -> None:
        """Corre el flow completo. Requiere MLflow arriba y red hacia la TLC."""
        self._exigir_mlflow()
        from mlflow import MlflowClient

        from taxi.config import ALIAS_CANDIDATO, ALIAS_PRODUCCION, MODELO_REGRESION

        resultado = training.entrenamiento_flow()
        assert resultado["model_version"] is not None
        assert resultado["promovido"] is False

        cliente = MlflowClient()
        candidato = cliente.get_model_version_by_alias(MODELO_REGRESION, ALIAS_CANDIDATO)
        assert str(candidato.version) == resultado["model_version"]
        try:
            champion = cliente.get_model_version_by_alias(MODELO_REGRESION, ALIAS_PRODUCCION)
        except Exception:
            return  # no hay champion todavia: correcto, el flow no lo crea
        assert str(champion.version) != resultado["model_version"], (
            "El flow promovio el candidato a champion. Eso es trabajo del gate (S06)."
        )

    @pytest.mark.slow
    def test_batch_persiste_predicciones(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Requiere MLflow arriba con un modelo en `@champion`."""
        self._exigir_mlflow()
        monkeypatch.setenv("PREDICCIONES_DB", str(tmp_path / "pred.db"))

        resultado: dict[str, Any] = batch.batch_flow()
        assert resultado["filas_escritas"] > 0
        assert resultado["model_version"]
