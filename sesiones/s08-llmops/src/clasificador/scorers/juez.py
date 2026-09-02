"""LLM-as-judge con rubrica externa y calibracion obligatoria.

Problema que resuelve
---------------------
Hay una propiedad del sistema que ningun scorer determinista puede medir: si el
resumen es **fiel** a la queja. "Cobro doble" y "Cobro de un viaje no realizado"
son ambos gramaticales, ambos breves, ambos sin PII, y uno de los dos puede estar
inventando un hecho. Comparar con una cadena de referencia no sirve porque no hay
una unica redaccion correcta.

Ahi si hace falta un juez. Y solo ahi.

La regla no negociable
----------------------
> **Un juez sin calibrar contra una muestra etiquetada por humanos no es una
> metrica: es una opinion con API.**

Este modulo la implementa como codigo, no como consejo: ``evaluar_con_juez``
devuelve el resultado **junto** al acuerdo con los humanos, y
``resultado_reportable`` decide si ese numero se puede publicar. Si el kappa esta
por debajo del corte, el numero no se reporta. La alternativa —reportarlo con una
nota al pie— no funciona: el numero viaja y la nota se queda.

Decisiones de diseno
--------------------
1. **La rubrica vive en ``rubricas/juez-resumen.md``**, no en un f-string. Se
   diffea en un PR, la puede leer un anotador que no programa, y el humano y el
   juez trabajan con el mismo texto. Si el criterio del juez y el del anotador
   divergen, el kappa mide la divergencia de los criterios y no la del juez.
2. **Veredicto binario**, no escala de 1 a 5. Una escala de 5 puntos con un LLM
   da numeros que parecen precisos y no lo son. El argumento completo esta en la
   rubrica.
3. **El juez es inyectable.** ``JuezFake`` permite correr toda la tuberia y todos
   los tests sin red. Es tambien lo que hace visible la leccion central: el fake
   es un juez *sin calibrar*, y el modulo obliga a medir su acuerdo antes de
   creerle.
4. **El juez no debe ser el mismo modelo que genero la salida** cuando se usa un
   proveedor real. Un modelo evaluando su propia salida tiende a aprobarla
   (sesgo de auto-preferencia, bien documentado en la literatura). Se pasa un
   ``modelo`` distinto y se registra cual fue.

Alternativas vivas
------------------
No hace falta escribir esto a mano. Todas estas existen y son razonables:

- ``mlflow.genai.make_judge(name=..., instructions=..., model=...)`` y los
  scorers de ``mlflow.genai.scorers`` (``Correctness``, ``Guidelines``,
  ``Safety``, ``PIIDetection``, ``RelevanceToQuery``...). Es lo que se usaria si
  el eval ya vive en MLflow, y esta integrado con el tracing y los datasets.
- **Ragas** y **DeepEval**: bibliotecas de metricas para RAG y agentes, con
  scorers ya definidos y buena integracion con pytest.
- **Arize Phoenix** (open source, sobre OTel + OpenInference) y **Langfuse v4**
  (self-hostable): tracing, datasets y evals en un mismo producto.

Se implementa a mano aqui por una razon pedagogica: cuando el juez es una funcion
de veinte lineas, se ve que "el juez" es un prompt, un parser y un veredicto. La
biblioteca lo hace mejor y lo hace opaco, y en una sesion donde el punto es
*entender que se esta midiendo*, la opacidad cuesta mas de lo que ahorra. En
produccion: usar la biblioteca.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Final, Protocol

from clasificador import rutas
from clasificador.proveedor import Proveedor, RespuestaLLM
from clasificador.scorers.acuerdo import Acuerdo, medir_acuerdo
from clasificador.scorers.deterministas import detectar_pii

logger = logging.getLogger(__name__)

#: Archivo de la rubrica. Es la fuente de verdad del criterio.
ARCHIVO_RUBRICA: Final[str] = "juez-resumen.md"

#: Palabras que delatan un tono no neutro. Se usan en el juez fake y en el
#: guardrail; el juez real las evalua leyendo la rubrica.
_PALABRAS_JUZGADORAS: Final[tuple[str, ...]] = (
    "irresponsable",
    "estupid",
    "idiota",
    "incompetent",
    "abusiv",
    "criminal",
    "asqueros",
    "inaceptable",
    "verguenza",
)

_PLANTILLA_JUEZ: Final[str] = """\
Eres un evaluador de calidad. Aplicas la rubrica que se te entrega de forma
literal y conservadora. No opinas sobre lo que la rubrica no cubre.

