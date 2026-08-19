"""Carga y validacion del dataset de evals. El activo mas valioso de la sesion.

Problema que resuelve
---------------------
Sin dataset de eval, cualquier afirmacion sobre un prompt es una anecdota. "Ahora
responde mejor" significa "las tres quejas que probe me gustaron mas", y las tres
las eligio quien escribio el prompt. Ese es el estado por defecto de casi todos
los proyectos de LLM que llegan a produccion.

Este archivo de 36 casos etiquetados a mano es lo que convierte "creo que mejoro"
en "la exactitud de categoria subio de 0.61 a 0.78 en el mismo holdout". Es
exactamente el rol que cumple ``PARTICION_TEST`` en el caso guia (ver
``taxi.config``): un holdout fijo que nadie usa para ajustar y que por eso puede
servir de juez.

Y es la parte que nadie quiere construir. Etiquetar 36 casos con criterio
consistente toma un par de horas, no se puede delegar a un modelo sin volverlo
circular, y no produce ninguna demo vistosa. Es tambien la que da todo el
retorno: el prompt se reescribe en cinco minutos, el dataset se reutiliza durante
anos y sobrevive al cambio de modelo, de proveedor y de framework.

Por que el dataset se versiona en Git y no se genera
----------------------------------------------------
- Generarlo con un LLM mide el acuerdo con ese LLM, no con la realidad. Sirve
  para *aumentar* un dataset ya etiquetado, no para crearlo.
- 36 lineas de JSONL se diffean en un PR. Cuando alguien cambia una etiqueta,
  la discusion queda en el review, que es donde debe estar.
- El campo ``notas`` documenta **por que** cada etiqueta es esa. Sin eso, en tres
  meses nadie recuerda el criterio y el siguiente anotador introduce otro.

Formato: JSONL y no CSV porque ``esperado`` es un objeto anidado, y no Parquet
porque un dataset que se edita a mano tiene que ser legible en un diff.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from clasificador import rutas
from clasificador.esquema import (
    CATEGORIAS_VALIDAS,
    SEVERIDAD_MAX,
    SEVERIDAD_MIN,
)

#: Campos que el sistema evalua. ``resumen`` no esta: no tiene una unica
#: respuesta correcta y por eso lo mide el juez, no una comparacion exacta. Esa
#: division es el nucleo de la sesion.
CAMPOS_ESPERADOS: Final[tuple[str, ...]] = ("categoria", "severidad", "requiere_reembolso")

#: Tolerancia de severidad. Un anotador humano y otro difieren en +-1 con
#: frecuencia; exigir igualdad exacta mide el ruido del etiquetado y no la
#: calidad del modelo. Se reportan las dos metricas (exacta y con tolerancia)
#: para que la diferencia sea visible en lugar de quedar escondida en la
#: definicion.
TOLERANCIA_SEVERIDAD: Final[int] = 1


@dataclass(frozen=True)
class CasoEval:
    """Un caso del dataset: entrada, verdad de terreno y el criterio que la sustenta."""

    id: str
    entrada: str
    esperado: dict[str, Any]
    notas: str = ""

    @property
    def categoria(self) -> str:
        return str(self.esperado["categoria"])

    @property
    def severidad(self) -> int:
        return int(self.esperado["severidad"])

    @property
    def requiere_reembolso(self) -> bool:
        return bool(self.esperado["requiere_reembolso"])


class DatasetInvalido(ValueError):
    """El dataset no cumple su propio contrato.

    Se valida al cargar y no al usar. Un dataset de eval corrupto produce
    metricas plausibles y equivocadas, que es el peor fallo posible: no se nota.
    Es el mismo argumento de los contratos de datos de la sesion 2, aplicado al
    activo que sostiene todas las decisiones de esta sesion.
    """


def cargar_casos(ruta: Path | None = None) -> list[CasoEval]:
    """Carga y **valida** el dataset de evals.

    Args:
        ruta: archivo JSONL. ``None`` usa ``datos/quejas.jsonl``.

    Returns:
        Los casos, en el orden del archivo.

    Raises:
        DatasetInvalido: si falta un campo, hay un id duplicado, una categoria
            fuera del enum o una severidad fuera de rango.
    """
    archivo = ruta or rutas.DATASET_EVALS
    if not archivo.is_file():
        raise DatasetInvalido(f"no existe el dataset de evals: {archivo}")

    casos: list[CasoEval] = []
    vistos: set[str] = set()
    for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip():
            continue
        try:
            registro: Any = json.loads(linea)
        except json.JSONDecodeError as exc:
            raise DatasetInvalido(f"{archivo.name}:{numero}: JSON malformado: {exc.msg}") from exc
        casos.append(_construir_caso(registro, archivo.name, numero, vistos))

    if not casos:
        raise DatasetInvalido(f"{archivo.name}: el dataset esta vacio")
    return casos


def _construir_caso(
    registro: Any,
    nombre_archivo: str,
    numero: int,
    vistos: set[str],
) -> CasoEval:
    """Valida un registro y lo convierte en ``CasoEval``."""
    ubicacion = f"{nombre_archivo}:{numero}"
    if not isinstance(registro, dict):
        raise DatasetInvalido(f"{ubicacion}: se esperaba un objeto JSON")

    for campo in ("id", "entrada", "esperado"):
        if campo not in registro:
            raise DatasetInvalido(f"{ubicacion}: falta el campo obligatorio {campo!r}")

    identificador = str(registro["id"])
    if identificador in vistos:
        raise DatasetInvalido(f"{ubicacion}: id duplicado {identificador!r}")
    vistos.add(identificador)

    if not str(registro["entrada"]).strip():
        raise DatasetInvalido(f"{ubicacion}: 'entrada' esta vacia")

    esperado = registro["esperado"]
    if not isinstance(esperado, dict):
        raise DatasetInvalido(f"{ubicacion}: 'esperado' debe ser un objeto")
    for campo in CAMPOS_ESPERADOS:
        if campo not in esperado:
            raise DatasetInvalido(f"{ubicacion}: 'esperado' no tiene {campo!r}")

    categoria = esperado["categoria"]
    if categoria not in CATEGORIAS_VALIDAS:
        raise DatasetInvalido(
            f"{ubicacion}: categoria {categoria!r} no esta en el enum. "
            f"Validas: {', '.join(CATEGORIAS_VALIDAS)}"
        )

    severidad = esperado["severidad"]
    if not isinstance(severidad, int) or isinstance(severidad, bool):
        raise DatasetInvalido(f"{ubicacion}: severidad debe ser un entero, no {type(severidad)}")
    if not SEVERIDAD_MIN <= severidad <= SEVERIDAD_MAX:
        raise DatasetInvalido(
            f"{ubicacion}: severidad {severidad} fuera del rango [{SEVERIDAD_MIN}, {SEVERIDAD_MAX}]"
        )

    if not isinstance(esperado["requiere_reembolso"], bool):
        raise DatasetInvalido(f"{ubicacion}: requiere_reembolso debe ser booleano")

    return CasoEval(
        id=identificador,
        entrada=str(registro["entrada"]),
        esperado=dict(esperado),
        notas=str(registro.get("notas", "")),
    )


def distribucion_de_categorias(casos: list[CasoEval]) -> dict[str, int]:
    """Cuenta casos por categoria.

    Se imprime al inicio de cada eval a proposito. Un dataset desbalanceado hace
    que la exactitud global sea enganosa: con 20 de 36 casos en 'tarifa', un
    modelo que responde siempre 'tarifa' saca 0.55 y parece decente. Ver la
    distribucion antes que la metrica es un habito que evita esa lectura.
    """
    conteo: dict[str, int] = dict.fromkeys(CATEGORIAS_VALIDAS, 0)
    for caso in casos:
        conteo[caso.categoria] += 1
    return conteo
