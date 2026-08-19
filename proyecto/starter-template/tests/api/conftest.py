"""Fixtures de los tests de la API.

Decision importante: los tests corren **sin modelo cargado**, forzado por
variable de entorno. Motivos, en orden de peso:

1. Es el estado en el que arranca la imagen en CI, asi que es el estado que hay
   que poder verificar.
2. Un test que intenta hablar con un registry real depende de la red, es lento y
   deja archivos de estado (`mlflow.db`, `mlruns/`) tirados en el directorio del
   proyecto. Un test no debe modificar el repositorio.
3. Un test que no corre en cada PR no protege nada, y los que necesitan
   infraestructura no corren en cada PR.

Los tests que SI necesitan un modelo se marcan con ``@pytest.mark.integration`` y
quedan fuera de ``pytest -m "not slow and not integration"``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _sin_modelo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fuerza el arranque sin modelo, de forma explicita y no por accidente."""
    monkeypatch.setenv("MIPROYECTO_MODELO_URI", "ninguno")


@pytest.fixture
def cliente() -> Iterator[TestClient]:
    """Cliente de prueba con el ``lifespan`` ejecutado.

    El context manager es lo que dispara el `lifespan`. Sin el, el modelo nunca
    se cargaria y el test estaria probando un estado que no existe en produccion.
    """
    from miproyecto.api.main import app

    with TestClient(app) as c:
        yield c
