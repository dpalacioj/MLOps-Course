"""Contrato de salida del clasificador de quejas, con validacion Pydantic.

Problema que resuelve
---------------------
Un LLM no devuelve un objeto: devuelve texto que *se parece* a lo que pediste.
Puede envolver el JSON en un bloque de codigo, inventar una categoria que no
esta en el enum, poner ``severidad: "alta"`` donde se pidio un entero, o agregar
un campo extra que aguas abajo nadie lee.

En ML clasico el contrato de salida es trivial: el modelo devuelve un float. En
LLMOps la salida es texto libre y el contrato hay que **imponerlo y verificarlo**
en tiempo de ejecucion. Este modulo es ese contrato, y es la pieza que convierte
"el modelo respondio algo" en "el modelo respondio algo que el sistema puede
consumir".

Decision de diseno: ``extra="forbid"``. Un campo que el esquema no declara es un
sintoma, no un detalle: significa que el prompt y el contrato se desincronizaron.
Prefiero que falle el parseo y se dispare el retry con feedback antes que dejar
pasar una salida que nadie valido.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class Categoria(StrEnum):
    """Categorias de queja. Enum cerrado: es lo que hace verificable la salida.

    Un enum abierto ("la categoria que el modelo considere") no se puede evaluar
    contra verdad de terreno ni monitorear por distribucion. Cerrarlo es lo que
    permite tener scorers deterministas en lugar de solo opiniones de un juez.
    """

    TARIFA = "tarifa"
    CONDUCTOR = "conductor"
    LIMPIEZA = "limpieza"
    TIEMPO_DE_ESPERA = "tiempo_de_espera"
    APP = "app"
    OTRO = "otro"


#: Valores validos como lista de strings, para prompts y mensajes de error.
CATEGORIAS_VALIDAS: Final[tuple[str, ...]] = tuple(c.value for c in Categoria)

#: Limite de palabras del resumen. Es una propiedad testeable del sistema, no
#: una preferencia estetica: un resumen largo rompe la UI del agente de soporte.
MAX_PALABRAS_RESUMEN: Final[int] = 20

SEVERIDAD_MIN: Final[int] = 1
SEVERIDAD_MAX: Final[int] = 5


class ClasificacionQueja(BaseModel):
    """Salida estructurada del clasificador.

    Los cuatro campos existen porque los consume alguien: ``categoria`` enruta
    al equipo responsable, ``severidad`` prioriza la cola, ``requiere_reembolso``
    dispara un flujo financiero y ``resumen`` es lo que ve el agente humano.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    categoria: Categoria
    severidad: int = Field(ge=SEVERIDAD_MIN, le=SEVERIDAD_MAX)
    requiere_reembolso: bool
    resumen: str = Field(min_length=1)

    @field_validator("resumen")
    @classmethod
    def _validar_longitud_resumen(cls, valor: str) -> str:
        """Rechaza resumenes mas largos que el limite del contrato."""
        palabras = len(valor.split())
        if palabras > MAX_PALABRAS_RESUMEN:
            raise ValueError(
                f"el resumen tiene {palabras} palabras y el maximo es {MAX_PALABRAS_RESUMEN}"
            )
        return valor.strip()


class ErrorDeContrato(ValueError):
    """La salida del LLM no cumple el contrato.

    Existe como tipo propio para que el retry con feedback pueda distinguir
    "el modelo respondio mal" (reintentable, y el mensaje sirve de feedback) de
    "el proveedor fallo" (un error de infraestructura, que no se arregla
    reformulando el prompt). Confundir los dos hace que un 500 del proveedor se
    lea como un problema de prompt.
    """


#: Bloques ``` con o sin lenguaje. Es el envoltorio que mas aparece en la
#: practica: el modelo obedece el "devuelve JSON" y ademas lo formatea.
_CERCA_DE_CODIGO: Final[re.Pattern[str]] = re.compile(
    r"^\s*```(?:json|JSON)?\s*(?P<cuerpo>.*?)\s*```\s*$", re.DOTALL
)


def extraer_json(texto: str) -> str:
    """Aisla el JSON de una respuesta que puede venir envuelta o con prosa.

    No es un parser tolerante a todo: solo quita el envoltorio observable en la
    practica (bloques de codigo y texto antes/despues del objeto). Si hace falta
    mas magia que esto, el problema esta en el prompt o en no estar usando la
    salida estructurada nativa del proveedor, y taparlo aqui esconde la causa.
    """
    candidato = texto.strip()
    coincidencia = _CERCA_DE_CODIGO.match(candidato)
    if coincidencia:
        candidato = coincidencia.group("cuerpo").strip()
    inicio = candidato.find("{")
    fin = candidato.rfind("}")
    if inicio == -1 or fin == -1 or fin < inicio:
        raise ErrorDeContrato(
            f"la respuesta no contiene un objeto JSON; se recibio: {texto.strip()[:200]!r}"
        )
    return candidato[inicio : fin + 1]


def parsear_clasificacion(texto: str) -> ClasificacionQueja:
    """Convierte texto crudo del LLM en un ``ClasificacionQueja`` validado.

    Args:
        texto: respuesta cruda del proveedor.

    Returns:
        La clasificacion validada.

    Raises:
        ErrorDeContrato: con un mensaje **legible por un LLM**. Ese mensaje es la
            entrada del retry con feedback, asi que su calidad determina si el
            reintento converge o repite el mismo error.
    """
    crudo = extraer_json(texto)
    try:
        datos: Any = json.loads(crudo)
    except json.JSONDecodeError as exc:
        raise ErrorDeContrato(f"JSON malformado: {exc.msg} en la posicion {exc.pos}") from exc
    if not isinstance(datos, dict):
        raise ErrorDeContrato(f"se esperaba un objeto JSON y se recibio {type(datos).__name__}")
    try:
        return ClasificacionQueja.model_validate(datos)
    except ValidationError as exc:
        raise ErrorDeContrato(_mensaje_de_validacion(exc)) from exc


def _mensaje_de_validacion(exc: ValidationError) -> str:
    """Traduce un ``ValidationError`` a instrucciones accionables para el modelo.

    El mensaje por defecto de Pydantic es correcto pero verboso y habla de tipos
    de Python. Un LLM corrige mejor cuando se le dice el campo, que recibio y
    cual es el rango o el conjunto valido. Esto es prompt engineering aplicado al
    manejo de errores.
    """
    partes: list[str] = []
    for error in exc.errors():
        campo = ".".join(str(x) for x in error["loc"]) or "(raiz)"
        tipo = error["type"]
        if campo == "categoria":
            partes.append(
                f"campo 'categoria': valor invalido. Usa exactamente uno de: "
                f"{', '.join(CATEGORIAS_VALIDAS)}."
            )
        elif campo == "severidad":
            partes.append(
                f"campo 'severidad': debe ser un entero entre {SEVERIDAD_MIN} y "
                f"{SEVERIDAD_MAX}, sin comillas."
            )
        elif tipo == "extra_forbidden":
            partes.append(f"campo '{campo}': no esta en el contrato. Elimina los campos extra.")
        elif tipo == "missing":
            partes.append(f"campo '{campo}': falta y es obligatorio.")
        else:
            partes.append(f"campo '{campo}': {error['msg']}.")
    return " ".join(partes)
