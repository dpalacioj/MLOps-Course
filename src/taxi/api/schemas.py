"""Contratos de entrada y salida de la API de inferencia.

Problema que resuelve: una API de ML es una **frontera de confianza**. Del otro
lado hay clientes que no conocen el modelo, no leyeron el contrato de features y
mandaran lo que sea. Sin validacion explicita, un `PULocationID` de 9999 o una
distancia negativa no producen un error: producen una prediccion silenciosamente
absurda, que el cliente consume como si fuera valida.

Aqui se declara, en un solo lugar y de forma ejecutable, que es un request
valido y que forma tiene la respuesta. FastAPI deriva de estas clases tanto la
validacion en runtime (422 con detalle) como el esquema OpenAPI que documenta la
API. El contrato y la documentacion no pueden divergir porque son el mismo
objeto.

Dos decisiones que conviene notar:

1. **Pydantic valida un registro a la vez; Pandera valida DataFrames.** Este
   modulo NO reemplaza a ``taxi.data.contract``: son fronteras distintas. La API
   valida lo que entra por HTTP; el contrato de datos valida lo que entra al
   pipeline de entrenamiento. Los rangos coinciden a proposito (zonas 1-265,
   distancia 0-100 millas): si el modelo nunca vio un valor, la API tampoco debe
   aceptarlo.
2. **La respuesta incluye la version del modelo.** Es lo que hace auditable el
   sistema: sin ese campo, una prediccion mala es imposible de atribuir a un
   modelo concreto tres semanas despues.

Dos anti-patrones que este modulo evita: ``class Config`` (la API de Pydantic
v1, deprecada en v2 — aqui se usa ``model_config``), y una respuesta que devuelve
los datos de entrada mas la prediccion sin referencia al artefacto que la
produjo.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taxi.config import UMBRAL_VIAJE_LARGO_MIN

# =============================================================================
# Limites del contrato
# =============================================================================
#: Zonas de taxi de la NYC TLC. El taxi zone lookup define 1-265; cualquier otro
#: valor es un ID inventado por el cliente. Mismo rango que el contrato de datos
#: de la sesion 2, a proposito.
ZONA_MIN: Final[int] = 1
ZONA_MAX: Final[int] = 265

#: MILLAS, no kilometros. La unidad esta declarada aqui porque confundirla no
#: lanza ninguna excepcion: alimentar en km un modelo entrenado en millas solo
#: degrada la prediccion (~60%), en silencio.
DISTANCIA_MIN_MI: Final[float] = 0.0
DISTANCIA_MAX_MI: Final[float] = 100.0

#: Tope de elementos por lote. Existe por dos razones operativas, no esteticas:
#: acota la memoria por request (un lote sin limite es un vector de DoS) y acota
#: la latencia de cola, porque un lote gigante bloquea el worker que lo atiende.
MAX_VIAJES_POR_LOTE: Final[int] = 500

#: Un pickup a mas de 30 dias es casi siempre un bug del cliente (timestamp en
#: milisegundos, ano mal parseado), no una reserva.
MAX_ADELANTO_PICKUP: Final[timedelta] = timedelta(days=30)

#: Los timestamps de la TLC estan en hora **local de Nueva York**. El modelo
#: aprendio `hora_pickup` en esa zona. Si el default se calculara con la hora del
#: contenedor (UTC), la feature quedaria desplazada 4-5 horas y el modelo serviria
#: predicciones peores sin que nada falle. Se declara la zona explicitamente en
#: lugar de confiar en la variable TZ del host.
ZONA_HORARIA_NYC: Final[ZoneInfo] = ZoneInfo("America/New_York")


def ahora_en_nyc() -> datetime:
    """Hora actual en la zona horaria de los datos, sin tzinfo.

    Se devuelve naive porque ``features/contract.py`` trabaja con timestamps
    naive en hora local, igual que el parquet de la TLC.
    """
    return datetime.now(ZONA_HORARIA_NYC).replace(tzinfo=None)


# =============================================================================
# Requests
# =============================================================================
class ViajeRequest(BaseModel):
    """Un viaje del que se quiere predecir la duracion.

    Solo contiene los campos **crudos** que un cliente puede conocer antes del
    viaje. `PU_DO`, `hora_pickup` y `dia_semana_pickup` NO se piden: son
    derivadas y las calcula ``taxi.features.contract.construir_features``. Pedir
    features derivadas al cliente es como pedirle que replique el pipeline: la
    primera vez que cambie una derivacion, todos los clientes quedan
    desalineados en silencio.

    Sobre ``pickup_datetime``: **si no viene, se usa la hora actual en Nueva
    York**. Es una comodidad para demos y para el caso "pideme un taxi ahora",
    pero tiene consecuencias que hay que conocer:

    - La prediccion deja de ser reproducible: el mismo request enviado a las
      08:00 y a las 03:00 devuelve duraciones distintas, porque `hora_pickup` es
      una feature del modelo.
    - Un test que no fije ``pickup_datetime`` es no determinista por diseno.
    - En un backfill o en un batch sobre datos historicos, omitir el campo
      etiqueta todos los viajes con la hora del proceso, no la del viaje. Eso es
      training/serving skew introducido por la API.

    Regla practica: en produccion, mandar siempre ``pickup_datetime`` explicito.
    El default esta para que `/docs` sea usable sin leer esta nota.
    """

    # extra="forbid": un cliente que manda `PULocationId` (i minuscula) recibe un
    # 422 en lugar de una prediccion calculada con el default silencioso. Fallar
    # ruidosamente es mas barato que degradar en silencio.
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "PULocationID": 43,
                    "DOLocationID": 238,
                    "trip_distance": 2.4,
                    "pickup_datetime": "2023-05-15T08:30:00",
                }
            ]
        },
    )

    PULocationID: int = Field(
        ...,
        ge=ZONA_MIN,
        le=ZONA_MAX,
        description=f"Zona de origen (taxi zone de la NYC TLC, {ZONA_MIN}-{ZONA_MAX}).",
    )
    DOLocationID: int = Field(
        ...,
        ge=ZONA_MIN,
        le=ZONA_MAX,
        description=f"Zona de destino (taxi zone de la NYC TLC, {ZONA_MIN}-{ZONA_MAX}).",
    )
    trip_distance: float = Field(
        ...,
        ge=DISTANCIA_MIN_MI,
        le=DISTANCIA_MAX_MI,
        description="Distancia estimada del viaje en MILLAS (no kilometros).",
    )
    pickup_datetime: datetime | None = Field(
        default=None,
        description=(
            "Inicio del viaje en hora local de Nueva York y SIN zona horaria. "
            "Si se omite se usa la hora actual en Nueva York; ver el docstring "
            "del schema, porque vuelve la prediccion no reproducible."
        ),
    )

    @field_validator("pickup_datetime")
    @classmethod
    def _validar_pickup(cls, valor: datetime | None) -> datetime | None:
        """Rechaza timestamps con zona horaria y pickups absurdamente futuros.

        Se rechaza el offset en lugar de convertirlo por una razon didactica: la
        conversion silenciosa esconde el malentendido. Un cliente que manda
        `2023-05-15T08:30:00Z` cree estar hablando de las 08:30 y el modelo
        entenderia 04:30. Es mejor que se entere con un 422 que despues con un
        reporte de drift.
        """
        if valor is None:
            return None
        if valor.tzinfo is not None:
            raise ValueError(
                "pickup_datetime debe venir sin zona horaria y expresado en hora "
                "local de Nueva York, igual que los datos de la NYC TLC con los "
                "que se entreno el modelo."
            )
        if valor > ahora_en_nyc() + MAX_ADELANTO_PICKUP:
            raise ValueError(
                f"pickup_datetime esta a mas de {MAX_ADELANTO_PICKUP.days} dias en el "
                "futuro; revisa las unidades del timestamp."
            )
        return valor

    def pickup_efectivo(self) -> datetime:
        """Timestamp de pickup que realmente se usara para derivar features."""
        return self.pickup_datetime if self.pickup_datetime is not None else ahora_en_nyc()


class LoteRequest(BaseModel):
    """Varios viajes en un solo request.

    El lote no es solo azucar sintactico: amortiza el costo fijo por llamada
    (parseo, construccion del DataFrame, overhead de `predict`) sobre N viajes.
    En inferencia sklearn ese costo fijo suele dominar, asi que un lote de 100
    no tarda 100 veces mas que uno de 1.
    """

    model_config = ConfigDict(extra="forbid")

    viajes: list[ViajeRequest] = Field(
        ...,
        min_length=1,
        max_length=MAX_VIAJES_POR_LOTE,
        description=f"Entre 1 y {MAX_VIAJES_POR_LOTE} viajes.",
    )


# =============================================================================
# Responses
# =============================================================================
class PrediccionResponse(BaseModel):
    """Prediccion de un viaje, con la trazabilidad necesaria para auditarla."""

    model_config = ConfigDict(extra="forbid")

    duration_min: float = Field(..., description="Duracion predicha en minutos.")
    viaje_largo: bool = Field(
        ...,
        description=(
            f"True si la duracion predicha alcanza el umbral de "
            f"{UMBRAL_VIAJE_LARGO_MIN:.0f} minutos. El umbral vive en config.py, "
            "no aqui: es una decision de negocio, no de la API."
        ),
    )
    model_name: str = Field(..., description="Nombre del modelo registrado que respondio.")
    model_version: str = Field(
        ...,
        description=(
            "Version exacta del modelo. Es el campo que permite reconstruir, "
            "semanas despues, que artefacto produjo una prediccion concreta."
        ),
    )
    latencia_ms: float = Field(
        ...,
        ge=0.0,
        description=(
            "Latencia de la llamada de inferencia que produjo esta prediccion. "
            "En un lote es la latencia del lote completo, no una fraccion: la "
            "inferencia esta vectorizada y no existe un costo por elemento "
            "medible por separado."
        ),
    )

    @classmethod
    def desde_duracion(
        cls,
        *,
        duracion_min: float,
        model_name: str,
        model_version: str,
        latencia_ms: float,
    ) -> PrediccionResponse:
        """Construye la respuesta derivando ``viaje_largo`` del umbral.

        Existe para que la derivacion del target binario ocurra en UN lugar. El
        endpoint individual y el de lote la comparten; si cada uno hiciera su
        propia comparacion, un cambio de umbral se aplicaria a medias.
        """
        return cls(
            duration_min=round(duracion_min, 2),
            viaje_largo=duracion_min >= UMBRAL_VIAJE_LARGO_MIN,
            model_name=model_name,
            model_version=model_version,
            latencia_ms=round(latencia_ms, 3),
        )


class LoteResponse(BaseModel):
    """Respuesta del endpoint de lote."""

    model_config = ConfigDict(extra="forbid")

    predicciones: list[PrediccionResponse]
    total: int = Field(..., ge=0, description="Cantidad de predicciones devueltas.")
    model_name: str
    model_version: str
    latencia_ms: float = Field(
        ..., ge=0.0, description="Latencia de la llamada de inferencia del lote completo."
    )


class SaludResponse(BaseModel):
    """Estado del servicio.

    Semantica deliberada: este endpoint responde **200 siempre que el proceso
    este vivo**, incluso sin modelo cargado. Es un *liveness* check.

    Por que importa la distincion: si `/health` devolviera 503 al no haber
    modelo, el orquestador reiniciaria el contenedor en bucle y nadie podria
    leer el diagnostico. Con 200 + ``model_loaded=false`` el contenedor es
    inspeccionable, y quien necesite un *readiness* check (no enviar trafico
    hasta que haya modelo) lo construye sobre el campo ``model_loaded``.

    Anti-patron corregido: el `/health` anterior lanzaba `HTTPException(503,
    detail=f"...{str(e)}")`, es decir, filtraba el mensaje de la excepcion
    interna al cliente y ademas hacia imposible arrancar sin modelo.
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="'ok' si hay modelo servible, 'degradado' si no.")
    model_loaded: bool
    model_name: str | None = None
    model_version: str | None = None
    model_uri: str | None = Field(
        default=None,
        description=(
            "URI con la que se pidio el modelo. Se expone porque el error mas "
            "comun en clase es apuntar al registry equivocado, y verlo ahorra "
            "media hora de depuracion."
        ),
    )
    version_api: str = Field(..., description="Version del paquete que sirve la API.")


