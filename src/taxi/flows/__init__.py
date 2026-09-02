"""Flows de Prefect 3 del caso guia (Sesion 4 — Orquestacion y Continuous Training).

Este paquete contiene **la unica** implementacion orquestada del pipeline. El
material de clase (`sesiones/s04-orquestacion/`) importa de aqui en lugar de
duplicarlo. Una copia por sesion significa el mismo problema resuelto varias
veces, con features distintas en cada copia y ninguna fuente de verdad.

Modulos:

- :mod:`taxi.flows.training` — flow de entrenamiento. Registra el candidato con
  el alias ``candidate`` y **no lo promueve**: la promocion es un gate y el gate
  vive en CI (Sesion 6).
- :mod:`taxi.flows.batch` — pipeline batch de predicciones, con trazabilidad de
  la version de modelo que produjo cada fila.
- :mod:`taxi.flows.deploy` — deployments: ``serve`` para clase y ``deploy`` con
  work pool para infraestructura dinamica.

No se re-exporta nada a proposito: importar ``taxi.flows`` no deberia arrastrar
xgboost ni mlflow. Quien necesita un flow importa su modulo.
"""

from __future__ import annotations

__all__: list[str] = []
