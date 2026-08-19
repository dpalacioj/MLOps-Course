"""Servicio HTTP de inferencia.

Todo lo que hay aqui es **wiring**: rutas, ciclo de vida y traduccion de errores.
La logica de contrato vive en ``schemas.py`` y la de features en
``features/contract.py``. Un ``main.py`` que ademas carga modelos y construye
features es el que nadie puede testear sin levantar el servidor completo.

Cinco anti-patrones que este archivo evita a proposito:

1. ``@app.on_event("startup")`` esta deprecado desde FastAPI 0.93 -> se usa
   ``lifespan``, que ademas libera recursos al apagar y funciona igual bajo
   ``TestClient`` y bajo uvicorn.
2. ``allow_origins=["*"]`` junto a ``allow_credentials=True`` es una combinacion
   invalida: el navegador rechaza la respuesta. Y si funcionara, cualquier sitio
   podria hacer requests autenticados a la API.
3. ``HTTPException(detail=str(e))`` filtra la excepcion interna al cliente. El
   detalle va al log; al cliente va un mensaje estable.
4. Los endpoints de prediccion se declaran ``def`` (sincronos) a proposito.
   ``model.predict`` es bloqueante: dentro de un ``async def`` congelaria el
   event loop y el servidor perderia toda su concurrencia. Siendo sincronos,
   Starlette los corre en su threadpool.
5. El modelo se resuelve del registry por alias, no se copia a la imagen. Asi el
   rollback es mover un alias y no reconstruir el contenedor.

TODO(estudiante) 17: agrega ``/metrics`` con ``prometheus_client`` (contador de
predicciones por version de modelo, histograma de latencia) cuando llegues al
modulo de monitoreo. Prometheus mide el SERVICIO; Evidently mide los DATOS. Son
dos preguntas distintas y hacen falta las dos.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from miproyecto.api.schemas import (
    ItemRequest,
    LoteRequest,
    LoteResponse,
    PrediccionResponse,
    SaludResponse,
)
from miproyecto.config import MODELO_REGISTRADO, uri_modelo
from miproyecto.features import contract as fc

logger = logging.getLogger(__name__)

#: Valor que desactiva la carga del modelo. Con `ninguno`, /health responde 200
#: con modelo_cargado=false y /predict devuelve 503. Es lo que permite verificar
#: la imagen en CI sin depender de que el registry este arriba.
SIN_MODELO = frozenset({"", "ninguno", "none"})


def modelo_uri_configurado() -> str:
    """URI del modelo, leida del entorno EN EL MOMENTO de usarla.

    Se lee aqui y no en una constante de modulo a proposito. Una constante
    `MODELO_URI = os.getenv(...)` se evalua al importar, asi que un test no puede
    cambiarla sin recargar el modulo — y el sintoma concreto es que el test de la
    API intenta hablar con un registry real, crea archivos de estado en el
    directorio del proyecto y depende de la red. Leer el entorno en el punto de
    uso hace la funcion testeable sin trucos.
    """
    return os.getenv("MIPROYECTO_MODELO_URI", uri_modelo())


def origenes_permitidos() -> list[str]:
    """Origenes CORS explicitos. Nunca "*" en un servicio con credenciales."""
    crudo = os.getenv("MIPROYECTO_CORS", "http://127.0.0.1:3000")
    return [o.strip() for o in crudo.split(",") if o.strip()]


class Estado:
    """Estado del proceso. Un objeto y no variables globales sueltas."""

    def __init__(self) -> None:
        self.modelo: Any | None = None
        self.version: str | None = None


estado = Estado()


def cargar_modelo() -> tuple[Any | None, str | None]:
    """Resuelve el modelo desde el registry por alias.

    Devuelve ``(None, None)`` si no hay modelo configurado o si la carga falla.
    Fallar el arranque cuando el registry no responde deja el servicio caido
    entero; devolver 503 en ``/predict`` y 200 en ``/health`` con
    ``modelo_cargado=false`` deja el diagnostico visible y el contenedor
    inspeccionable. Eleccion deliberada, no descuido.
    """
    uri = modelo_uri_configurado()
    if uri in SIN_MODELO:
        logger.warning("MIPROYECTO_MODELO_URI=%s: la API arranca sin modelo", uri)
        return None, None
    try:
        import mlflow

        modelo = mlflow.pyfunc.load_model(uri)
        version = getattr(getattr(modelo, "metadata", None), "model_uuid", None)
        logger.info("modelo cargado desde %s", uri)
        return modelo, str(version) if version else None
    except Exception:
        logger.exception("no se pudo cargar el modelo desde %s", uri)
        return None, None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Carga el modelo al arrancar y lo libera al apagar."""
    estado.modelo, estado.version = cargar_modelo()
    yield
    estado.modelo = None
    estado.version = None


app = FastAPI(
    title="API de inferencia — miproyecto",
    description="TODO(estudiante) 18: describe tu servicio y su contrato.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _a_dataframe(items: Sequence[ItemRequest]) -> pd.DataFrame:
    """Construye el dataframe de entrada usando el MISMO contrato de features.

    Este es el punto exacto donde se evita el training/serving skew: la API no
    reimplementa la derivacion de features, la importa.
    """
    filas = []
    for item in items:
        datos = item.model_dump(exclude={"ts"})
        datos[fc.COL_TIEMPO] = item.ts_efectivo()
        filas.append(datos)
    return fc.construir_features(pd.DataFrame(filas))


def _predecir(items: Sequence[ItemRequest]) -> list[float]:
    if estado.modelo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="el modelo no esta cargado; consulta /health",
        )
    correlacion = uuid.uuid4().hex[:8]
    try:
        entrada = fc.a_diccionarios(_a_dataframe(items))
        return [float(v) for v in estado.modelo.predict(entrada)]
    except Exception:
        # El detalle interno va al LOG con un id de correlacion; al cliente le
        # llega un mensaje estable y ese id. Devolver str(e) filtra rutas,
        # nombres de columnas y a veces credenciales.
        logger.exception("fallo la inferencia [%s]", correlacion)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"error interno al predecir (referencia {correlacion})",
        ) from None


@app.get("/health", response_model=SaludResponse, tags=["operacion"])
def salud() -> SaludResponse:
    """Estado del servicio y del modelo. Lo consume el healthcheck del contenedor."""
    return SaludResponse(
        estado="ok",
        modelo_cargado=estado.modelo is not None,
        modelo=MODELO_REGISTRADO,
        version_modelo=estado.version,
    )


@app.post("/predict", response_model=PrediccionResponse, tags=["inferencia"])
def predecir(item: ItemRequest) -> PrediccionResponse:
    """Prediccion de un registro."""
    return PrediccionResponse(
        prediccion=_predecir([item])[0],
        modelo=MODELO_REGISTRADO,
        version_modelo=estado.version,
    )


@app.post("/predict/batch", response_model=LoteResponse, tags=["inferencia"])
def predecir_lote(lote: LoteRequest) -> LoteResponse:
    """Predicciones de un lote, en el mismo orden que la entrada."""
    return LoteResponse(
        predicciones=_predecir(lote.items),
        modelo=MODELO_REGISTRADO,
        version_modelo=estado.version,
    )
