"""El clasificador: prompt + LLM + validacion + retry con feedback, instrumentado.

Problema que resuelve
---------------------
Pedirle JSON a un LLM y hacer ``json.loads`` sobre la respuesta funciona el 90%
de las veces. El 10% restante es el que define si el sistema sirve en produccion,
y hay tres formas de tratarlo:

1. **Dejar que explote.** El usuario ve un 500 porque el modelo puso una coma de
   mas. Inaceptable y evitable.
2. **Parsear con tolerancia infinita.** Regex, arreglar comillas, adivinar la
   categoria mas parecida. Esconde el problema: el sistema deja de fallar y
   empieza a mentir, y el eval no lo nota porque la salida siempre parsea.
3. **Retry con feedback**, que es lo que hace este modulo: devolverle al modelo
   su propia salida y el mensaje de validacion, y pedirle que corrija. Es barato
   (una llamada mas), converge en la gran mayoria de los casos, y —clave— **deja
   registrado que hubo un reintento**, asi que el numero de reintentos se vuelve
   una metrica de calidad del prompt.

El reintento se acota (``max_intentos``) porque un bucle de reintentos contra un
modelo que no puede cumplir el contrato es una factura creciente sin final.

Sobre la alternativa nativa: los proveedores ofrecen salida estructurada forzada
(``response_format`` con un JSON Schema, o *structured outputs*). Cuando esta
disponible es preferible —el proveedor garantiza el esquema y el retry casi
desaparece— pero no reemplaza a la validacion local por tres razones: no todos
los modelos ni todos los gateways la soportan, garantiza la *forma* pero no la
*semantica* (nada impide ``severidad: 5`` en una queja trivial), y el sistema
queda sin defensa el dia que se cambia de modelo. La validacion local es la
frontera de confianza; la salida estructurada nativa es una optimizacion.

Instrumentacion
---------------
``@mlflow.trace`` en tres niveles: la funcion publica, la llamada al modelo y el
parseo. Los tres spans separados son lo que responde "donde se rompio": si el
span de parseo falla y el de la llamada no, el problema es el prompt; si falla el
de la llamada, es el proveedor. Un solo span alrededor de todo no distingue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import mlflow

from clasificador import prompts, tracing
from clasificador.esquema import ClasificacionQueja, ErrorDeContrato, parsear_clasificacion
from clasificador.proveedor import (
    TEMPERATURA_POR_DEFECTO,
    Proveedor,
    RespuestaLLM,
)

logger = logging.getLogger(__name__)

#: Intentos totales, no reintentos: 2 significa una llamada y una correccion.
#: Mas de 3 no ayuda: si el modelo no cumplio el contrato en dos correcciones, el
#: problema es el prompt o el modelo, y seguir pagando llamadas no lo arregla.
MAX_INTENTOS_POR_DEFECTO: int = 2

#: Instruccion del turno de correccion. Es un prompt, y por tanto tambien deberia
#: versionarse; se deja aqui y no en ``prompts/`` para no multiplicar artefactos
#: en una sesion de 4 horas. Si en produccion se toca, se versiona.
_PLANTILLA_FEEDBACK = (
    "Tu respuesta anterior no cumple el contrato de salida.\n"
    "Error de validacion: {error}\n"
    "Corrige y devuelve UNICAMENTE el objeto JSON valido, sin explicaciones."
)


@dataclass
class ResultadoClasificacion:
    """Salida del clasificador con todo lo que hace falta para evaluarla y facturarla.

    ``intentos``, ``tokens_*`` y ``huella_prompt`` no son adornos: son las
    columnas que el eval agrega y el reporte de costos suma. Si no viajan con el
    resultado hay que reconstruirlas despues leyendo trazas, y eso solo funciona
    si el servidor estaba levantado.
    """

    clasificacion: ClasificacionQueja | None
    exito: bool
    intentos: int
    tokens_entrada: int
    tokens_salida: int
    modelo: str
    proveedor: str
    etiqueta_prompt: str
    huella_prompt: str
    #: Ultimo texto crudo recibido. Es lo primero que se mira cuando algo falla.
    texto_crudo: str = ""
    #: Errores de contrato de cada intento, en orden.
    errores: list[str] = field(default_factory=list)

    @property
    def tokens_totales(self) -> int:
        return self.tokens_entrada + self.tokens_salida

    def como_dict(self) -> dict[str, Any]:
        """Forma plana para escribir a JSONL o construir un DataFrame."""
        salida: dict[str, Any] = {
            "exito": self.exito,
            "intentos": self.intentos,
            "tokens_entrada": self.tokens_entrada,
            "tokens_salida": self.tokens_salida,
            "modelo": self.modelo,
            "proveedor": self.proveedor,
            "etiqueta_prompt": self.etiqueta_prompt,
            "huella_prompt": self.huella_prompt,
            "errores": list(self.errores),
        }
        if self.clasificacion is not None:
            salida.update(self.clasificacion.model_dump(mode="json"))
        return salida


@mlflow.trace(name="llamar_modelo", span_type="LLM")
def _llamar_modelo(
    proveedor: Proveedor,
    sistema: str,
    mensajes: list[dict[str, str]],
    temperatura: float,
) -> RespuestaLLM:
    """Span propio para la llamada al modelo.

    Se envuelve incluso teniendo ``mlflow.openai.autolog()`` disponible: el
    autolog solo aparece con el SDK real, y la traza debe verse igual corriendo
    con el fake. Si la instrumentacion cambia de forma segun el proveedor, el
    material de clase deja de ser el mismo material.
    """
    return proveedor.completar(sistema, mensajes, temperatura=temperatura)


@mlflow.trace(name="parsear_salida", span_type="PARSER")
def _parsear(texto: str) -> ClasificacionQueja:
    """Span propio para el parseo, para separarlo del fallo del modelo."""
    return parsear_clasificacion(texto)


def clasificar(
    texto_queja: str,
    *,
    proveedor: Proveedor,
    plantilla: prompts.Plantilla | None = None,
    max_intentos: int = MAX_INTENTOS_POR_DEFECTO,
    temperatura: float = TEMPERATURA_POR_DEFECTO,
) -> ResultadoClasificacion:
    """Punto de entrada publico. Asegura el tracing y delega en la funcion trazada.

    Es una envoltura de tres lineas y no un capricho: ``@mlflow.trace`` **abre el
    span al invocar la funcion**, antes de ejecutar su cuerpo. Si la configuracion
    del tracing se hiciera dentro del cuerpo, el span exterior ya se habria creado
    con la configuracion global de MLflow, que es justo lo que hay que evitar (ver
    ``tracing.asegurar_configurado``: sin esto, un notebook con
    ``MLFLOW_TRACKING_URI`` apuntando a un servidor caido se cuelga).

    La leccion generalizable: la configuracion de la telemetria tiene que ocurrir
    en una costura **por fuera** de lo instrumentado. Un decorador no se puede
    configurar desde dentro de la funcion que decora.
    """
    tracing.asegurar_configurado()
    return _clasificar(
        texto_queja,
        proveedor=proveedor,
        plantilla=plantilla,
        max_intentos=max_intentos,
        temperatura=temperatura,
    )


@mlflow.trace(name="clasificar_queja", span_type="CHAIN")
def _clasificar(
    texto_queja: str,
    *,
    proveedor: Proveedor,
    plantilla: prompts.Plantilla | None = None,
    max_intentos: int = MAX_INTENTOS_POR_DEFECTO,
    temperatura: float = TEMPERATURA_POR_DEFECTO,
) -> ResultadoClasificacion:
    """Clasifica una queja y devuelve la salida validada o el registro del fallo.

    No lanza excepcion cuando el modelo no logra cumplir el contrato: devuelve
    ``exito=False`` con los errores. La razon es que quien llama casi siempre esta
    procesando un lote (un eval de 40 casos, una cola de tickets) y un caso malo
    no debe abortar el lote. La excepcion se reserva para los fallos de
    infraestructura, que si son motivo de detenerse.

    Args:
        texto_queja: el texto libre del usuario.
        proveedor: implementacion de ``Proveedor``. Inyectado, nunca construido
            aqui: es lo que hace testeable esta funcion.
        plantilla: prompt a usar. ``None`` carga ``v2`` del disco.
        max_intentos: llamadas totales al modelo, incluyendo correcciones.
        temperatura: 0 por defecto para una tarea de clasificacion.

    Returns:
        ``ResultadoClasificacion``, con exito o con el rastro del fallo.
    """
    if max_intentos < 1:
        raise ValueError("max_intentos debe ser >= 1")

    plantilla = plantilla or prompts.cargar_local("v2")
    sistema = plantilla.renderizar(**prompts.contexto_por_defecto())

    mensajes: list[dict[str, str]] = [{"role": "user", "content": texto_queja}]
    resultado = ResultadoClasificacion(
        clasificacion=None,
        exito=False,
        intentos=0,
        tokens_entrada=0,
        tokens_salida=0,
        modelo=getattr(proveedor, "modelo", "desconocido"),
        proveedor=getattr(proveedor, "nombre", type(proveedor).__name__),
        etiqueta_prompt=plantilla.etiqueta,
        huella_prompt=plantilla.huella,
    )

    for intento in range(1, max_intentos + 1):
        resultado.intentos = intento
        respuesta = _llamar_modelo(proveedor, sistema, mensajes, temperatura)
        # Los tokens se ACUMULAN entre intentos. Contar solo el ultimo intento
        # subestima el costo real justo en los casos problematicos, que son los
        # que hay que ver en el reporte.
        resultado.tokens_entrada += respuesta.tokens_entrada
        resultado.tokens_salida += respuesta.tokens_salida
        resultado.modelo = respuesta.modelo
        resultado.texto_crudo = respuesta.texto

        try:
            resultado.clasificacion = _parsear(respuesta.texto)
            resultado.exito = True
            break
        except ErrorDeContrato as exc:
            mensaje = str(exc)
            resultado.errores.append(mensaje)
            logger.info("Intento %d/%d fallo el contrato: %s", intento, max_intentos, mensaje)
            if intento == max_intentos:
                break
            # Retry con feedback: se conserva la respuesta del modelo como turno
            # de assistant y se agrega el error como turno de usuario. Sin el
            # turno de assistant el modelo no sabe QUE esta corrigiendo y suele
            # repetir el mismo error.
            mensajes = [
                *mensajes,
                {"role": "assistant", "content": respuesta.texto},
                {"role": "user", "content": _PLANTILLA_FEEDBACK.format(error=mensaje)},
            ]

    tracing.anotar_traza(
        exito=resultado.exito,
        intentos=resultado.intentos,
        prompt=plantilla.etiqueta,
        huella_prompt=plantilla.huella,
        modelo=resultado.modelo,
        proveedor=resultado.proveedor,
        tokens_totales=resultado.tokens_totales,
    )
    return resultado


def clasificar_lote(
    textos: list[str],
    *,
    proveedor: Proveedor,
    plantilla: prompts.Plantilla | None = None,
    max_intentos: int = MAX_INTENTOS_POR_DEFECTO,
) -> list[ResultadoClasificacion]:
    """Clasifica varias quejas en serie, sin abortar por un caso malo.

    En serie a proposito: el paralelismo introduce rate limits, reintentos
    superpuestos y trazas entrelazadas, y ninguno de los tres aporta al objetivo
    de la sesion. En produccion se paraleliza con un limite de concurrencia
    alineado con la cuota del proveedor, no con un pool sin tope.
    """
    return [
        clasificar(
            texto,
            proveedor=proveedor,
            plantilla=plantilla,
            max_intentos=max_intentos,
        )
        for texto in textos
    ]