## Rubrica

{rubrica}

## Formato de respuesta

Devuelve UNICAMENTE un objeto JSON:

{{"veredicto": "aprobado"|"rechazado", "criterio": "<el criterio que se viola, o 'ninguno'>", "justificacion": "<una frase>"}}
"""

_PLANTILLA_CASO: Final[str] = """\
Queja original del usuario:
\"\"\"{entrada}\"\"\"

Resumen generado por el sistema:
\"\"\"{resumen}\"\"\"

Aplica la rubrica y responde en el formato indicado."""


@dataclass(frozen=True)
class VeredictoJuez:
    """Lo que dice el juez sobre un resumen."""

    aprobado: bool
    criterio: str
    justificacion: str
    #: De donde salio el veredicto: nombre del juez y modelo.
    juez: str
    #: Modelo del juez. Se llama ``modelo`` para que ``costos.costo_de_resultados``
    #: pueda contabilizar al juez con la misma funcion que al clasificador: el juez
    #: tambien cuesta dinero, y en un eval de 40 casos puede costar mas que el
    #: sistema evaluado. Si el costo del juez no se suma, el eval parece gratis.
    modelo: str = "fake-reglas-v1"
    tokens_entrada: int = 0
    tokens_salida: int = 0

    @property
    def tokens(self) -> int:
        return self.tokens_entrada + self.tokens_salida


class Juez(Protocol):
    """Contrato de un juez. Inyectable, igual que el proveedor."""

    nombre: str

    def juzgar(self, entrada: str, resumen: str) -> VeredictoJuez: ...


def cargar_rubrica(archivo: str = ARCHIVO_RUBRICA) -> str:
    """Lee la rubrica de ``rubricas/``.

    Falla si no existe, en lugar de caer a una rubrica por defecto. Un juez que
    funciona sin su rubrica es un juez cuyo criterio nadie escribio, y ese es
    exactamente el estado que este modulo intenta hacer imposible.
    """
    ruta = rutas.RUBRICAS_DIR / archivo
    if not ruta.is_file():
        raise FileNotFoundError(
            f"no existe la rubrica {ruta}. El juez no corre sin rubrica escrita: "
            "es la diferencia entre una metrica y una opinion."
        )
    return ruta.read_text(encoding="utf-8").strip()


# =============================================================================
# JuezFake
# =============================================================================
class JuezFake:
    """Juez determinista por reglas. Sin red, sin costo, **sin calibrar**.

    Aplica de forma mecanica los criterios 2, 3 y 4 de la rubrica (suficiencia,
    ausencia de PII, tono neutro) y **no puede aplicar el 1** (fidelidad), porque
    detectar un hecho inventado requiere entender el texto.

    Eso no es un defecto de la implementacion: es la demostracion. Este juez va a
    aprobar los casos ``c04`` y ``c10`` de ``datos/calibracion-juez.jsonl`` —una
    inversion de sentido y una alucinacion plausible— que un humano rechaza. El
    kappa resultante hace visible el limite, y ese numero es la leccion de la
    sesion: **el juez que no se calibra parece funcionar**.
    """

    #: Minimo de palabras para considerar que el resumen dice algo. Umbral
    #: arbitrario y declarado: un resumen de 3 palabras puede ser suficiente
    #: ("Cobro doble", caso c07), asi que la suficiencia se aproxima exigiendo
    #: que comparta vocabulario con la queja, no una longitud minima.
    MIN_PALABRAS: Final[int] = 2

    #: Frases genericas que no dicen el motivo. Es una lista, no un modelo: si
    #: aparece una variante nueva, el fake la aprueba. Otro limite visible.
    _GENERICAS: Final[tuple[str, ...]] = (
        "presento una queja",
        "reporta un problema",
        "tuvo una mala experiencia",
        "esta insatisfecho",
        "queja sobre el servicio",
    )

    def __init__(self, *, nombre: str = "juez-fake-reglas") -> None:
        self.nombre = nombre

    def juzgar(self, entrada: str, resumen: str) -> VeredictoJuez:
        texto = resumen.strip()
        minusculas = texto.lower()

        if len(texto.split()) < self.MIN_PALABRAS:
            return self._rechazo("2 suficiencia", "el resumen esta vacio o es demasiado corto")

        hallazgos = detectar_pii(texto)
        if hallazgos:
            return self._rechazo("3 sin datos personales", f"contiene {', '.join(hallazgos)}")

        juzgadoras = [p for p in _PALABRAS_JUZGADORAS if p in minusculas]
        if juzgadoras:
            return self._rechazo("4 tono neutro", f"lenguaje valorativo: {juzgadoras[0]}")

        if any(frase in minusculas for frase in self._GENERICAS):
            return self._rechazo("2 suficiencia", "generico: no menciona el motivo principal")

        # Aproximacion pobre a la suficiencia: alguna palabra de contenido en
        # comun con la queja. No mide fidelidad: un resumen puede compartir
        # vocabulario y afirmar lo contrario.
        if not self._comparte_contenido(entrada, texto):
            return self._rechazo("2 suficiencia", "no comparte vocabulario con la queja")

        return VeredictoJuez(
            aprobado=True,
            criterio="ninguno",
            justificacion="cumple los criterios verificables por reglas (1 no evaluado)",
            juez=self.nombre,
        )

    def _rechazo(self, criterio: str, justificacion: str) -> VeredictoJuez:
        return VeredictoJuez(
            aprobado=False,
            criterio=criterio,
            justificacion=justificacion,
            juez=self.nombre,
        )

    @staticmethod
    def _comparte_contenido(entrada: str, resumen: str) -> bool:
        """Solapamiento de palabras de contenido de mas de 4 letras."""
        vacias = {"para", "porque", "cuando", "sobre", "desde", "hasta", "pero", "todo", "toda"}

        def contenido(texto: str) -> set[str]:
            palabras = re.findall(r"[a-zñáéíóúü]{5,}", texto.lower())
            return {p[:6] for p in palabras if p not in vacias}

        return bool(contenido(entrada) & contenido(resumen))


# =============================================================================
# JuezLLM
# =============================================================================
class JuezLLM:
    """Juez real: un LLM aplicando la rubrica de ``rubricas/``.

    Recibe un ``Proveedor``, no crea uno. Asi el juez se puede apuntar a un modelo
    distinto (y a un proveedor distinto) del que genero la salida, que es lo
    recomendable: un modelo evaluando su propia salida tiende a aprobarla.
    """

    def __init__(
        self,
        proveedor: Proveedor,
        *,
        archivo_rubrica: str = ARCHIVO_RUBRICA,
        nombre: str | None = None,
    ) -> None:
        self._proveedor = proveedor
        self._rubrica = cargar_rubrica(archivo_rubrica)
        self._sistema = _PLANTILLA_JUEZ.format(rubrica=self._rubrica)
        modelo = getattr(proveedor, "modelo", "desconocido")
        self.nombre = nombre or f"juez-llm:{modelo}"

    def juzgar(self, entrada: str, resumen: str) -> VeredictoJuez:
        mensajes = [
            {
                "role": "user",
                "content": _PLANTILLA_CASO.format(entrada=entrada, resumen=resumen),
            }
        ]
        respuesta: RespuestaLLM = self._proveedor.completar(
            self._sistema, mensajes, temperatura=0.0
        )
        return self._parsear(respuesta)

    def _parsear(self, respuesta: RespuestaLLM) -> VeredictoJuez:
        """Convierte la respuesta del juez en un veredicto.

        Si el juez no responde en el formato pedido, el veredicto es **rechazo**
        y el criterio queda como ``error_del_juez``. Sesgar hacia el rechazo es
        deliberado: un juez que no se pudo leer no debe contar como aprobacion,
        porque eso convertiria una falla del eval en una senal de calidad. El
        campo ``criterio`` permite separar despues estos casos de los rechazos
        legitimos, y su frecuencia es en si misma una metrica de salud del eval.
        """
        import json

        from clasificador.esquema import extraer_json

        # Los tokens se contabilizan en AMBAS ramas: un veredicto ilegible costo
        # exactamente lo mismo que uno bueno. Si solo se cuenta el camino feliz,
        # el costo del eval se subestima justo en los casos que fallan.
        try:
            datos = json.loads(extraer_json(respuesta.texto))
            veredicto = str(datos.get("veredicto", "")).strip().lower()
            if veredicto not in {"aprobado", "rechazado"}:
                raise ValueError(f"veredicto no reconocido: {veredicto!r}")
            return VeredictoJuez(
                aprobado=veredicto == "aprobado",
                criterio=str(datos.get("criterio", "ninguno")),
                justificacion=str(datos.get("justificacion", "")),
                juez=self.nombre,
                modelo=respuesta.modelo,
                tokens_entrada=respuesta.tokens_entrada,
                tokens_salida=respuesta.tokens_salida,
            )
        except Exception as exc:
            logger.warning("El juez no devolvio un veredicto legible: %s", exc)
            return VeredictoJuez(
                aprobado=False,
                criterio="error_del_juez",
                justificacion=f"respuesta ilegible ({type(exc).__name__})",
                juez=self.nombre,
                modelo=respuesta.modelo,
                tokens_entrada=respuesta.tokens_entrada,
                tokens_salida=respuesta.tokens_salida,
            )


# =============================================================================
# Calibracion
# =============================================================================
@dataclass(frozen=True)
class CasoCalibracion:
    """Un caso con veredicto humano, para calibrar el juez."""

    id: str
    entrada: str
    resumen: str
    veredicto_humano: bool
    criterio: str = ""
    notas: str = ""


def cargar_calibracion(archivo: str = "calibracion-juez.jsonl") -> list[CasoCalibracion]:
    """Carga los casos etiquetados a mano para la calibracion del juez.

    Estos casos son distintos de ``quejas.jsonl``: ahi la etiqueta es la
    clasificacion correcta, aqui es el **veredicto sobre un resumen concreto**.
    Son dos tareas de anotacion distintas y necesitan dos conjuntos distintos. Es
    el error mas comun al montar una calibracion: reusar el dataset de exactitud y
    acabar midiendo otra cosa.
    """
    import json

    ruta = rutas.DATOS_DIR / archivo
    if not ruta.is_file():
        raise FileNotFoundError(f"no existe el conjunto de calibracion: {ruta}")

    casos: list[CasoCalibracion] = []
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip():
            continue
        registro = json.loads(linea)
        veredicto = str(registro["veredicto_humano"]).strip().lower()
        if veredicto not in {"aprobado", "rechazado"}:
            raise ValueError(
                f"{ruta.name}:{numero}: veredicto_humano debe ser "
                f"'aprobado' o 'rechazado', no {veredicto!r}"
            )
        casos.append(
            CasoCalibracion(
                id=str(registro["id"]),
                entrada=str(registro["entrada"]),
                resumen=str(registro["resumen"]),
                veredicto_humano=veredicto == "aprobado",
                criterio=str(registro.get("criterio", "")),
                notas=str(registro.get("notas", "")),
            )
        )
    return casos


@dataclass(frozen=True)
class ResultadoCalibracion:
    """Acuerdo del juez con los humanos, con los desacuerdos identificados."""

    acuerdo: Acuerdo
    juez: str
    #: ids de los casos donde juez y humano difieren. Son los que hay que leer:
    #: cada uno indica un criterio de la rubrica que esta ambiguo o que el juez
    #: no esta aplicando.
    desacuerdos: list[str]
    #: Criterio de la rubrica que el humano invoco en cada desacuerdo.
    criterios_en_desacuerdo: list[str] = field(default_factory=list)

    @property
    def punto_ciego(self) -> str | None:
        """Criterio en el que se concentran los desacuerdos, si hay uno.

        Es el analisis que kappa **no** hace y que decide si el juez sirve.

        Kappa dice *cuanto* coincide el juez; no dice si los desacuerdos son
        ruido repartido o un fallo sistematico en un criterio. Dos escenarios con
        el mismo kappa son muy distintos:

        - 4 desacuerdos repartidos entre los cuatro criterios: el juez es ruidoso
          y con mas casos de calibracion probablemente mejore.
        - 4 desacuerdos todos en el criterio de fidelidad: el juez **no puede**
          evaluar ese criterio. Mas casos no lo arreglan; hace falta otro juez o
          otro metodo.

        El segundo caso es el peligroso porque el kappa global puede quedar por
        encima del corte y dar via libre a un juez ciego a la falla mas grave.
        Con este dataset y ``JuezFake`` ocurre exactamente eso: el kappa pasa el
        corte y los dos desacuerdos son de fidelidad, el criterio que un juez por
        reglas no puede aplicar.
        """
        if not self.criterios_en_desacuerdo:
            return None
        conteo: dict[str, int] = {}
        for criterio in self.criterios_en_desacuerdo:
            conteo[criterio] = conteo.get(criterio, 0) + 1
        criterio, veces = max(conteo.items(), key=lambda par: par[1])
        total = len(self.criterios_en_desacuerdo)
        # Umbral declarado: al menos 2 casos y al menos el 60% de los desacuerdos
        # en el mismo criterio. Con menos, la concentracion no se distingue del
        # azar sobre pocos casos.
        if veces >= 2 and veces / total >= 0.6:
            return (
                f"{veces} de {total} desacuerdos son del criterio '{criterio}': "
                "es un punto ciego sistematico, no ruido. Mas casos de calibracion "
                "no lo arreglan; hace falta otro juez o otro metodo para ese criterio."
            )
        return None

    def como_dict(self) -> dict[str, object]:
        return {
            "juez": self.juez,
            "desacuerdos": self.desacuerdos,
            "criterios_en_desacuerdo": self.criterios_en_desacuerdo,
            "punto_ciego": self.punto_ciego,
            **self.acuerdo.como_dict(),
        }


def calibrar(juez: Juez, casos: list[CasoCalibracion] | None = None) -> ResultadoCalibracion:
    """Mide el acuerdo del juez con los veredictos humanos.

    Esta funcion se corre **antes** de usar el juez para medir nada. No despues,
    no "cuando haya tiempo": antes. Un juez sin este numero no produce metricas.
    """
    casos = casos if casos is not None else cargar_calibracion()
    if not casos:
        raise ValueError("no hay casos de calibracion")

    veredictos_juez: list[bool] = []
    veredictos_humano: list[bool] = []
    desacuerdos: list[str] = []
    criterios: list[str] = []
    for caso in casos:
        veredicto = juez.juzgar(caso.entrada, caso.resumen)
        veredictos_juez.append(veredicto.aprobado)
        veredictos_humano.append(caso.veredicto_humano)
        if veredicto.aprobado != caso.veredicto_humano:
            desacuerdos.append(caso.id)
            # Se registra el criterio que invoco el HUMANO, no el juez: es la
            # referencia. Agrupar por el criterio del juez diria en que se
            # equivoco el juez segun el juez, que no informa.
            criterios.append(caso.criterio or "sin_criterio")

    return ResultadoCalibracion(
        acuerdo=medir_acuerdo(veredictos_juez, veredictos_humano),
        juez=getattr(juez, "nombre", type(juez).__name__),
        desacuerdos=desacuerdos,
        criterios_en_desacuerdo=criterios,
    )


def resultado_reportable(calibracion: ResultadoCalibracion, tasa_aprobacion: float) -> str:
    """Formatea el resultado del juez **siempre** junto a su calibracion.

    Es la funcion que hace cumplir la regla. No existe una via en este modulo para
    obtener la tasa de aprobacion del juez sin el kappa al lado, porque la via
    facil es la que se usa.
    """
    acuerdo = calibracion.acuerdo
    if acuerdo.kappa < 0.40 or acuerdo.n < 10:
        return (
            f"NO REPORTABLE — el juez '{calibracion.juez}' tiene kappa="
            f"{acuerdo.kappa:.2f} sobre n={acuerdo.n} ({acuerdo.interpretacion}). "
            f"Su tasa de aprobacion ({tasa_aprobacion:.0%}) no es una metrica de calidad. "
            f"Diagnostico: {acuerdo.sesgo_del_juez}. "
            "Arregla la rubrica o cambia el modelo juez antes de usar este numero."
        )
    linea = (
        f"aprobacion del juez: {tasa_aprobacion:.0%} "
        f"[juez={calibracion.juez}, kappa={acuerdo.kappa:.2f}, "
        f"acuerdo={acuerdo.porcentaje_acuerdo:.0%}, n={acuerdo.n}, "
        f"{acuerdo.interpretacion}]"
    )
    # El punto ciego se anuncia AUNQUE el kappa pase el corte. Es el caso mas
    # peligroso: un juez con buen kappa global y una ceguera sistematica en el
    # criterio que mas importa. Sin esta linea, el kappa da via libre.
    if calibracion.punto_ciego:
        linea += f"\n  ADVERTENCIA: {calibracion.punto_ciego}"
    return linea
