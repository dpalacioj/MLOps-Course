"""Servicio HTTP de inferencia (sesion 5) e instrumentacion (sesion 7).

Problema que resuelve: un modelo en un notebook no le sirve a nadie. Este modulo
lo convierte en un servicio con un contrato explicito, observable, que arranca en
un contenedor y del que se puede decir con precision que version esta
respondiendo.

Todo lo que hay aqui es **wiring**: rutas HTTP, ciclo de vida y traduccion de
errores. La logica vive en modulos separados y testeables por su cuenta
(``schemas`` el contrato, ``modelo`` la carga y la inferencia, ``metricas`` la
instrumentacion). Un `main.py` que ademas carga modelos y construye features es
el que nadie puede testear sin levantar el servidor completo.

Cinco atajos tentadores que este modulo evita. Todos son comunes en una API de
inferencia escrita a las prisas, y todos fallan tarde:

1. ``@app.on_event("startup")``, deprecado desde FastAPI 0.93. Aqui se usa
   ``lifespan``, que ademas permite liberar recursos al apagar y es lo unico que
   funciona igual bajo tests y bajo uvicorn.
2. ``allow_origins=["*"]`` junto a ``allow_credentials=True`` es una combinacion
   invalida: el navegador rechaza la respuesta porque no se puede devolver
   ``Access-Control-Allow-Origin: *`` con credenciales. Ademas, si funcionara,
   cualquier sitio web podria hacer requests autenticados a la API. Aqui los
   origenes son explicitos y configurables.
3. ``HTTPException(detail=f"...{str(e)}")``, que filtra la excepcion interna al
   cliente. Aqui el detalle va al log con un id de correlacion y al cliente va
   un mensaje estable.
4. Endpoints de prediccion declarados ``async def`` que dentro llaman a
   ``model.predict``, que es bloqueante: cada inferencia congela el event loop
   y el servidor pierde toda su concurrencia. Aqui se declaran ``def``
   (sincronos) a proposito, para que Starlette los ejecute en su threadpool.
5. Copiar el modelo a la imagen con ``shutil.copytree``. Aqui se resuelve del
   Model Registry por alias; el porque esta en ``modelo.py``.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as version_paquete
from typing import Final

from fastapi import Depends, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from taxi.api import metricas
from taxi.api.modelo import (
    CargadorModelo,
    construir_registros,
    obtener_cargador,
)
from taxi.api.schemas import (
    MAX_VIAJES_POR_LOTE,
    ErrorResponse,
    LoteRequest,
    LoteResponse,
    ModeloResponse,
    PrediccionResponse,
    SaludResponse,
    ViajeRequest,
)
from taxi.config import UMBRAL_VIAJE_LARGO_MIN
from taxi.features.contract import FEATURES

logging.basicConfig(
    level=os.getenv("TAXI_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def _version_api() -> str:
    """Version del paquete instalado.

    Se lee de la metadata de la distribucion en lugar de escribirla a mano. Es el
    mismo principio que en el Dockerfile: una sola fuente de verdad
    (``pyproject.toml``) en lugar de un numero duplicado que se desactualiza y
    hace que `/health` mienta sobre que codigo esta corriendo.
    """
    try:
        return version_paquete("mlops-curso")
    except PackageNotFoundError:  # pragma: no cover - solo sin instalar el paquete
        return "0.0.0+no-instalado"


VERSION_API: Final[str] = _version_api()

#: Mensajes que SI pueden salir al cliente. Estables, sin internals.
MSG_SIN_MODELO: Final[str] = (
    "El servicio no tiene un modelo cargado y no puede predecir. "
    "Consulta /health para ver el estado."
)
MSG_ERROR_INFERENCIA: Final[str] = "No se pudo calcular la prediccion."
MSG_ERROR_INTERNO: Final[str] = "Error interno del servicio."
MSG_ERROR_VALIDACION: Final[str] = "El request no cumple el contrato de la API."


# =============================================================================
# CORS
# =============================================================================
def origenes_cors() -> list[str]:
    """Origenes permitidos, leidos de ``TAXI_CORS_ORIGENES``.

    El default cubre un frontend local de desarrollo. En produccion se pasa la
    lista real por variable de entorno: los origenes son configuracion de
    despliegue, no una constante del codigo.
    """
    crudo = os.getenv("TAXI_CORS_ORIGENES", "http://localhost:3000,http://127.0.0.1:3000")
    return [o.strip() for o in crudo.split(",") if o.strip()]


def _configurar_cors(app: FastAPI) -> None:
    """Registra el middleware de CORS con una combinacion valida.

    La regla del estandar: con ``Access-Control-Allow-Credentials: true`` el
    header de origen NO puede ser ``*``. Si alguien configura el comodin, se
    desactivan las credenciales y se avisa, en lugar de desplegar una politica
    que el navegador rechaza y que nadie entiende por que falla.

    ``allow_methods`` y ``allow_headers`` se declaran explicitos por el mismo
    motivo por el que el contrato usa ``extra="forbid"``: enumerar lo permitido
    es mas barato de auditar que enumerar lo prohibido.
    """
    origenes = origenes_cors()
    comodin = "*" in origenes
    if comodin:
        logger.warning(
            "TAXI_CORS_ORIGENES incluye '*': se desactivan las credenciales porque "
            "'*' con allow_credentials=True es una combinacion invalida que el "
            "navegador rechaza. Declara los origenes explicitamente."
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origenes,
        allow_credentials=not comodin,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )


# =============================================================================
# Errores
# =============================================================================
def _nuevo_id_correlacion() -> str:
    """Id corto para cruzar la respuesta del cliente con el log del servidor.

    En un sistema real este id viene propagado del ingress o del tracing
    distribuido (``traceparent``) para poder seguir un request entre servicios.
    Aqui se genera local porque no hay upstream, y se genera nuestro en lugar de
    confiar en un header del cliente: un id que viene de fuera es texto no
    confiable inyectado en los logs.
    """
    return uuid.uuid4().hex[:12]


def _error(
    codigo: int,
    mensaje: str,
    *,
    id_correlacion: str | None = None,
    detalle_validacion: list[dict] | None = None,
) -> JSONResponse:
    """Construye una respuesta de error con el envelope unico de la API."""
    cuerpo = ErrorResponse(
        error=mensaje,
        id_correlacion=id_correlacion,
        detalle_validacion=detalle_validacion,
    )
    return JSONResponse(status_code=codigo, content=jsonable_encoder(cuerpo))


# =============================================================================
# Ciclo de vida
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Carga el modelo al arrancar y libera al apagar.

    Reemplaza a ``@app.on_event("startup")``. Cargar aqui —y no en el primer
    request— evita que un usuario pague la descarga del artefacto: ese cold start
    puede ser de varios segundos y se manifiesta como un timeout aparentemente
    aleatorio en el primer request tras cada despliegue.

    No se aborta si la carga falla. Un contenedor que muere al arrancar entra en
    CrashLoopBackOff y no deja consultar `/health`, que es justo donde esta
    escrito el motivo del fallo.
    """
    cargador = obtener_cargador()
    logger.info("Arrancando API version=%s uri_modelo=%s", VERSION_API, cargador.uri)
    cargador.cargar()
    if (meta := cargador.metadatos) is not None:
        metricas.fijar_modelo(meta.nombre, meta.version, meta.uri)
    else:
        logger.warning(
            "API arrancada en modo degradado (motivo=%s): /predict devolvera 503",
            cargador.error,
        )
    yield
    logger.info("Apagando API")