class ModeloResponse(BaseModel):
    """Metadatos del modelo que sirve el proceso.

    Existe separado de ``/health`` porque responde otra pregunta. `/health` es
    para el orquestador ("reinicio este contenedor?"); `/modelo` es para una
    persona ("que exactamente esta respondiendo y con que features?"). Exponer
    la lista de features evita la conversacion mas repetida en un equipo de ML:
    "el modelo usa la hora del pickup o no?".
    """

    model_config = ConfigDict(extra="forbid")

    model_name: str
    model_version: str
    model_uri: str
    features: list[str] = Field(..., description="Features que consume el modelo, en orden.")
    umbral_viaje_largo_min: float = Field(
        ..., description="Umbral en minutos usado para derivar `viaje_largo`."
    )


class ErrorResponse(BaseModel):
    """Error devuelto al cliente. Nunca contiene la excepcion interna.

    El anti-patron a evitar es ``detail=f"Error: {str(e)}"``, que es la forma
    mas rapida de escribir un handler y filtra rutas del filesystem, cadenas de
    conexion, nombres de columnas y trazas del ORM a cualquiera que sepa mandar
    un request malformado. El detalle tecnico va al log del servidor; al cliente
    va un mensaje estable mas un ``id_correlacion`` para cruzar ambos.
    """

    model_config = ConfigDict(extra="forbid")

    error: str = Field(..., description="Mensaje seguro, apto para mostrar al usuario final.")
    id_correlacion: str | None = Field(
        default=None,
        description="Identificador para localizar el detalle tecnico en los logs del servidor.",
    )
    detalle_validacion: list[dict] | None = Field(
        default=None,
        description=(
            "Solo en errores 422. Aqui SI conviene ser explicito: el detalle "
            "describe el request del cliente, no el interior del servidor."
        ),
    )
