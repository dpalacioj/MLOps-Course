#!/usr/bin/env python
"""Registra las dos versiones del prompt, las evalua y produce la tabla comparativa.

Problema que resuelve
---------------------
Se cambia una palabra del prompt, se prueban tres ejemplos, "ahora funciona
mejor" y al registry. Ese flujo es indistinguible de no tener proceso: la muestra
la eligio quien escribio el cambio, no hay linea base y no queda registro.

Este script es la alternativa con el mismo esfuerzo: dos versiones, el mismo
dataset de 36 casos, los mismos scorers, y una tabla con el delta de cada metrica.

Es literalmente el mismo patron que ``scripts/promote.py`` del caso guia, con las
piezas sustituidas:

    candidato vs @champion   ->   prompt v2 vs prompt v1
    holdout fijo (2023-05)   ->   dataset de evals (quejas.jsonl)
    RMSE                     ->   exactitud de categoria y tasa de contrato
    mover el alias           ->   mover el alias del prompt

Y por tanto la misma advertencia: el dataset de evals **no se usa para iterar el
prompt**. Si se ajusta el prompt mirando los 36 casos hasta que suban los numeros,
el dataset deja de ser un juez y se convierte en un conjunto de entrenamiento. La
practica correcta es un conjunto de desarrollo aparte para iterar y este como
holdout. En una sesion de 4 horas no hay tiempo para dos conjuntos: hay que decir
en voz alta que se esta tomando el atajo.

Modo degradado
--------------
Si no hay tracking server, el registro se omite con un aviso y la comparacion se
guarda en ``reports/llmops/comparacion-prompts.{json,md}``. En clase no siempre
hay tiempo de levantar el server, y un material que exige infraestructura para
mostrar una idea es un material que no se corre.

Uso
---
    python -m clasificador.comparar_prompts
    python -m clasificador.comparar_prompts --registrar --promover v2
    python -m clasificador.comparar_prompts --proveedor openai
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from typing import Any

from clasificador import prompts, rutas, tracing
from clasificador.evaluar import ResultadoEval, decidir, ejecutar_eval
from clasificador.proveedor import crear_proveedor
from clasificador.scorers import juez as modulo_juez

logger = logging.getLogger(__name__)

#: Metricas que se comparan, en el orden en que se leen. "Mas alto es mejor" en
#: todas menos ``intentos_promedio``, y eso se declara explicitamente abajo en
#: lugar de dejar que quien lee la tabla lo adivine.
METRICAS_COMPARADAS: tuple[str, ...] = (
    "json_valido",
    "sin_reintentos",
    "categoria_correcta",
    "severidad_exacta",
    "severidad_con_tolerancia",
    "reembolso_correcto",
    "resumen_dentro_del_limite",
    "salida_sin_pii",
    "intentos_promedio",
)

#: Metricas donde un valor menor es mejor.
MENOR_ES_MEJOR: frozenset[str] = frozenset({"intentos_promedio"})


@dataclass
class Comparacion:
    """Resultado de comparar dos versiones del prompt."""

    base: ResultadoEval
    candidato: ResultadoEval
    versiones_registradas: dict[str, str | None]

    def deltas(self) -> dict[str, tuple[float, float, float, bool]]:
        """Por metrica: (valor base, valor candidato, delta, mejora).

        Se devuelve tambien el booleano ``mejora`` en lugar de dejar que el
        consumidor deduzca el signo. Es el mismo error que ``scripts/promote.py``
        evita al marcar la convencion "negativo es mejor" en la columna de delta:
        una tabla que obliga a recordar el sentido de cada fila se lee mal.
        """
        salida: dict[str, tuple[float, float, float, bool]] = {}
        for nombre in METRICAS_COMPARADAS:
            if nombre not in self.base.metricas or nombre not in self.candidato.metricas:
                continue
            antes = self.base.metricas[nombre]
            despues = self.candidato.metricas[nombre]
            delta = despues - antes
            mejora = delta < 0 if nombre in MENOR_ES_MEJOR else delta > 0
            salida[nombre] = (antes, despues, delta, mejora)
        return salida

    def resumen(self) -> str:
        """Una linea con el veredicto de la comparacion.

        No dice "v2 es mejor" a la ligera: cuenta cuantas metricas mejoraron y
        cuantas empeoraron. Un prompt que sube la exactitud de categoria y baja la
        de reembolso no es "mejor": es un cambio con un trade-off que alguien
        tiene que decidir. Colapsar eso en un unico veredicto es como se aprueban
        regresiones.
        """
        deltas = self.deltas()
        mejoras = [n for n, (_, _, d, m) in deltas.items() if m and abs(d) > 1e-9]
        empeoras = [n for n, (_, _, d, m) in deltas.items() if not m and abs(d) > 1e-9]
        if not mejoras and not empeoras:
            return "sin diferencias medibles entre las dos versiones en este dataset"
        partes = [f"{len(mejoras)} metricas mejoran", f"{len(empeoras)} empeoran"]
        if empeoras:
            partes.append(f"revisar el trade-off en: {', '.join(empeoras)}")
        return " · ".join(partes)


def comparar(
    *,
    base: str = "v1",
    candidato: str = "v2",
    nombre_proveedor: str | None = None,
    con_juez: bool = True,
    registrar: bool = False,
    promover: str | None = None,
) -> Comparacion:
    """Evalua dos versiones del prompt con el mismo proveedor y el mismo dataset.

    Se construye **un solo** proveedor y se reusa para las dos versiones. Con dos
    instancias distintas el contador de llamadas y cualquier estado interno
    diferirian, y en un proveedor real se estarian comparando dos ventanas de
    tiempo distintas del mismo servicio. Comparar dos cosas exige que todo lo
    demas sea igual.
    """
    proveedor = crear_proveedor(nombre_proveedor)
    juez = modulo_juez.JuezFake() if con_juez else None

    registradas: dict[str, str | None] = {}
    if registrar:
        for etiqueta in (base, candidato):
            alias = prompts.ALIAS_PRODUCCION if etiqueta == promover else prompts.ALIAS_CANDIDATO
            registradas[etiqueta] = prompts.registrar(
                etiqueta,
                mensaje=f"comparacion de prompts de la sesion 8 ({etiqueta})",
                alias=alias,
            )

    resultado_base = ejecutar_eval(etiqueta_prompt=base, proveedor=proveedor, juez=juez)
    resultado_candidato = ejecutar_eval(etiqueta_prompt=candidato, proveedor=proveedor, juez=juez)
    return Comparacion(
        base=resultado_base,
        candidato=resultado_candidato,
        versiones_registradas=registradas,
    )


def escribir_comparacion(comparacion: Comparacion) -> tuple[Any, Any]:
    """Escribe la tabla comparativa en Markdown y en JSON."""
    rutas.asegurar_directorios()
    ruta_md = rutas.REPORTES_LLM_DIR / "comparacion-prompts.md"
    ruta_json = rutas.REPORTES_LLM_DIR / "comparacion-prompts.json"

    base = comparacion.base
    cand = comparacion.candidato
    deltas = comparacion.deltas()

    lineas = [
        "# Comparación de versiones del prompt",
        "",
        f"- Dataset: `datos/quejas.jsonl` ({base.n_casos} casos etiquetados a mano)",
        f"- Proveedor: `{base.proveedor}` · modelo: `{base.modelo}`",
        f"- Base: `{base.etiqueta_prompt}` (huella `{base.huella_prompt}`)",
        f"- Candidato: `{cand.etiqueta_prompt}` (huella `{cand.huella_prompt}`)",
        f"- **Veredicto:** {comparacion.resumen()}",
        "",
        "Las huellas son SHA-256 del texto del prompt. Si cambian, el resultado de",
        "abajo dejó de aplicar: es la única forma de saber que se comparó lo que dice",
        "que se comparó.",
        "",
        "| métrica | " + f"{base.etiqueta_prompt} | {cand.etiqueta_prompt} | delta | |",
        "|---|---:|---:|---:|---|",
    ]
    for nombre, (antes, despues, delta, mejora) in deltas.items():
        marca = "mejora" if mejora else "empeora"
        if abs(delta) < 1e-9:
            marca = "igual"
        sentido = " (menor es mejor)" if nombre in MENOR_ES_MEJOR else ""
        lineas.append(
            f"| {nombre}{sentido} | {antes:.3f} | {despues:.3f} | {delta:+.3f} | {marca} |"
        )

    lineas += [
        "",
        "## Costo",
        "",
        f"- `{base.etiqueta_prompt}`: {base.costo_usd:.6f} USD",
        f"- `{cand.etiqueta_prompt}`: {cand.costo_usd:.6f} USD",
        "",
        "El prompt con rúbrica es más largo y por tanto más caro **en cada llamada**,",
        "para siempre. Si la mejora en las métricas no justifica el costo por request",
        "al volumen real del negocio, el prompt corto es la decisión correcta aunque",
        "puntúe peor. Esta es la comparación que no se puede hacer sin medir las dos",
        "cosas a la vez.",
    ]

    if comparacion.versiones_registradas:
        lineas += ["", "## Registro en MLflow", ""]
        for etiqueta, version in comparacion.versiones_registradas.items():
            estado = f"version {version}" if version else "NO registrada (sin servidor MLflow)"
            lineas.append(f"- `{etiqueta}`: {estado}")
    else:
        lineas += [
            "",
            "## Registro en MLflow",
            "",
            "No se registró ninguna versión (falta `--registrar`). La comparación es",
            "válida igual: el resultado depende del texto del prompt, no de que esté",
            "en el registry. El registry sirve para *publicar* la versión ganadora.",
        ]

    if base.linea_juez or cand.linea_juez:
        lineas += [
            "",
            "## Juez",
            "",
            f"- `{base.etiqueta_prompt}`: {base.linea_juez}",
            f"- `{cand.etiqueta_prompt}`: {cand.linea_juez}",
        ]

    lineas += ["", "---", "", "Generado por `python -m clasificador.comparar_prompts`.", ""]
    ruta_md.write_text("\n".join(lineas), encoding="utf-8")

    ruta_json.write_text(
        json.dumps(
            {
                "base": base.como_dict(),
                "candidato": cand.como_dict(),
                "deltas": {
                    n: {"base": a, "candidato": c, "delta": d, "mejora": m}
                    for n, (a, c, d, m) in deltas.items()
                },
                "resumen": comparacion.resumen(),
                "versiones_registradas": comparacion.versiones_registradas,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ruta_md, ruta_json


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada."""
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--base", default="v1")
    analizador.add_argument("--candidato", default="v2")
    analizador.add_argument("--proveedor", default=None, help="fake, eco, openai")
    analizador.add_argument("--sin-juez", action="store_true")
    analizador.add_argument(
        "--registrar", action="store_true", help="registra las versiones en el Prompt Registry"
    )
    analizador.add_argument(
        "--promover",
        default=None,
        help=f"etiqueta que recibe el alias @{prompts.ALIAS_PRODUCCION} (requiere --registrar)",
    )
    analizador.add_argument("-v", "--verbose", action="store_true")
    args = analizador.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)-8s %(name)s: %(message)s",
    )
    tracing.configurar(tracing.EXPERIMENTO_EVALS)

    if args.promover and not args.registrar:
        print("--promover requiere --registrar: no se puede mover un alias sin version.")
        return 2

    comparacion = comparar(
        base=args.base,
        candidato=args.candidato,
        nombre_proveedor=args.proveedor,
        con_juez=not args.sin_juez,
        registrar=args.registrar,
        promover=args.promover,
    )
    ruta_md, ruta_json = escribir_comparacion(comparacion)

    ancho = 26
    print(f"\nDataset: {comparacion.base.n_casos} casos · proveedor: {comparacion.base.proveedor}")
    print(f"{'metrica':<{ancho}} {args.base:>8} {args.candidato:>8} {'delta':>8}")
    print("-" * (ancho + 27))
    for nombre, (antes, despues, delta, mejora) in comparacion.deltas().items():
        marca = "" if abs(delta) < 1e-9 else ("  mejora" if mejora else "  empeora")
        print(f"{nombre:<{ancho}} {antes:>8.3f} {despues:>8.3f} {delta:>+8.3f}{marca}")
    print(f"\n{comparacion.resumen()}")
    print(f"\nReporte: {ruta_md}")
    print(f"         {ruta_json}")

    # Exit 0 siempre: comparar NO es decidir. El gate es `evaluar`, y mezclarlos
    # haria que una comparacion exploratoria pudiera romper el CI.
    veredicto = decidir(comparacion.candidato)
    if not veredicto.paso:
        print(f"\nAVISO: el candidato no pasaria el gate de `evaluar`: {veredicto.motivo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
