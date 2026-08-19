"""Scorers deterministas: baratos, rapidos y no mienten.

Problema que resuelve
---------------------
La reaccion habitual ante "hay que evaluar un LLM" es ir directo al juez de LLM.
Es un error de orden. La mayoria de los fallos reales de un sistema con salida
estructurada son **verificables sin ningun modelo**:

- el JSON no parsea,
- la categoria no esta en el enum,
- la severidad viene como string o fuera de rango,
- el resumen tiene 60 palabras y rompe la UI,
- el resumen filtra un telefono del usuario,
- la categoria no coincide con la etiqueta humana.

Los seis se miden con codigo, en milisegundos, con costo cero y con resultado
identico en cada ejecucion. Un juez de LLM para esto seria mas caro, mas lento y
menos fiable.

Regla de orden que se ensena en la sesion: **primero deterministas, y el juez
solo para lo que genuinamente no tiene respuesta unica** (la calidad del
resumen). Si un scorer se puede escribir con un ``==``, escribirlo con un LLM es
pagar por varianza.

Relacion con el testing de la sesion 1
--------------------------------------
Esto es *property-based testing* aplicado a evals. No se afirma "la salida es
igual a X" —para el resumen eso es imposible— sino "la salida tiene estas
propiedades". La diferencia entre un test determinista clasico y un scorer es que
el scorer devuelve un numero agregable en lugar de aprobar o fallar, porque con
un LLM la pregunta no es "paso" sino "en que fraccion de los casos paso".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from clasificador.clasificador import ResultadoClasificacion
from clasificador.datos import TOLERANCIA_SEVERIDAD, CasoEval
from clasificador.esquema import (
    CATEGORIAS_VALIDAS,
    MAX_PALABRAS_RESUMEN,
    SEVERIDAD_MAX,
    SEVERIDAD_MIN,
)


@dataclass(frozen=True)
class Puntaje:
    """Resultado de un scorer sobre un caso.

    ``motivo`` no es opcional en la practica: un scorer que devuelve 0.0 sin
    explicar por que obliga a reproducir el caso a mano para entenderlo. Con el
    motivo, el reporte del eval se lee y se actua sin volver a correr nada.
    """

    nombre: str
    valor: float
    motivo: str = ""

    @property
    def aprobado(self) -> bool:
        return self.valor >= 1.0


# =============================================================================
# Deteccion de PII
# =============================================================================
#: Patrones de datos personales que NO deben aparecer en la salida.
#:
#: Advertencia honesta y necesaria: esta es una deteccion por regex, es decir un
#: piso, no un techo. No detecta nombres propios, no entiende contexto y produce
#: falsos positivos (un numero de factura de 10 digitos parece un telefono). Para
#: produccion se usa un detector dedicado —Presidio, o el scorer ``PIIDetection``
#: que trae ``mlflow.genai.scorers``, que usa un modelo— y este queda como
#: verificacion barata de primera linea, no como la unica.
#:
#: El valor de tenerlo aqui es que corre en CI sin credenciales y atrapa la clase
#: de fuga mas comun: el modelo copiando literalmente el contacto del usuario.
_PATRONES_PII: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("correo", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")),
    # Telefono colombiano: 10 digitos, con separadores opcionales, o con indicativo.
    ("telefono", re.compile(r"(?<!\d)(?:\+?57[\s-]?)?3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")),
    # Placa colombiana de vehiculo: tres letras y tres digitos.
    ("placa", re.compile(r"\b[A-Z]{3}[\s-]?\d{3}\b")),
    # Tarjeta: 13 a 16 digitos seguidos, o los ultimos 4 precedidos de contexto.
    ("tarjeta", re.compile(r"(?<!\d)\d{13,16}(?!\d)")),
    ("tarjeta_parcial", re.compile(r"(?i)\b(?:termina(?:da|)|final)\s+en\s+\d{4}\b")),
    # Direccion urbana colombiana: 'carrera 43 #12-05', 'calle 10 # 5 - 20'.
    (
        "direccion",
        re.compile(r"(?i)\b(?:calle|carrera|cra|cl|avenida|av|diagonal|transversal)\s*\d+\s*#"),
    ),
)


def detectar_pii(texto: str) -> list[str]:
    """Devuelve los tipos de PII encontrados en el texto. Lista vacia = limpio."""
    return [nombre for nombre, patron in _PATRONES_PII if patron.search(texto)]


# =============================================================================
# Scorers de contrato — no necesitan verdad de terreno
# =============================================================================
def json_valido(resultado: ResultadoClasificacion) -> Puntaje:
    """1.0 si la salida parseo y valido contra el esquema.

    Es el scorer mas importante y el que mas se olvida. Un sistema con 0.95 aqui
    falla una peticion de cada veinte, y eso no es un problema de calidad del
    modelo: es una caida parcial del servicio.
    """
    if resultado.exito:
        motivo = "" if resultado.intentos == 1 else f"valido tras {resultado.intentos} intentos"
        return Puntaje("json_valido", 1.0, motivo)
    ultimo = resultado.errores[-1] if resultado.errores else "sin detalle"
    return Puntaje("json_valido", 0.0, f"no cumplio el contrato: {ultimo}")


def sin_reintentos(resultado: ResultadoClasificacion) -> Puntaje:
    """1.0 si acerto en el primer intento.

    Se separa de ``json_valido`` a proposito: un sistema que siempre acierta al
    segundo intento tiene 1.0 en validez y el doble de costo y de latencia. Esa
    diferencia hay que poder verla, y es la razon por la que este scorer existe
    aunque parezca redundante.
    """
    if resultado.intentos <= 1 and resultado.exito:
        return Puntaje("sin_reintentos", 1.0)
    return Puntaje("sin_reintentos", 0.0, f"{resultado.intentos} intentos")


def categoria_en_enum(resultado: ResultadoClasificacion) -> Puntaje:
    """1.0 si la categoria pertenece al enum.

    Con validacion Pydantic esto es redundante por construccion, y se mantiene
    por dos razones: documenta la propiedad de forma explicita en el reporte, y
    sigue midiendo algo el dia que alguien relaje el esquema o agregue un camino
    que no pase por ``parsear_clasificacion``. Un scorer que hoy siempre da 1.0
    es una alarma que no ha sonado, no una alarma inutil.
    """
    if resultado.clasificacion is None:
        return Puntaje("categoria_en_enum", 0.0, "no hay salida valida")
    valor = str(resultado.clasificacion.categoria)
    if valor in CATEGORIAS_VALIDAS:
        return Puntaje("categoria_en_enum", 1.0)
    return Puntaje("categoria_en_enum", 0.0, f"categoria fuera del enum: {valor!r}")


def severidad_en_rango(resultado: ResultadoClasificacion) -> Puntaje:
    """1.0 si la severidad esta dentro del rango del contrato."""
    if resultado.clasificacion is None:
        return Puntaje("severidad_en_rango", 0.0, "no hay salida valida")
    valor = resultado.clasificacion.severidad
    if SEVERIDAD_MIN <= valor <= SEVERIDAD_MAX:
        return Puntaje("severidad_en_rango", 1.0)
    return Puntaje("severidad_en_rango", 0.0, f"severidad {valor} fuera de rango")


def resumen_dentro_del_limite(resultado: ResultadoClasificacion) -> Puntaje:
    """1.0 si el resumen no excede el limite de palabras.

    El limite es un requisito de producto (la UI del agente de soporte), no una
    preferencia. Medirlo como scorer y no solo como validacion permite ver la
    *distribucion*: un sistema que queda siempre en 19 de 20 palabras esta al
    borde y se va a romper con el proximo cambio de prompt.
    """
    if resultado.clasificacion is None:
        return Puntaje("resumen_dentro_del_limite", 0.0, "no hay salida valida")
    palabras = len(resultado.clasificacion.resumen.split())
    if palabras == 0:
        return Puntaje("resumen_dentro_del_limite", 0.0, "resumen vacio")
    if palabras <= MAX_PALABRAS_RESUMEN:
        return Puntaje("resumen_dentro_del_limite", 1.0, f"{palabras} palabras")
    return Puntaje(
        "resumen_dentro_del_limite",
        0.0,
        f"{palabras} palabras (maximo {MAX_PALABRAS_RESUMEN})",
    )


def salida_sin_pii(resultado: ResultadoClasificacion) -> Puntaje:
    """1.0 si el resumen no contiene datos personales detectables.

    Se evalua sobre la **salida**, no sobre la entrada: el usuario puede escribir
    su telefono en la queja y esta en su derecho. El problema es que el sistema lo
    copie al resumen, porque desde ahi se propaga al ticket de soporte, a los
    logs, a las trazas y a cualquier dataset que se construya con esas trazas.
    Ese es el vector de fuga real, y esta descrito en ``riesgos.md``.
    """
    if resultado.clasificacion is None:
        return Puntaje("salida_sin_pii", 0.0, "no hay salida valida")
    hallazgos = detectar_pii(resultado.clasificacion.resumen)
    if not hallazgos:
        return Puntaje("salida_sin_pii", 1.0)
    return Puntaje("salida_sin_pii", 0.0, f"PII en el resumen: {', '.join(hallazgos)}")


# =============================================================================
# Scorers de exactitud — requieren verdad de terreno
# =============================================================================
def categoria_correcta(resultado: ResultadoClasificacion, caso: CasoEval) -> Puntaje:
    """1.0 si la categoria coincide con la etiqueta humana.

    Esta es la metrica que solo existe porque alguien etiqueto el dataset a mano.
    Es lo que ningun juez de LLM puede sustituir: el juez puede opinar si una
    categoria es *razonable*, no si es *la que el negocio decidio*.
    """
    if resultado.clasificacion is None:
        return Puntaje("categoria_correcta", 0.0, "no hay salida valida")
    obtenida = str(resultado.clasificacion.categoria)
    if obtenida == caso.categoria:
        return Puntaje("categoria_correcta", 1.0)
    return Puntaje("categoria_correcta", 0.0, f"esperada {caso.categoria!r}, obtenida {obtenida!r}")


def severidad_exacta(resultado: ResultadoClasificacion, caso: CasoEval) -> Puntaje:
    """1.0 si la severidad coincide exactamente con la etiqueta."""
    if resultado.clasificacion is None:
        return Puntaje("severidad_exacta", 0.0, "no hay salida valida")
    obtenida = resultado.clasificacion.severidad
    if obtenida == caso.severidad:
        return Puntaje("severidad_exacta", 1.0)
    return Puntaje("severidad_exacta", 0.0, f"esperada {caso.severidad}, obtenida {obtenida}")


def severidad_con_tolerancia(resultado: ResultadoClasificacion, caso: CasoEval) -> Puntaje:
    """1.0 si la severidad esta a +-1 de la etiqueta.

    Existe porque dos anotadores humanos difieren en un nivel con frecuencia (ver
    ``rubricas/severidad.md``). Exigir igualdad exacta mide, en buena parte, el
    ruido del etiquetado.

    Se reportan **las dos** metricas. Publicar solo la tolerante infla el numero;
    publicar solo la exacta castiga al modelo por un desacuerdo que los humanos
    tambien tienen. Ver las dos juntas es lo que permite decir "el modelo esta en
    el techo del dataset" en lugar de "el modelo esta mal".
    """
    if resultado.clasificacion is None:
        return Puntaje("severidad_con_tolerancia", 0.0, "no hay salida valida")
    diferencia = abs(resultado.clasificacion.severidad - caso.severidad)
    if diferencia <= TOLERANCIA_SEVERIDAD:
        return Puntaje("severidad_con_tolerancia", 1.0, f"diferencia {diferencia}")
    return Puntaje("severidad_con_tolerancia", 0.0, f"diferencia {diferencia}")


def reembolso_correcto(resultado: ResultadoClasificacion, caso: CasoEval) -> Puntaje:
    """1.0 si ``requiere_reembolso`` coincide con la etiqueta.

    Es el campo con **consecuencia economica directa**: un falso positivo devuelve
    dinero que no correspondia y un falso negativo deja a un usuario sin su
    reembolso. En un sistema real este campo no se automatiza al 100%: se usa como
    sugerencia y un humano confirma, precisamente porque los dos errores cuestan
    dinero de formas distintas y asimetricas. La matriz de costos de la sesion 3
    aplica igual aqui.
    """
    if resultado.clasificacion is None:
        return Puntaje("reembolso_correcto", 0.0, "no hay salida valida")
    obtenido = resultado.clasificacion.requiere_reembolso
    if obtenido == caso.requiere_reembolso:
        return Puntaje("reembolso_correcto", 1.0)
    return Puntaje(
        "reembolso_correcto",
        0.0,
        f"esperado {caso.requiere_reembolso}, obtenido {obtenido}",
    )


# =============================================================================
# Orquestacion
# =============================================================================
#: Scorers que solo necesitan la salida. Sirven para monitorear **produccion**,
#: donde no hay etiquetas. Es la distincion clave con los de abajo.
SCORERS_DE_CONTRATO: Final[tuple[str, ...]] = (
    "json_valido",
    "sin_reintentos",
    "categoria_en_enum",
    "severidad_en_rango",
    "resumen_dentro_del_limite",
    "salida_sin_pii",
)

#: Scorers que necesitan verdad de terreno. Solo corren **offline**, contra el
#: dataset etiquetado.
SCORERS_DE_EXACTITUD: Final[tuple[str, ...]] = (
    "categoria_correcta",
    "severidad_exacta",
    "severidad_con_tolerancia",
    "reembolso_correcto",
)

TODOS_LOS_SCORERS: Final[tuple[str, ...]] = SCORERS_DE_CONTRATO + SCORERS_DE_EXACTITUD


def puntuar(resultado: ResultadoClasificacion, caso: CasoEval | None = None) -> list[Puntaje]:
    """Aplica todos los scorers deterministas aplicables.

    Args:
        resultado: salida del clasificador.
        caso: verdad de terreno. Si es ``None`` solo corren los de contrato, que
            es exactamente el modo en que esto se usaria sobre trafico de
            produccion.

    Returns:
        Los puntajes, en orden estable para que el reporte sea diffeable.
    """
    puntajes = [
        json_valido(resultado),
        sin_reintentos(resultado),
        categoria_en_enum(resultado),
        severidad_en_rango(resultado),
        resumen_dentro_del_limite(resultado),
        salida_sin_pii(resultado),
    ]
    if caso is not None:
        puntajes += [
            categoria_correcta(resultado, caso),
            severidad_exacta(resultado, caso),
            severidad_con_tolerancia(resultado, caso),
            reembolso_correcto(resultado, caso),
        ]
    return puntajes


def agregar(puntajes_por_caso: list[list[Puntaje]]) -> dict[str, float]:
    """Promedia cada scorer sobre todos los casos.

    La media de un scorer binario es la fraccion de casos que pasaron, que es la
    lectura que interesa ("el 78% de las salidas fueron validas"). No se reporta
    una media global de todos los scorers juntos: mezclar exactitud de categoria
    con ausencia de PII en un unico numero produce una cifra que sube cuando algo
    importante empeora. Un solo numero de calidad es comodo y es como se ocultan
    las regresiones.
    """
    sumas: dict[str, float] = {}
    conteos: dict[str, int] = {}
    for puntajes in puntajes_por_caso:
        for puntaje in puntajes:
            sumas[puntaje.nombre] = sumas.get(puntaje.nombre, 0.0) + puntaje.valor
            conteos[puntaje.nombre] = conteos.get(puntaje.nombre, 0) + 1
    return {nombre: sumas[nombre] / conteos[nombre] for nombre in sorted(sumas)}
