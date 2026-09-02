"""Tests de los helpers del Model Registry, con MlflowClient mockeado.

No se levanta MLflow. Lo que se verifica es el contrato de estas funciones con la
API de MLflow: que llamen al metodo correcto, en el orden correcto, y que traten
"todavia no hay champion" como un estado normal y no como un error.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from mlflow.exceptions import MlflowException

from taxi import config
from taxi.models import registry


def test_asignar_alias_usa_la_api_de_aliases() -> None:
    """La API vigente es set_registered_model_alias, no los stages deprecados."""
    cliente = MagicMock()
    registry.asignar_alias("modelo-x", "champion", 7, cliente_mlflow=cliente)
    cliente.set_registered_model_alias.assert_called_once_with(
        name="modelo-x", alias="champion", version="7"
    )
    # El mock aceptaria cualquier metodo: lo que se verifica es que el codigo NO
    # llame al de stages.
    cliente.transition_model_version_stage.assert_not_called()


def test_version_por_alias_devuelve_none_si_no_existe() -> None:
    """ "Todavia no hay champion" es el estado normal del primer dia.

    Si esta funcion propagara la excepcion, el gate no podria distinguir "primer
    modelo" de "MLflow caido" y trataria los dos igual.
    """
    cliente = MagicMock()
    cliente.get_model_version_by_alias.side_effect = MlflowException("no existe")
    assert registry.version_por_alias("modelo-x", "champion", cliente_mlflow=cliente) is None


def test_version_por_alias_devuelve_la_version() -> None:
    cliente = MagicMock()
    esperada = SimpleNamespace(version="4", run_id="abc")
    cliente.get_model_version_by_alias.return_value = esperada
    assert registry.version_por_alias("modelo-x", cliente_mlflow=cliente) is esperada
    cliente.get_model_version_by_alias.assert_called_once_with(
        name="modelo-x", alias=config.ALIAS_PRODUCCION
    )


def test_marcar_validacion_escribe_el_tag_del_config() -> None:
    cliente = MagicMock()
    registry.marcar_validacion("modelo-x", 3, "passed", cliente_mlflow=cliente)
    cliente.set_model_version_tag.assert_called_once_with(
        name="modelo-x", version="3", key=config.TAG_VALIDACION, value="passed"
    )


@pytest.mark.parametrize("estado", ["ok", "PASSED", "aprobado", ""])
def test_marcar_validacion_rechaza_estados_invalidos(estado: str) -> None:
    """El vocabulario del tag es cerrado: si no, cada pipeline inventa el suyo."""
    cliente = MagicMock()
    with pytest.raises(ValueError, match="estado invalido"):
        registry.marcar_validacion("modelo-x", 1, estado, cliente_mlflow=cliente)
    cliente.set_model_version_tag.assert_not_called()


def test_ultima_version_compara_como_numero_no_como_texto() -> None:
    """El bug clasico: ordenar versiones como strings pone la 9 despues de la 10."""
    cliente = MagicMock()
    cliente.search_model_versions.return_value = [
        SimpleNamespace(version="9", run_id="r9"),
        SimpleNamespace(version="10", run_id="r10"),
        SimpleNamespace(version="2", run_id="r2"),
    ]
    ultima = registry.ultima_version("modelo-x", cliente_mlflow=cliente)
    assert ultima is not None
    assert ultima.version == "10"


def test_ultima_version_devuelve_none_sin_versiones() -> None:
    cliente = MagicMock()
    cliente.search_model_versions.return_value = []
    assert registry.ultima_version("modelo-x", cliente_mlflow=cliente) is None


def test_metricas_de_version_lee_las_del_run() -> None:
    cliente = MagicMock()
    cliente.get_model_version.return_value = SimpleNamespace(version="4", run_id="run-abc")
    cliente.get_run.return_value = SimpleNamespace(
        data=SimpleNamespace(metrics={"valid_rmse": 4.5, "valid_mae": 3.0})
    )
    metricas = registry.metricas_de_version("modelo-x", 4, cliente_mlflow=cliente)
    assert metricas == {"valid_rmse": 4.5, "valid_mae": 3.0}


def test_metricas_de_version_sin_run_asociado() -> None:
    cliente = MagicMock()
    cliente.get_model_version.return_value = SimpleNamespace(version="4", run_id=None)
    assert registry.metricas_de_version("modelo-x", 4, cliente_mlflow=cliente) == {}


def test_explicar_por_que_no_stages_es_coherente_con_el_codigo() -> None:
    """El texto didactico vive en el codigo para que no se contradiga con el.

    El notebook y la model card imprimen ESTA funcion. Si la explicacion
    estuviera duplicada en un markdown, en seis meses habria dos versiones
    incompatibles: un modulo ensenando aliases y otro promoviendo con stages.
    """
    texto = registry.explicar_por_que_no_stages()
    assert config.ALIAS_PRODUCCION in texto
    assert config.TAG_VALIDACION in texto
    assert "2.9.0" in texto
    assert "rollback" in texto.lower()
    # La API deprecada se menciona solo para decir que no se usa.
    assert "set_registered_model_alias" in texto