# =============================================================================
# Aplicacion
# =============================================================================
app = FastAPI(
    title="NYC Taxi — API de duracion de viajes",
    version=VERSION_API,
    description=(
        "Predice la duracion en minutos de un viaje de green taxi en Nueva York.\n\n"
        "El modelo se resuelve del Model Registry de MLflow por alias "
        "(`models:/<nombre>@champion`): la imagen contiene el codigo, no el "
        "artefacto. Cada respuesta incluye `model_version` para que una "
        "prediccion sea atribuible a un artefacto concreto.\n\n"
        "Endpoints operativos: `/health` (liveness) y `/metrics` (exposicion "
        "Prometheus). `/metrics` no aparece en este esquema a proposito: lo "
        "consume Prometheus, no un cliente de la API."
    ),
    lifespan=lifespan,
)
_configurar_cors(app)


@app.exception_handler(RequestValidationError)
async def manejar_validacion(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Traduce los errores de validacion al envelope unico de la API.

    Aqui el detalle SI se devuelve: describe el request del cliente, no el
    interior del servidor. Es informacion que el cliente necesita para
    corregirse.

    Trade-off asumido: FastAPI devuelve por defecto ``{"detail": [...]}`` y este
    handler cambia la forma a ``{"error", "detalle_validacion"}``. Se rompe la
    convencion por defecto para tener UN solo envelope de error en toda la API;
    el esquema OpenAPI lo documenta, asi que el cliente no tiene que adivinarlo.
    """
    metricas.registrar_error("validacion")
    return _error(
        422,
        MSG_ERROR_VALIDACION,
        detalle_validacion=jsonable_encoder(exc.errors()),
    )


@app.exception_handler(Exception)
async def manejar_no_previsto(request: Request, exc: Exception) -> JSONResponse:
    """Red de seguridad: nada sale del servicio con el texto de una excepcion.

    Los endpoints ya capturan sus fallos esperables. Este handler existe para lo
    demas —un bug en un middleware, un ``KeyError`` en una rama nueva— porque el
    comportamiento por defecto seria una traza de Starlette en el cuerpo de la
    respuesta cuando el servidor corre en modo debug.
    """
    cid = _nuevo_id_correlacion()
    metricas.registrar_error("interno")
    logger.exception(
        "Error no previsto id_correlacion=%s metodo=%s ruta=%s",
        cid,
        request.method,
        request.url.path,
    )
    return _error(500, MSG_ERROR_INTERNO, id_correlacion=cid)


# =============================================================================
# Endpoints
# =============================================================================
@app.get("/", include_in_schema=False)
async def raiz() -> RedirectResponse:
    """Manda la raiz a la documentacion interactiva.

    Un 404 en `/` es la primera impresion mas comun de una API interna. Redirigir
    a `/docs` cuesta dos lineas y ahorra la pregunta "esta caido?" en cada demo.
    """
    return RedirectResponse(url="/docs")


@app.get("/metrics", include_in_schema=False)
def metricas_prometheus() -> Response:
    """Exposicion de metricas en el formato de texto de Prometheus.

    Se declara como ruta normal y no con ``app.mount("/metrics", make_asgi_app())``
    por una razon concreta: una sub-aplicacion montada responde en ``/metrics/``
    (con barra final) y redirige ``/metrics`` con un 307. Prometheus sigue la
    redireccion, pero un ``curl -s /metrics | grep taxi_`` en clase devuelve un
    cuerpo vacio y parece que "no hay metricas". ``generate_latest`` es la misma
    funcion que usa el exporter por debajo; no se reimplementa nada.
    """
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


@app.get("/health", response_model=SaludResponse, tags=["operacion"])
async def salud(cargador: CargadorModelo = Depends(obtener_cargador)) -> SaludResponse:
    """Estado del servicio. Responde 200 mientras el proceso este vivo.

    Devuelve 200 incluso sin modelo, a proposito: es un liveness check. El campo
    ``model_loaded`` es el que debe consultar un readiness check. Ver el
    docstring de ``SaludResponse``.
    """
    meta = cargador.metadatos
    return SaludResponse(
        status="ok" if cargador.cargado else "degradado",
        model_loaded=cargador.cargado,
        model_name=meta.nombre if meta else None,
        model_version=meta.version if meta else None,
        model_uri=cargador.uri,
        version_api=VERSION_API,
    )


@app.get(
    "/modelo",
    response_model=ModeloResponse,
    tags=["operacion"],
    responses={503: {"model": ErrorResponse, "description": "Sin modelo cargado"}},
)
async def info_modelo(
    cargador: CargadorModelo = Depends(obtener_cargador),
) -> ModeloResponse | JSONResponse:
    """Metadatos del modelo cargado, incluida la lista de features que consume."""
    meta = cargador.metadatos
    if meta is None:
        metricas.registrar_error("modelo_no_disponible")
        return _error(503, MSG_SIN_MODELO)
    return ModeloResponse(
        model_name=meta.nombre,
        model_version=meta.version,
        model_uri=meta.uri,
        features=list(FEATURES),
        umbral_viaje_largo_min=UMBRAL_VIAJE_LARGO_MIN,
    )


# Nota deliberada: `def`, no `async def`.
#
# `modelo.predecir` es CPU-bound y bloqueante. En una corrutina bloquearia el
# event loop y el servidor atenderia un request a la vez, sin importar cuantos
# workers tenga. Declarado sincrono, Starlette lo ejecuta en su threadpool y el
# loop sigue libre para aceptar conexiones. Es un cambio de una palabra con
# efecto directo en el throughput medido.
@app.post(
    "/predict",
    response_model=PrediccionResponse,
    tags=["inferencia"],
    responses={
        422: {"model": ErrorResponse, "description": "Request invalido"},
        500: {"model": ErrorResponse, "description": "Fallo de inferencia"},
        503: {"model": ErrorResponse, "description": "Sin modelo cargado"},
    },
)
def predecir(
    viaje: ViajeRequest,
    cargador: CargadorModelo = Depends(obtener_cargador),
) -> PrediccionResponse | JSONResponse:
    """Predice la duracion de un viaje."""
    resultado = _predecir_lote(cargador, [viaje])
    if isinstance(resultado, JSONResponse):
        return resultado
    predicciones, _ = resultado
    return predicciones[0]


@app.post(
    "/predict/batch",
    response_model=LoteResponse,
    tags=["inferencia"],
    responses={
        422: {
            "model": ErrorResponse,
            "description": f"Request invalido o mas de {MAX_VIAJES_POR_LOTE} viajes",
        },
        500: {"model": ErrorResponse, "description": "Fallo de inferencia"},
        503: {"model": ErrorResponse, "description": "Sin modelo cargado"},
    },
)
def predecir_lote(
    lote: LoteRequest,
    cargador: CargadorModelo = Depends(obtener_cargador),
) -> LoteResponse | JSONResponse:
    """Predice la duracion de varios viajes en una sola llamada de inferencia.

    El tope de ``MAX_VIAJES_POR_LOTE`` lo aplica el schema, no este endpoint: un
    limite declarado en el contrato aparece en OpenAPI y el cliente lo ve antes
    de escribir el request.
    """
    resultado = _predecir_lote(cargador, lote.viajes)
    if isinstance(resultado, JSONResponse):
        return resultado
    predicciones, latencia_ms = resultado
    primera = predicciones[0]
    return LoteResponse(
        predicciones=predicciones,
        total=len(predicciones),
        model_name=primera.model_name,
        model_version=primera.model_version,
        # Redondeada igual que en cada elemento: el contrato promete que es el
        # MISMO valor, y un cliente que compare los dos campos debe obtener True.
        latencia_ms=round(latencia_ms, 3),
    )


def _predecir_lote(
    cargador: CargadorModelo,
    viajes: list[ViajeRequest],
) -> tuple[list[PrediccionResponse], float] | JSONResponse:
    """Camino de inferencia compartido por los dos endpoints.

    Devuelve las predicciones y la latencia, o una respuesta de error ya
    formateada. Vive en una sola funcion para que la instrumentacion y el manejo
    de errores no se dupliquen. Con una copia del try/except por endpoint, solo
    una se mantiene al dia cuando cambia el contrato de features, y el otro
    camino empieza a filtrar.
    """
    meta = cargador.metadatos
    if meta is None or not cargador.cargado:
        metricas.registrar_error("modelo_no_disponible")
        logger.warning("Prediccion rechazada: no hay modelo cargado (uri=%s)", cargador.uri)
        return _error(503, MSG_SIN_MODELO)

    cid = _nuevo_id_correlacion()
    try:
        registros = construir_registros(viajes)
        inicio = time.perf_counter()
        duraciones = cargador.predecir(registros)
        latencia_s = time.perf_counter() - inicio
    except Exception:
        metricas.registrar_error("inferencia")
        # exception() incluye la traza en el log del servidor. Al cliente solo va
        # el mensaje estable mas el id: con el id, quien opera el servicio
        # encuentra esta linea en segundos.
        logger.exception(
            "Fallo la inferencia id_correlacion=%s n=%d model_version=%s",
            cid,
            len(viajes),
            meta.version,
        )
        return _error(500, MSG_ERROR_INFERENCIA, id_correlacion=cid)

    if len(duraciones) != len(viajes):
        # Defensa contra un modelo que devuelve otra cantidad de filas. Sin este
        # chequeo, un desalineamiento silencioso asocia cada prediccion al viaje
        # equivocado, que es peor que un error.
        metricas.registrar_error("inferencia")
        logger.error(
            "El modelo devolvio %d predicciones para %d viajes id_correlacion=%s",
            len(duraciones),
            len(viajes),
            cid,
        )
        return _error(500, MSG_ERROR_INFERENCIA, id_correlacion=cid)

    latencia_ms = latencia_s * 1000.0
    metricas.observar_latencia(version=meta.version, segundos=latencia_s)

    predicciones = [
        PrediccionResponse.desde_duracion(
            duracion_min=duracion,
            model_name=meta.nombre,
            model_version=meta.version,
            latencia_ms=latencia_ms,
        )
        for duracion in duraciones
    ]
    for prediccion in predicciones:
        metricas.registrar_prediccion(version=meta.version, viaje_largo=prediccion.viaje_largo)

    return predicciones, latencia_ms


if __name__ == "__main__":  # pragma: no cover
    # Solo para depurar a mano. En el contenedor arranca uvicorn como comando de
    # la imagen, y en local `make serve` usa `uvicorn --reload`. Un `uvicorn.run`
    # aqui con host 0.0.0.0 hardcodeado expone el servicio en toda la red del
    # equipo sin que nadie lo pida; de ahi que el default sea 127.0.0.1.
    import uvicorn

    uvicorn.run(
        "taxi.api.main:app",
        host=os.getenv("TAXI_API_HOST", "127.0.0.1"),
        port=int(os.getenv("TAXI_API_PORT", "8000")),
        reload=True,
    )
