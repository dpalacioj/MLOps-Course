"""Servicio de inferencia: contrato HTTP, carga del modelo e instrumentacion.

Cuatro modulos con una responsabilidad cada uno, para que se puedan testear por
separado:

- ``schemas``:  el contrato de entrada y salida (Pydantic v2).
- ``modelo``:   carga desde el Model Registry por alias y adaptacion de requests
                a las features del contrato compartido.
- ``metricas``: instrumentacion Prometheus del servicio.
- ``main``:     el wiring de FastAPI (rutas, lifespan, manejo de errores).

Este ``__init__`` no re-exporta nada a proposito: importar ``taxi.api`` no debe
arrastrar FastAPI ni mlflow. Quien necesita la aplicacion pide
``taxi.api.main:app``, que es exactamente lo que reciben uvicorn y el CMD de la
imagen.
"""
