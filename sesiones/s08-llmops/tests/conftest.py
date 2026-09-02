"""Fixtures de la sesion 8. Todo corre sin red y sin API key.

Por que existe un conftest local
--------------------------------
El paquete ``clasificador`` vive en ``sesiones/s08-llmops/src`` y no en
``src/taxi``, asi que no esta en el ``pythonpath`` que declara
``pyproject.toml``. Este conftest lo agrega, lo que permite correr los tests de
dos formas equivalentes::

    pytest sesiones/s08-llmops/tests        # solo la sesion 8
    pytest                                  # toda la suite, sesion 8 incluida

Se prefirio esto a mover el paquete a ``src/`` porque instalar el extra
``llmops`` no debe ser un requisito para correr la suite del caso guia.

Por que el tracing se desactiva
-------------------------------
Hallazgo medido en este repo: con ``MLFLOW_TRACKING_URI`` apuntando a un servidor
que no responde, una funcion decorada con ``@mlflow.trace`` **se queda colgada**
en el reintento con backoff del exporter (mas de 2 minutos, sin retornar). Un
test suite que depende de que un servidor este caido o levantado no es
determinista.

``tracing.configurar(modo="off")`` deja el decorador como no-op de coste cero. Es
la misma decision que ``registry.fallar_rapido()`` en el caso guia: la
observabilidad no puede ser un punto de fallo de lo observado.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from clasificador import prompts, tracing
from clasificador.proveedor import ProveedorFake
from clasificador.scorers.juez import JuezFake


@pytest.fixture(autouse=True, scope="session")
def _tracing_desactivado() -> None:
    """Desactiva el tracing en toda la sesion de tests. Ver el docstring."""
    tracing.configurar(modo="off")


@pytest.fixture
def proveedor() -> ProveedorFake:
    """Proveedor determinista, sin red y sin costo."""
    return ProveedorFake()


@pytest.fixture
def juez() -> JuezFake:
    """Juez por reglas, determinista."""
    return JuezFake()


@pytest.fixture
def plantilla_v2() -> prompts.Plantilla:
    """Prompt v2 cargado del disco, sin tocar el registry."""
    return prompts.cargar_local("v2")


@pytest.fixture
def plantilla_v1() -> prompts.Plantilla:
    """Prompt v1 cargado del disco."""
    return prompts.cargar_local("v1")
