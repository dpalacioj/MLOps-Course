"""Contratos de entrada y salida de la API de inferencia.

Problema que resuelve: una API de ML es una **frontera de confianza**. Del otro
lado hay clientes que no conocen el modelo, no leyeron el contrato de features y
van a mandar lo que sea. Sin validacion explicita, un valor fuera de rango no
produce un error: produce una prediccion silenciosamente absurda que el cliente
consume como valida.

FastAPI deriva de estas clases la validacion en runtime (422 con detalle) y el
esquema OpenAPI. El contrato y la documentacion no pueden divergir porque son el
mismo objeto.

Dos decisiones que conviene notar:

1. **Pydantic valida un registro; Pandera valida DataFrames.** Este modulo NO
   reemplaza a ``data/contract.py``: son fronteras distintas. Los rangos
   coinciden a proposito — si el modelo nunca vio un valor, la API tampoco debe
   aceptarlo.
2. **La respuesta incluye la version del modelo.** Sin ese campo, una prediccion
   mala es imposible de atribuir a un artefacto concreto tres semanas despues.

TODO(estudiante) 16: reemplaza los campos por los de tu problema. Pide solo
features CRUDAS: pedirle al cliente features derivadas es pedirle que replique tu
pipeline, y el dia que cambies una derivacion todos los clientes quedan
desalineados en silencio.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Limites del contrato — los mismos que el contrato de datos
# =============================================================================
CANTIDAD_MIN: Final[float] = 0.0
CANTIDAD_MAX: Final[float] = 10_000.0
PRECIO_MIN: Final[float] = 0.0
PRECIO_MAX: Final[float] = 1_000_000.0

#: Tope de elementos por lote. Existe por dos razones operativas, no esteticas:
#: acota la memoria por request (un lote sin limite es un vector de DoS) y acota
#: la latencia de cola, porque un lote gigante bloquea el worker que lo atiende.
MAX_ITEMS_POR_LOTE: Final[int] = 500

#: Un timestamp a mas de 30 dias en el futuro es casi siempre un bug del cliente
#: (milisegundos leidos como segundos, ano mal parseado), no una reserva.
MAX_ADELANTO: Final[timedelta] = timedelta(days=30)


class ItemRequest(BaseModel):
    """Un registro del que se quiere predecir el objetivo."""

    # extra="forbid": un cliente que manda `Region` en lugar de `region` recibe
    # un 422 en lugar de una prediccion calculada con un default silencioso.
    # Fallar ruidosamente es mas barato que degradar en silencio.
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "categoria": "A",
                    "region": "norte",
                    "canal": "web",
                    "cantidad": 3.0,
                    "precio_unitario": 19990.0,
                    "descuento": 0.1,
                    "ts": "2024-01-15T08:30:00",
                }
            ]
        },
    )

    categoria: str = Field(..., min_length=1, max_length=64)
    region: str = Field(..., min_length=1, max_length=64)
    canal: str = Field(..., min_length=1, max_length=64)
    cantidad: float = Field(..., ge=CANTIDAD_MIN, le=CANTIDAD_MAX)
    precio_unitario: float = Field(..., ge=PRECIO_MIN, le=PRECIO_MAX)
    descuento: float = Field(0.0, ge=0.0, le=1.0)
    ts: datetime | None = Field(
        default=None,
        description=(
            "Timestamp del evento, SIN zona horaria y en la hora local de los "
            "datos de entrenamiento. Si se omite se usa la hora actual, lo que "
            "vuelve la prediccion no reproducible: ver el validador."
        ),
    )

    @field_validator("ts")
    @classmethod
    def _validar_ts(cls, valor: datetime | None) -> datetime | None:
        """Rechaza timestamps con zona horaria y fechas absurdamente futuras.

        Se RECHAZA el offset en lugar de convertirlo: la conversion silenciosa
        esconde el malentendido. Un cliente que manda ``2024-01-15T08:30:00Z``
        cree hablar de las 08:30 y el modelo entenderia otra hora, con lo que
        `hora` —que es una feature— queda desplazada. Es mejor que se entere con
        un 422 que despues con un reporte de drift.
        """
        if valor is None:
            return None
        if valor.tzinfo is not None:
            raise ValueError(
                "ts debe venir sin zona horaria, en la misma hora local que los "
                "datos con los que se entreno el modelo."
            )
        if valor > datetime.now() + MAX_ADELANTO:
            raise ValueError(
                f"ts esta a mas de {MAX_ADELANTO.days} dias en el futuro; "
                "revisa las unidades del timestamp."
            )
        return valor

    def ts_efectivo(self) -> datetime:
        """Timestamp que realmente se usara para derivar features de calendario."""
        return self.ts if self.ts is not None else datetime.now()


class LoteRequest(BaseModel):
    """Varios registros en un solo request.

    No es azucar sintactico: amortiza el costo fijo por llamada (parseo,
    construccion del DataFrame, overhead de ``predict``) sobre N registros. En
    inferencia sklearn ese costo fijo suele dominar.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[ItemRequest] = Field(..., min_length=1, max_length=MAX_ITEMS_POR_LOTE)


# =============================================================================
# Responses
# =============================================================================
class PrediccionResponse(BaseModel):
    """Una prediccion, con la referencia al artefacto que la produjo."""

    prediccion: float
    modelo: str = Field(..., description="Nombre del modelo registrado.")
    version_modelo: str | None = Field(
        None, description="Version del registry. None si se sirve sin registry."
    )


class LoteResponse(BaseModel):
    """Predicciones de un lote, en el MISMO orden que los items de entrada."""

    predicciones: list[float]
    modelo: str
    version_modelo: str | None = None


class SaludResponse(BaseModel):
    """Estado del servicio.

    Reporta si el modelo esta cargado y cual. Un ``/health`` que devuelve
    ``{"status": "ok"}`` sin mirar el modelo miente: el proceso esta vivo y el
    servicio no sirve. Ese es el healthcheck que hace que un orquestador mande
    trafico a un contenedor roto.
    """

    estado: str
    modelo_cargado: bool
    modelo: str
    version_modelo: str | None = None
