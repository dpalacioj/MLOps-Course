"""Abstraccion sobre el proveedor de LLM, con implementaciones inyectables.

Problema que resuelve
---------------------
Tres problemas distintos, y por eso hay tres implementaciones:

1. **No poder dar clase sin API key ni sin red.** Si el material solo funciona
   con una cuenta de pago activa, la mitad del grupo no lo corre. ``ProveedorFake``
   es determinista y offline: los tests y la clase funcionan siempre.
2. **No poder testear.** Un test que llama a un LLM real no es un test: es lento,
   cuesta dinero y su resultado cambia entre ejecuciones. La frontera de red
   tiene que ser un parametro, no un ``import`` enterrado en la logica.
3. **No saber que se envio.** Cuando la salida es mala, la primera pregunta es
   "que texto recibio realmente el modelo". ``ProveedorEco`` responde eso sin
   gastar un token.

Decision de diseno: el ``import`` de ``openai`` es **tardio**, dentro del metodo.
El grupo ``llmops`` de ``pyproject.toml`` es un extra opcional, asi que este
modulo tiene que importarse y sus tests tienen que pasar en un entorno donde
``openai`` no esta instalado. Un ``import openai`` en la cabecera convertiria un
extra opcional en una dependencia obligatoria de toda la suite.

Alternativas consideradas para la capa de acceso
-----------------------------------------------
- SDK del proveedor directo (``openai``): menos piezas, mas lock-in.
- ``litellm`` como libreria: una firma para muchos proveedores, a costa de una
  dependencia mas y de una capa de traduccion que puede quedarse atras.
- ``litellm`` como **gateway** HTTP (ver ``gateway/``): la app sigue hablando el
  protocolo de OpenAI y el cambio de proveedor, los budgets y los fallbacks son
  configuracion del gateway, no codigo de la app. Es lo que se recomienda aqui.

Las tres se atienden con la misma clase ``ProveedorOpenAI`` porque las tres
hablan el mismo protocolo: lo unico que cambia es ``base_url``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from clasificador.esquema import Categoria

logger = logging.getLogger(__name__)

#: Modelo por defecto. Se declara aqui y no en cada llamada para que aparezca
#: una sola vez en los params de MLflow y en la calculadora de costos.
MODELO_POR_DEFECTO: Final[str] = "gpt-4o-mini"

#: Temperatura por defecto: 0. En una tarea de clasificacion con salida
#: estructurada, la creatividad no es una virtud. Es tambien lo unico que acerca
#: la ejecucion a ser reproducible, aunque no la garantiza: con el mismo prompt y
#: temperatura 0 un endpoint gestionado puede devolver salidas distintas
#: (batching en GPU, cambios de version del modelo detras del mismo alias).
TEMPERATURA_POR_DEFECTO: Final[float] = 0.0


@dataclass(frozen=True)
class RespuestaLLM:
    """Lo que devuelve un proveedor, con la contabilidad incluida.

    Los tokens viajan con la respuesta a proposito. Si el costo se calcula en
    otro lado a partir del texto, se calcula mal: el proveedor cobra por los
    tokens que **el** conto, incluyendo los del prompt de sistema, los mensajes
    de reintento y el overhead del formato de chat.
    """

    texto: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    #: Metadatos libres (id de request, motivo de terminacion, latencia).
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens_totales(self) -> int:
        return self.tokens_entrada + self.tokens_salida


@runtime_checkable
class Proveedor(Protocol):
    """Contrato minimo de un proveedor de LLM.

    Es un ``Protocol`` y no una clase base abstracta porque no se necesita
    herencia: se necesita que cualquier objeto con este metodo sirva. Eso permite
    que un test pase una funcion envuelta en una clase de tres lineas sin
    importar nada de este modulo.
    """

    nombre: str
    modelo: str

    def completar(
        self,
        sistema: str,
        mensajes: list[dict[str, str]],
        *,
        temperatura: float = TEMPERATURA_POR_DEFECTO,
    ) -> RespuestaLLM:
        """Devuelve la respuesta del modelo a una conversacion.

        Se recibe la lista completa de mensajes y no un solo string porque el
        retry con feedback necesita mandar el turno anterior y el error. Aplanar
        eso a un unico string pierde la estructura que el modelo usa para saber
        que esta corrigiendo su propia respuesta.
        """
        ...


# =============================================================================
# Conteo de tokens
# =============================================================================
def contar_tokens(texto: str, modelo: str = MODELO_POR_DEFECTO) -> int:
    """Cuenta tokens con ``tiktoken`` si esta instalado, y estima si no.

    La estimacion (4 caracteres por token) es suficiente para dimensionar costos
    con un orden de magnitud correcto, y **no** es suficiente para facturar. La
    diferencia importa: en espanol y con nombres propios la estimacion se queda
    corta respecto al conteo real.

    Regla operativa: para reportar costos reales se usan los tokens que devuelve
    el proveedor en ``usage``, no este conteo. Este sirve para estimar *antes* de
    llamar (por ejemplo, para rechazar un input demasiado largo).
    """
    try:
        import tiktoken
    except ImportError:
        logger.debug("tiktoken no instalado; se usa la estimacion de 4 caracteres por token")
        return max(1, len(texto) // 4)
    try:
        codificador = tiktoken.encoding_for_model(modelo)
    except KeyError:
        codificador = tiktoken.get_encoding("o200k_base")
    return len(codificador.encode(texto))


# =============================================================================
# ProveedorFake — determinista, offline
# =============================================================================
#: Reglas de palabra clave por categoria. El orden importa: la primera categoria
#: con alguna coincidencia gana.
#:
#: Nota didactica: este es a proposito un clasificador **mediocre**. Si el fake
#: acertara siempre, el eval marcaria 1.00 y no ensenaria nada; con un fake
#: imperfecto los scorers producen numeros que hay que interpretar, que es el
#: objetivo de la sesion. Los aciertos y los fallos son ambos material de clase.
_REGLAS: Final[tuple[tuple[Categoria, tuple[str, ...]], ...]] = (
    (
        Categoria.TARIFA,
        ("cobr", "tarifa", "precio", "caro", "peaje", "recargo", "factur", "cargo", "cupon"),
    ),
    (
        Categoria.LIMPIEZA,
        ("sucio", "sucia", "olor", "basura", "mancha", "limpi", "hediondo", "vomit"),
    ),
    (
        Categoria.CONDUCTOR,
        ("conductor", "chofer", "grosero", "maltrat", "agresiv", "gritó", "grito", "insult"),
    ),
    (
        Categoria.TIEMPO_DE_ESPERA,
        ("esper", "tard", "demor", "no llegó", "no llego", "cancel"),
    ),
    (
        Categoria.APP,
        ("app", "aplicaci", "gps", "no carga", "se cerró", "se cerro", "pantalla", "actualiz"),
    ),
)

#: Palabras que suben la severidad. La escala es una convencion del negocio y
#: esta escrita en ``rubricas/severidad.md``: si vive solo en el codigo, cada
#: anotador la interpreta distinto y el dataset deja de ser consistente.
_AGRAVANTES: Final[tuple[str, ...]] = (
    "peligro",
    "accidente",
    "borracho",
    "acos",
    "amenaz",
    "golpe",
    "robo",
    "arma",
    "menor",
)

#: Palabras que sugieren dinero mal cobrado y por tanto reembolso.
_INDICIOS_REEMBOLSO: Final[tuple[str, ...]] = (
    "cobr",
    "doble",
    "reembols",
    "devuelv",
    "devolu",
    "no me llevó",
    "no me llevo",
    "nunca llegó",
    "nunca llego",
)

_ESPACIOS: Final[re.Pattern[str]] = re.compile(r"\s+")


class ProveedorFake:
    """Proveedor determinista basado en reglas. Sin red, sin API key, sin costo.

    Para que sirve
    --------------
    - Correr los tests en CI de un fork sin secretos configurados.
    - Dar la clase cuando la red del aula falla o la cuota se agoto.
    - Tener una **linea base** honesta: si el LLM no supera a un puñado de
      palabras clave, el LLM no es la herramienta correcta para esta tarea. Esa
      comparacion es el equivalente al ``DummyRegressor`` de la sesion 3, y se
      omite mucho mas de lo que se deberia.

    Para que NO sirve: para medir la calidad del sistema real. Un eval corrido
    contra el fake mide el fake.
    """

    def __init__(
        self,
        *,
        modelo: str = "fake-reglas-v1",
        fallos_iniciales: int = 0,
        salida_de_fallo: str = "no soy un JSON",
    ) -> None:
        """
        Args:
            fallos_iniciales: cuantas primeras llamadas devuelven una salida que
                no cumple el contrato. Sirve para ejercitar el retry con
                feedback de forma deterministica en un test.
            salida_de_fallo: el texto invalido que se devuelve en esas llamadas.
        """
        self.nombre = "fake"
        self.modelo = modelo
        self.fallos_iniciales = fallos_iniciales
        self.salida_de_fallo = salida_de_fallo
        #: Contador de llamadas. Un test lo lee para afirmar que hubo reintento.
        self.llamadas = 0

    def completar(
        self,
        sistema: str,
        mensajes: list[dict[str, str]],
        *,
        temperatura: float = TEMPERATURA_POR_DEFECTO,
    ) -> RespuestaLLM:
        self.llamadas += 1
        entrada = sistema + "\n" + "\n".join(m.get("content", "") for m in mensajes)
        tokens_entrada = contar_tokens(entrada, self.modelo)

        if self.llamadas <= self.fallos_iniciales:
            return RespuestaLLM(
                texto=self.salida_de_fallo,
                modelo=self.modelo,
                tokens_entrada=tokens_entrada,
                tokens_salida=contar_tokens(self.salida_de_fallo, self.modelo),
                extra={"simulado": True, "intento_fallido": self.llamadas},
            )

        queja = self._ultimo_texto_de_usuario(mensajes)
        # El fake LEE el prompt de sistema para decidir que juego de reglas usa.
        # Ver la nota en 'MARCADOR_RUBRICA': es una simulacion de sensibilidad al
        # prompt, no una medicion de ella.
        con_rubrica = MARCADOR_RUBRICA in sistema
        salida = json.dumps(
            clasificar_por_reglas(queja, con_rubrica=con_rubrica), ensure_ascii=False
        )
        return RespuestaLLM(
            texto=salida,
            modelo=self.modelo,
            tokens_entrada=tokens_entrada,
            tokens_salida=contar_tokens(salida, self.modelo),
            extra={"simulado": True},
        )

    @staticmethod
    def _ultimo_texto_de_usuario(mensajes: list[dict[str, str]]) -> str:
        """El primer mensaje de usuario es la queja; los siguientes son feedback.

        Se toma el **primero** y no el ultimo a proposito: en un reintento el
        ultimo turno de usuario es el mensaje de error de validacion, no la
        queja. Clasificar el mensaje de error es un bug facil de escribir y
        dificil de ver.
        """
        for mensaje in mensajes:
            if mensaje.get("role") == "user":
                return mensaje.get("content", "")
        return ""


#: Fragmento que solo aparece en ``prompts/v2-rubrica.txt``. El fake lo busca en el
#: prompt de sistema para decidir si aplica el juego de reglas grueso o el fino.
#:
#: ADVERTENCIA DIDACTICA, y hay que decirla en clase en voz alta: esto **simula**
#: que un prompt mejor produce salidas mejores. No lo demuestra. Un LLM real puede
#: perfectamente ignorar la rubrica, o empeorar con ella (un prompt de sistema
#: largo diluye la atencion sobre la instruccion principal: es un resultado
#: frecuente, no una rareza).
#:
#: Existe por una razon operativa concreta: sin esto, en modo fake las dos
#: versiones del prompt puntuan **exactamente igual**, la tabla comparativa sale
#: con deltas en cero y no se puede practicar el flujo de comparar versiones sin
#: API key. El precio de la simulacion es que el numero no dice nada sobre
#: prompts reales, y ese precio hay que cobrarlo explicitamente: el eval reporta
#: siempre el proveedor, y ``proveedor=fake`` significa "esta comparacion no mide
#: el sistema real".
MARCADOR_RUBRICA: Final[str] = "Como asignar la severidad"

#: Reglas finas: el prompt v2 pide elegir el motivo PRINCIPAL, no el primero que
#: aparece. Se implementa puntuando cada categoria y quedandose con la de mayor
#: puntaje, en lugar de cortar en la primera coincidencia.
#:
#: El peso importa: el sustantivo "conductor" aparece en casi cualquier queja
#: ("el conductor fue amable", "el conductor cancelo") y no indica que la queja
#: sea SOBRE el conductor. Lo que lo indica es la conducta. Por eso los
#: sustantivos pesan 0 y las conductas pesan 2. Ese es exactamente el error que
#: la regla gruesa comete en 7 de los 36 casos.
#:
#: SEGUNDA ADVERTENCIA, y es la mas importante de este archivo: estas reglas se
#: escribieron **mirando los 36 casos del dataset de evals**. Eso es sobreajuste al
#: holdout, el pecado exacto contra el que advierte ``rubricas/severidad.md`` y el
#: que ``taxi.config.PARTICION_TEST`` existe para evitar. Por eso el fake saca
#: ~0.94 de exactitud de categoria: no porque las reglas sean buenas, sino porque
#: se ajustaron a la respuesta.
#:
#: Se deja asi a proposito y se declara, porque es un anti-patron que en clase se
#: puede senalar con el dedo: cualquiera puede llegar a 0.94 en un eval si itera
#: contra el eval. La forma correcta —conjunto de desarrollo para iterar, este
#: como holdout intacto— esta descrita en ``comparar_prompts.py``. Si un
#: estudiante llega a un numero asi con su propio prompt, la primera pregunta es
#: cuantas veces lo corrio contra estos mismos 36 casos.
_PESOS: Final[dict[Categoria, tuple[tuple[str, int], ...]]] = {
    Categoria.TARIFA: (
        ("cobr", 2),
        ("tarifa", 2),
        ("recargo", 2),
        ("peaje", 2),
        ("cupon", 2),
        ("factur", 2),
        ("cargo", 2),
        ("precio", 1),
        ("caro", 1),
        ("descont", 2),
        ("abuso", 1),
        ("mil", 1),
    ),
    Categoria.LIMPIEZA: (
        ("sucio", 2),
        ("sucia", 2),
        ("olor", 2),
        ("olia horrible", 2),
        ("basura", 2),
        ("mancha", 2),
        ("limpi", 2),
        ("barro", 2),
        ("mojado", 2),
        ("envoltura", 2),
        ("lata vacia", 2),
        ("cigarrillo", 2),
        ("ensucie", 2),
        ("vomit", 2),
    ),
    Categoria.CONDUCTOR: (
        # Sustantivos: peso 0. Nombrar al conductor no es quejarse de el.
        ("conductor", 0),
        ("chofer", 0),
        # Conductas: peso 2.
        ("grosero", 2),
        ("maltrat", 2),
        ("agresiv", 2),
        ("grito", 2),
        ("gritó", 2),
        ("insult", 2),
        ("me trato mal", 2),
        ("no quiso llevar", 2),
        ("se nego", 2),
        ("hablando por celular", 2),
        ("semaforo", 2),
        ("licor", 2),
        ("eses", 2),
        ("zona escolar", 2),
        ("siguio", 2),
        ("efectivo por fuera", 2),
        ("reggaeton", 2),
        ("volumen", 2),
        ("velocidad", 2),
        ("temerari", 2),
    ),
    Categoria.TIEMPO_DE_ESPERA: (
        ("esper", 2),
        ("tard", 2),
        ("demor", 2),
        ("cancel", 2),
        ("nunca llego", 2),
        ("nunca llegó", 2),
        ("no llego", 2),
        ("no llegó", 2),
        ("minutos despues", 2),
    ),
    Categoria.APP: (
        ("app", 2),
        ("aplicaci", 2),
        ("gps", 2),
        ("no carga", 2),
        ("se cierra", 2),
        ("se cerro", 2),
        ("se cerró", 2),
        ("pantalla", 2),
        ("actualizacion", 2),
        ("notificacion", 1),
        ("error desconocido", 2),
        ("agregar mi tarjeta", 2),
        ("direcciones guardadas", 2),
        ("foto", 1),
    ),
}

#: Señales de que la queja es sobre el estado fisico o el equipamiento del
#: vehiculo, o sobre accesibilidad. La rubrica las manda a 'otro' y la regla
#: gruesa no las conoce.
_SENALES_OTRO: Final[tuple[str, ...]] = (
    "aire acondicionado",
    "cinturon",
    "silla de ruedas",
    "maleta",
    "olvid",
    "computador",
)

#: Señales de comentario positivo. Sin esto, una felicitacion se clasifica como
#: queja grave, que es el fallo mas embarazoso posible en produccion.
_SENALES_POSITIVAS: Final[tuple[str, ...]] = (
    "excelente",
    "muy amable",
    "gracias",
    "felicit",
    "todo bien",
)

#: Palabras que llevan la severidad al maximo por riesgo a la integridad.
_RIESGO_GRAVE: Final[tuple[str, ...]] = (
    "matabamos",
    "semaforos en rojo",
    "zona escolar",
    "licor",
    "eses",
    "siguio",
    "tengo miedo",
    "acos",
    "amenaz",
    "arma",
    "golpe",
)

#: Palabras que indican que el usuario perdio un compromiso concreto (nivel 3).
_COMPROMISO_PERDIDO: Final[tuple[str, ...]] = (
    "reunion",
    "reunión",
    "entrevista",
    "cliente",
    "vuelo",
    "cita",
)


def clasificar_por_reglas(texto: str, *, con_rubrica: bool = False) -> dict[str, Any]:
    """Linea base por palabras clave. Devuelve un dict que cumple el contrato.

    Se expone como funcion publica porque tambien es la **linea base** con la que
    se compara el LLM en el reporte del eval, no solo el motor del fake. Si el LLM
    no supera a esto, el LLM no es la herramienta correcta para la tarea.

    Args:
        con_rubrica: aplica el juego de reglas fino, que emula lo que la rubrica
            del prompt v2 le pide al modelo (elegir el motivo principal, separar
            severidad de reembolso, reconocer los comentarios positivos).

    La longitud de este codigo es en si misma un argumento de la sesion: son unas
    cien lineas de reglas para 36 casos, no generalizan a una queja escrita de
    otra forma, y hay que reescribirlas cuando el negocio agrega una categoria.
    Eso es precisamente lo que un LLM resuelve bien. Y la razon por la que la
    linea base sigue siendo obligatoria es la inversa: si estas cien lineas
    empatan con el LLM, el LLM esta costando dinero por nada.
    """
    minusculas = texto.lower()
    if not con_rubrica:
        return _reglas_gruesas(minusculas, texto)
    return _reglas_finas(minusculas, texto)


def _reglas_gruesas(minusculas: str, original: str) -> dict[str, Any]:
    """Primera coincidencia gana. Es lo que produce el prompt v1."""
    categoria = Categoria.OTRO
    for candidata, claves in _REGLAS:
        if any(clave in minusculas for clave in claves):
            categoria = candidata
            break

    base = {
        Categoria.CONDUCTOR: 4,
        Categoria.TARIFA: 3,
        Categoria.LIMPIEZA: 2,
        Categoria.TIEMPO_DE_ESPERA: 2,
        Categoria.APP: 2,
        Categoria.OTRO: 2,
    }[categoria]
    agravantes = sum(1 for clave in _AGRAVANTES if clave in minusculas)
    return {
        "categoria": categoria.value,
        "severidad": max(1, min(5, base + (2 if agravantes else 0))),
        "requiere_reembolso": any(clave in minusculas for clave in _INDICIOS_REEMBOLSO),
        "resumen": _resumir(original),
    }


def _reglas_finas(minusculas: str, original: str) -> dict[str, Any]:
    """Motivo principal por puntaje, con las reglas de la rubrica."""
    positiva = any(clave in minusculas for clave in _SENALES_POSITIVAS)

    puntajes: dict[Categoria, int] = {}
    for categoria, pesos in _PESOS.items():
        puntajes[categoria] = sum(peso for clave, peso in pesos if clave in minusculas)

    reclama_dinero = any(clave in minusculas for clave in _INDICIOS_REEMBOLSO)
    # Regla de desempate de la rubrica: si hay espera Y reclamo de dinero, gana
    # tarifa, porque lo que el usuario pide es el reembolso.
    if reclama_dinero and puntajes[Categoria.TARIFA] > 0:
        puntajes[Categoria.TARIFA] += 3

    if any(clave in minusculas for clave in _SENALES_OTRO) or positiva:
        elegida = Categoria.OTRO
    else:
        mejor = max(puntajes.items(), key=lambda par: par[1])
        elegida = mejor[0] if mejor[1] > 0 else Categoria.OTRO

    severidad = _severidad_fina(minusculas, elegida, positiva=positiva)
    return {
        "categoria": elegida.value,
        "severidad": severidad,
        "requiere_reembolso": reclama_dinero and not positiva,
        "resumen": _resumir(original),
    }


def _severidad_fina(minusculas: str, categoria: Categoria, *, positiva: bool) -> int:
    """Severidad segun las anclas de ``rubricas/severidad.md``."""
    if positiva:
        return 1
    if any(clave in minusculas for clave in _RIESGO_GRAVE):
        return 5
    # Nivel 4: impacto grave sin riesgo a la integridad.
    graves = (
        "me grito",
        "gritó",
        "me trato muy mal",
        "no quiso llev",
        "se nego",
        "silla de ruedas",
        "cinturon",
        "olvid",
        "computador",
        "nunca hice",
        "efectivo por fuera",
        "no me llev",
    )
    if any(clave in minusculas for clave in graves):
        return 4
    # Monto significativo: cifras de seis digitos o "120 mil" y similares.
    if re.search(r"\b(?:1[0-9]{2}|[2-9][0-9]{2})\s*mil\b", minusculas):
        return 4
    if any(clave in minusculas for clave in _COMPROMISO_PERDIDO):
        return 3
    # Nivel 3: el servicio no cumplio lo prometido, o hay disputa de monto con
    # una discrepancia explicita.
    tres = (
        "no me explico",
        "nadie me explico",
        "sin explicaci",
        "no me encontro",
        "llevo tres dias",
        "no logro",
        "distinto al de la foto",
        "ensucie",
        "no cargo",
        "todavia no me llega",
        "tres horas",
        "otros 20 minutos",
    )
    if any(clave in minusculas for clave in tres):
        return 3
    if "un poco mas" in minusculas or "por lo demas todo bien" in minusculas:
        return 1
    return 2


def _resumir(texto: str, max_palabras: int = 12) -> str:
    """Resumen extractivo: las primeras palabras, normalizadas.

    Es deliberadamente tonto. Un resumen de verdad necesita un modelo; lo que
    hace falta aqui es una cadena que **cumpla el contrato** para que el resto de
    la tuberia se pueda ejercitar sin red.
    """
    limpio = _ESPACIOS.sub(" ", texto).strip()
    palabras = limpio.split(" ")[:max_palabras]
    return " ".join(palabras) if palabras else "queja sin texto"


# =============================================================================
# ProveedorEco — depuracion
# =============================================================================
class ProveedorEco:
    """Devuelve el prompt que se le paso, en lugar de llamar a un modelo.

    Problema que resuelve: cuando la salida es mala, la causa mas frecuente no es
    el modelo sino el prompt renderizado — una variable que quedo sin sustituir,
    un ``{{contexto}}`` vacio, la queja truncada, dos mensajes de sistema
    pegados. Verlo tal cual se envio toma diez segundos con esto y bastante mas
    leyendo logs.

    No cumple el contrato de salida a proposito: si se usa por error dentro del
    clasificador, el parseo falla de inmediato en lugar de producir un resultado
    que parece valido.
    """

    def __init__(self, *, modelo: str = "eco") -> None:
        self.nombre = "eco"
        self.modelo = modelo

    def completar(
        self,
        sistema: str,
        mensajes: list[dict[str, str]],
        *,
        temperatura: float = TEMPERATURA_POR_DEFECTO,
    ) -> RespuestaLLM:
        lineas = [f"[system] {sistema}"]
        lineas += [f"[{m.get('role', '?')}] {m.get('content', '')}" for m in mensajes]
        texto = "\n".join(lineas)
        return RespuestaLLM(
            texto=texto,
            modelo=self.modelo,
            tokens_entrada=contar_tokens(texto, self.modelo),
            tokens_salida=0,
            extra={"eco": True, "temperatura": temperatura},
        )


# =============================================================================
# ProveedorOpenAI — el real
# =============================================================================
class ProveedorOpenAI:
    """Proveedor real via protocolo OpenAI: SDK directo, gateway o LiteLLM.

    El ``import`` es tardio: ``openai`` vive en el extra ``llmops`` y este modulo
    debe importarse en un entorno que no lo tenga.

    Sobre versiones del SDK: la serie **3.x** es la vigente. Muchos tutoriales
    todavia muestran ``openai.ChatCompletion.create(...)``, que es de la era 0.x
    y no existe; y bastantes snippets de la era 1.x circulan como si fueran
    actuales. La forma correcta hoy es instanciar un cliente y llamar a
    ``client.chat.completions.create(...)``. Copiar un snippet viejo es la causa
    numero uno de los ``AttributeError`` de la primera hora de clase.
    """

    def __init__(
        self,
        *,
        modelo: str = MODELO_POR_DEFECTO,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_reintentos: int = 2,
    ) -> None:
        """
        Args:
            base_url: apuntar aqui al gateway de LiteLLM para no cambiar codigo
                al cambiar de proveedor. ``None`` usa el endpoint por defecto del
                SDK.
            api_key: si es ``None`` se lee de ``OPENAI_API_KEY``. Nunca se
                escribe en logs ni en los params de MLflow.
            timeout: un LLM lento es indistinguible de uno caido si no hay
                timeout. El default del SDK es generoso para un servicio
                interactivo.
        """
        self.nombre = "openai"
        self.modelo = modelo
        self._base_url = base_url or os.getenv("LLMOPS_BASE_URL") or None
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._timeout = timeout
        self._max_reintentos = max_reintentos
        self._cliente: Any | None = None

    def _obtener_cliente(self) -> Any:
        """Instancia el cliente del SDK de forma perezosa."""
        if self._cliente is not None:
            return self._cliente
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depende del extra
            raise RuntimeError(
                "El proveedor real necesita el extra 'llmops'. Instalalo con:\n"
                "    uv sync --extra llmops\n"
                "O corre la sesion con el fake:  export LLMOPS_PROVEEDOR=fake"
            ) from exc
        if not self._api_key and not self._base_url:
            raise RuntimeError(
                "Falta OPENAI_API_KEY y no hay LLMOPS_BASE_URL (gateway). "
                "Usa LLMOPS_PROVEEDOR=fake para trabajar sin credenciales."
            )
        self._cliente = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
            max_retries=self._max_reintentos,
        )
        return self._cliente

    def completar(
        self,
        sistema: str,
        mensajes: list[dict[str, str]],
        *,
        temperatura: float = TEMPERATURA_POR_DEFECTO,
    ) -> RespuestaLLM:
        cliente = self._obtener_cliente()
        conversacion: list[dict[str, str]] = [{"role": "system", "content": sistema}, *mensajes]
        respuesta = cliente.chat.completions.create(
            model=self.modelo,
            messages=conversacion,
            temperature=temperatura,
            response_format={"type": "json_object"},
        )
        uso = getattr(respuesta, "usage", None)
        contenido = respuesta.choices[0].message.content or ""
        return RespuestaLLM(
            texto=contenido,
            modelo=getattr(respuesta, "model", self.modelo),
            # El conteo del proveedor manda. Si falta, se estima y se deja
            # constancia en 'extra' para que el reporte de costos no presente una
            # estimacion como si fuera una medicion.
            tokens_entrada=int(getattr(uso, "prompt_tokens", 0) or contar_tokens(sistema)),
            tokens_salida=int(getattr(uso, "completion_tokens", 0) or contar_tokens(contenido)),
            extra={
                "finish_reason": respuesta.choices[0].finish_reason,
                "tokens_medidos": uso is not None,
                "via_gateway": self._base_url is not None,
            },
        )


# =============================================================================
# Factory
# =============================================================================
def crear_proveedor(nombre: str | None = None) -> Proveedor:
    """Devuelve el proveedor indicado por ``LLMOPS_PROVEEDOR``.

    Politica de defaults, y es deliberada: **si no hay credenciales, se usa el
    fake**. La alternativa —fallar con "falta la API key"— deja al estudiante
    bloqueado en el minuto tres de la sesion. Con el fake, todo el material
    corre y lo unico que cambia es la calidad de las respuestas.

    El precio de este default es que se puede correr un eval contra el fake sin
    darse cuenta y creer que se midio el sistema real. Por eso el nombre del
    proveedor y el del modelo se registran en cada run y aparecen en el reporte:
    un numero de eval sin saber que modelo lo produjo no significa nada.

    Args:
        nombre: ``"fake"``, ``"eco"`` u ``"openai"``. ``None`` lee el entorno.
    """
    elegido = (nombre or os.getenv("LLMOPS_PROVEEDOR") or "").strip().lower()
    if not elegido:
        tiene_credenciales = bool(os.getenv("OPENAI_API_KEY") or os.getenv("LLMOPS_BASE_URL"))
        elegido = "openai" if tiene_credenciales else "fake"
        logger.info("LLMOPS_PROVEEDOR no definido; se usa '%s'", elegido)

    if elegido == "fake":
        return ProveedorFake()
    if elegido == "eco":
        return ProveedorEco()
    if elegido == "openai":
        return ProveedorOpenAI(modelo=os.getenv("LLMOPS_MODELO", MODELO_POR_DEFECTO))
    raise ValueError(f"proveedor desconocido: {elegido!r}. Validos: fake, eco, openai")
