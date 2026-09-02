"""Entrenamiento, evaluacion y ciclo de vida del modelo.

Separacion de responsabilidades del paquete:

- ``train``: construye pipelines, entrena y deja evidencia en MLflow.
- ``evaluate``: calcula metricas (globales y por subgrupo) y define la politica
  del gate de promocion como funciones puras, testeables sin infraestructura.
- ``registry``: envuelve el Model Registry con aliases y tags.

Los submodulos no se importan aqui a proposito: ``train`` arrastra xgboost,
optuna y matplotlib, y no todo consumidor de ``taxi.models`` los necesita (la
API solo usa ``registry.cargar_por_alias``). Importar el paquete no deberia
costar dos segundos de arranque.
"""

from __future__ import annotations

__all__ = ["evaluate", "registry", "train"]
