"""Calculadora de costos por request, con precios parametrizables.

Problema que resuelve
---------------------
En ML clasico el costo de inferencia es casi invisible: el modelo esta cargado en
memoria y una prediccion mas no cambia la factura. Por eso el costo aparece al
final de la lista de preocupaciones, si aparece.

Con un LLM el costo es **por request y proporcional al texto**, y sube de
prioridad hasta quedar al lado de la latencia y la calidad:

- Cada request cuesta dinero medible. Mil requests son mil veces mas caros.
- El costo depende de decisiones de diseno que parecen inocuas: agregar tres
  ejemplos al prompt de sistema encarece **todas** las llamadas para siempre.
- Un reintento duplica el costo de ese caso. Un bucle de reintentos sin tope es
  una factura sin tope.
- El eval tambien cuesta. Un dataset de 40 casos, dos versiones de prompt y un
  juez de LLM son ~120 llamadas por corrida, y en CI se corre en cada PR.

Sin una estimacion, la conversacion "usemos el modelo grande" no tiene datos. Con
ella, se compara el costo con la mejora en el eval y la decision es de ingenieria
y no de intuicion.

Decision de diseno: los precios viven en ``config/precios.yaml``
----------------------------------------------------------------
Los precios cambian todos los meses. Hardcodeados en un ``.py`` produce
estimaciones equivocadas de forma silenciosa: nadie revisa una constante que ya
esta ahi. En un archivo de configuracion con campo ``actualizado``, la
calculadora puede **advertir** cuando los precios estan viejos, que es lo unico
que evita la cifra plausible y falsa.

Advertencia sobre el alcance
----------------------------
Esto estima el costo de los tokens del modelo. El costo total de un sistema con
LLM incluye ademas embeddings, base vectorial, almacenamiento de trazas (que en
un sistema con trafico real no es despreciable), reintentos por rate limit y el
tiempo de las personas que revisan las salidas. Presentar el costo de tokens como
el costo del sistema es la subestimacion mas comun.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from clasificador import rutas

logger = logging.getLogger(__name__)

_TOKENS_POR_UNIDAD: Final[int] = 1_000_000


@dataclass(frozen=True)
class PrecioModelo:
    """Precio de un modelo, en USD por millon de tokens."""

    modelo: str
    entrada: float
    salida: float
    notas: str = ""


@dataclass(frozen=True)
class TablaDePrecios:
    """Precios cargados, con la fecha en que se actualizaron.

    La fecha es parte del dato. Un precio sin fecha no se puede auditar y no se
    puede saber si la estimacion que produjo sigue siendo valida.
    """

    precios: dict[str, PrecioModelo]
    actualizado: dt.date | None
    vigencia_dias: int
    modelo_por_defecto: str

    def esta_vencida(self, hoy: dt.date | None = None) -> bool:
        """Si los precios llevan mas de ``vigencia_dias`` sin revisarse."""
        if self.actualizado is None:
            return True
        referencia = hoy or dt.date.today()
        return (referencia - self.actualizado).days > self.vigencia_dias

    def precio_de(self, modelo: str) -> PrecioModelo:
        """Precio de un modelo, cayendo al default (el mas caro) si no esta.

        Se cae al modelo caro y no a cero. Un modelo desconocido con precio cero
        produce un reporte que dice que el sistema es gratis, y ese es el peor
        error posible en una estimacion de costos: la que tranquiliza.
        """
        if modelo in self.precios:
            return self.precios[modelo]
        respaldo = self.precios.get(self.modelo_por_defecto)
        if respaldo is None:
            raise KeyError(
                f"modelo {modelo!r} no esta en la tabla de precios y el modelo por "
                f"defecto {self.modelo_por_defecto!r} tampoco. Revisa precios.yaml."
            )
        logger.warning(
            "Modelo %r no esta en precios.yaml; se estima con %r (el mas caro) "
            "para no subestimar el costo.",
            modelo,
            self.modelo_por_defecto,
        )
        return PrecioModelo(
            modelo=f"{modelo} (estimado como {respaldo.modelo})",
            entrada=respaldo.entrada,
            salida=respaldo.salida,
            notas="precio no encontrado; se uso el modelo por defecto",
        )


def cargar_precios(ruta: Path | None = None) -> TablaDePrecios:
    """Carga ``config/precios.yaml``.

    Raises:
        FileNotFoundError: si no existe. No hay tabla de precios por defecto en
            codigo a proposito: si el archivo falta, la respuesta correcta es
            "no puedo estimar el costo", no una cifra inventada.
    """
    import yaml

    archivo = ruta or rutas.PRECIOS_YAML
    if not archivo.is_file():
        raise FileNotFoundError(
            f"no existe {archivo}. Los precios son configuracion obligatoria: "
            "sin ellos no hay estimacion de costo posible."
        )
    datos: Any = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}

    precios: dict[str, PrecioModelo] = {}
    for nombre, valores in (datos.get("modelos") or {}).items():
        precios[str(nombre)] = PrecioModelo(
            modelo=str(nombre),
            entrada=float(valores["entrada"]),
            salida=float(valores["salida"]),
            notas=str(valores.get("notas", "")),
        )

    actualizado: dt.date | None = None
    crudo = datos.get("actualizado")
    if crudo:
        try:
            actualizado = dt.date.fromisoformat(str(crudo))
        except ValueError:
            logger.warning("El campo 'actualizado' de %s no es una fecha ISO", archivo.name)

    return TablaDePrecios(
        precios=precios,
        actualizado=actualizado,
        vigencia_dias=int(datos.get("vigencia_dias", 60)),
        modelo_por_defecto=str(datos.get("modelo_por_defecto_si_desconocido", "gpt-4o")),
    )


@dataclass(frozen=True)
class Costo:
    """Costo estimado de una o varias llamadas."""

    modelo: str
    tokens_entrada: int
    tokens_salida: int
    usd_entrada: float
    usd_salida: float
    #: True si los precios usados estan fuera de vigencia. Viaja con el resultado
    #: para que ningun reporte pueda mostrar el numero sin la advertencia.
    precios_vencidos: bool = False

    @property
    def usd_total(self) -> float:
        return self.usd_entrada + self.usd_salida

    def por_mil_requests(self) -> float:
        """Extrapolacion a 1000 requests con este mismo perfil de tokens.

        Es la cifra que hace tangible el costo. "0.00021 USD por request" no le
        dice nada a nadie; "0.21 USD por cada mil quejas clasificadas" si, y
        permite hacer la cuenta con el volumen real del negocio.
        """
        return self.usd_total * 1000


def calcular_costo(
    tokens_entrada: int,
    tokens_salida: int,
    modelo: str,
    *,
    tabla: TablaDePrecios | None = None,
    requests: int = 1,
) -> Costo:
    """Costo de ``requests`` llamadas con ese perfil de tokens.

    Args:
        tokens_entrada: tokens del prompt. Incluye el prompt de sistema, que en
            este proyecto es la mayor parte: ``v2-rubrica.txt`` es largo y se
            envia en **cada** llamada. Esa es la razon por la que un prompt de
            sistema extenso es una decision de costo y no solo de calidad.
        tokens_salida: tokens generados. Casi siempre mucho menos que la entrada
            en una tarea de clasificacion, y mas caros por token.
        modelo: nombre reportado por el proveedor.
        tabla: tabla de precios. ``None`` la carga del YAML.
        requests: cuantas llamadas con ese perfil.

    Returns:
        ``Costo`` con el desglose.
    """
    if tokens_entrada < 0 or tokens_salida < 0:
        raise ValueError("los tokens no pueden ser negativos")
    if requests < 0:
        raise ValueError("requests no puede ser negativo")

    tabla = tabla if tabla is not None else cargar_precios()
    precio = tabla.precio_de(modelo)

    total_entrada = tokens_entrada * requests
    total_salida = tokens_salida * requests
    return Costo(
        modelo=precio.modelo,
        tokens_entrada=total_entrada,
        tokens_salida=total_salida,
        usd_entrada=total_entrada / _TOKENS_POR_UNIDAD * precio.entrada,
        usd_salida=total_salida / _TOKENS_POR_UNIDAD * precio.salida,
        precios_vencidos=tabla.esta_vencida(),
    )


def costo_de_resultados(
    resultados: list[Any],
    *,
    tabla: TablaDePrecios | None = None,
) -> dict[str, Costo]:
    """Agrupa por modelo el costo de una lista de ``ResultadoClasificacion``.

    Se agrupa por modelo y no se suma todo junto porque en un eval comparativo hay
    varios modelos en juego (el clasificador y el juez, o dos candidatos). Un total
    unico esconde justamente la comparacion que se quiere hacer.

    Recibe ``list[Any]`` para no acoplar el modulo de costos al de clasificacion:
    cualquier objeto con ``modelo``, ``tokens_entrada`` y ``tokens_salida`` sirve,
    incluyendo los veredictos del juez.
    """
    tabla = tabla if tabla is not None else cargar_precios()
    por_modelo: dict[str, tuple[int, int]] = {}
    for resultado in resultados:
        modelo = str(getattr(resultado, "modelo", "desconocido"))
        entrada, salida = por_modelo.get(modelo, (0, 0))
        por_modelo[modelo] = (
            entrada + int(getattr(resultado, "tokens_entrada", 0)),
            salida + int(getattr(resultado, "tokens_salida", 0)),
        )
    return {
        modelo: calcular_costo(entrada, salida, modelo, tabla=tabla)
        for modelo, (entrada, salida) in sorted(por_modelo.items())
    }


def formatear_costo(costo: Costo) -> str:
    """Linea legible con el costo y, si aplica, la advertencia de vigencia."""
    base = (
        f"{costo.modelo}: {costo.tokens_entrada} tokens de entrada + "
        f"{costo.tokens_salida} de salida = {costo.usd_total:.6f} USD "
        f"({costo.por_mil_requests():.2f} USD / 1000 requests con este perfil)"
    )
    if costo.precios_vencidos:
        return base + "  [AVISO: los precios de config/precios.yaml estan fuera de vigencia]"
    return base
