"""Monitoreo de datos y de modelo: deteccion de drift y reporte accionable.

Problema que resuelve el paquete
--------------------------------
Un modelo desplegado no avisa cuando deja de servir. El entrenamiento y el
deployment tienen un final claro —el modelo queda registrado, la API responde—;
el monitoreo no tiene final: es la parte del sistema que responde "sigue siendo
valido lo que desplegamos?" de forma continua.

Este paquete separa deliberadamente tres responsabilidades, y esa separacion es
parte del contenido de la sesion:

- ``estadistico``: **calcula**. Tests, tamanos de efecto y veredicto por columna,
  con scipy y nada mas. Sin I/O, sin librerias de monitoreo. Es el plan B y es la
  explicacion de que hace un detector de drift por dentro.
- ``reporte``: **traduce y presenta**. Aisla la forma del ``dict()`` de Evidently
  (que cambia entre versiones), la tabla de consola y el JSON que consume el CI.
- ``check_drift``: **decide y falla**. Carga los datos reales, genera el HTML,
  compara con el umbral del curso y termina con exit code distinto de cero cuando
  hay que actuar.

Lo que NO esta aqui: las metricas del servicio (latencia, throughput, errores).
Eso vive en ``taxi.api.metricas`` con Prometheus, porque responde otra pregunta.
Prometheus mide el **servicio**; este paquete mide los **datos y el modelo**.
"""

from __future__ import annotations

from taxi.monitoring.estadistico import (
    ResultadoColumna,
    ResultadoDrift,
    detectar_drift,
)

__all__ = [
    "ResultadoColumna",
    "ResultadoDrift",
    "detectar_drift",
]
