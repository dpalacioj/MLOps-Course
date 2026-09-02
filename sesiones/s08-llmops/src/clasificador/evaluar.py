#!/usr/bin/env python
"""Corre el eval completo, loguea a MLflow, escribe el reporte y actua de gate.

Problema que resuelve
---------------------
"El prompt nuevo responde mejor" es una opinion hasta que existe un comando que
la contradiga. Este script es ese comando: mismo dataset, mismos scorers, exit
code distinto de cero si el resultado baja del umbral.

Es **el mismo patron** que ``scripts/promote.py`` del caso guia, y esa
equivalencia es el cierre conceptual de la sesion y del curso:

| Caso guia (S03-S06)              | LLMOps (S08)                        |
|----------------------------------|-------------------------------------|
| Modelo registrado, version N     | Prompt registrado, version N        |
| Holdout fijo (``PARTICION_TEST``)| Dataset de evals (``quejas.jsonl``) |
| RMSE en el holdout               | Exactitud + tasa de contrato        |
| ``MEJORA_MINIMA_RELATIVA``       | Umbrales de este modulo             |
| ``validation_status`` tag        | Tags de la version del prompt       |
| ``@champion``                    | ``@champion`` del prompt            |
| exit 1 -> el CI falla            | exit 1 -> el CI falla               |

El gate **no cambia** al pasar de ML clasico a LLMs. Cambia lo que se mide y con
que se compara; la forma de decidir es identica. Si esta parte se entendio en la
sesion 6, aqui no hay nada nuevo, y eso es exactamente lo que se quiere mostrar.

Exit codes (misma convencion que ``scripts/promote.py``)
-------------------------------------------------------
    0  el eval paso los umbrales
    1  el eval NO paso  <- el CI debe fallar aqui
    2  error de infraestructura (no se pudo cargar el dataset, la rubrica, etc.)

Distinguir 1 de 2 importa: "el prompt no es lo bastante bueno" es un resultado
exitoso del eval; "no pude medir" es una falla del eval. Confundirlos hace que un
dataset movido de sitio se lea como una regresion de calidad.

Uso
---
    python -m clasificador.evaluar                          # fake, sin red
    python -m clasificador.evaluar --prompt v1
    python -m clasificador.evaluar --proveedor openai --juez openai
    python -m clasificador.evaluar --sin-juez --umbral-categoria 0.5
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from clasificador import costos, datos, prompts, rutas, tracing
from clasificador.clasificador import ResultadoClasificacion, clasificar
from clasificador.proveedor import Proveedor, crear_proveedor
from clasificador.scorers import deterministas
from clasificador.scorers import juez as modulo_juez

logger = logging.getLogger(__name__)

EXITO = 0
FALLO_UMBRAL = 1
ERROR_INFRA = 2

#: Umbrales por defecto del gate.
#:
#: De donde salen: se calibraron contra el ``ProveedorFake``, que es la linea base
#: por reglas. Estan puestos **debajo** de lo que logra el fake para que el gate
#: pase en un fork sin credenciales y siga siendo un gate real: si alguien rompe
#: el parseo o el esquema, ``json_valido`` se hunde y el CI falla.
#:
#: Con un modelo real se suben. Un umbral que el sistema supera con holgura no
#: protege de nada; un umbral que no se puede alcanzar se acaba desactivando. La
#: practica sana es fijarlo un poco por debajo del resultado actual y subirlo
#: cuando el resultado mejora (*ratchet*), nunca al valor deseado de golpe.
UMBRAL_JSON_VALIDO: float = 1.0
UMBRAL_CATEGORIA_CORRECTA: float = 0.40
UMBRAL_SIN_PII: float = 1.0
UMBRAL_RESUMEN_EN_LIMITE: float = 1.0


@dataclass
class ResultadoEval:
    """Todo lo que produce una corrida del eval."""

    etiqueta_prompt: str
    huella_prompt: str
    proveedor: str
    modelo: str
    n_casos: int
    metricas: dict[str, float]
    #: Fallos por caso, para el reporte. Es lo unico accionable del eval: la
    #: metrica dice cuanto, la lista dice que arreglar.
    fallos: list[dict[str, Any]] = field(default_factory=list)
    calibracion_juez: dict[str, object] | None = None
    #: Kappa del juez como float tipado. Se guarda aparte de ``calibracion_juez``
    #: porque de ese dict sale como ``object`` y hay que castearlo para loguearlo;
    #: un cast es una asercion sin verificar, y aqui no hace falta.
    kappa_juez: float | None = None
    tasa_aprobacion_juez: float | None = None
    linea_juez: str = ""
    costo_usd: float = 0.0
    detalle_costos: list[str] = field(default_factory=list)
    segundos: float = 0.0
    distribucion: dict[str, int] = field(default_factory=dict)

    def como_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.etiqueta_prompt,
            "huella_prompt": self.huella_prompt,
            "proveedor": self.proveedor,
            "modelo": self.modelo,
            "n_casos": self.n_casos,
            "metricas": self.metricas,
            "calibracion_juez": self.calibracion_juez,
            "tasa_aprobacion_juez": self.tasa_aprobacion_juez,
            "juez_reportable": self.linea_juez,
            "costo_usd": round(self.costo_usd, 6),
            "detalle_costos": self.detalle_costos,
            "segundos": round(self.segundos, 3),
            "distribucion_categorias": self.distribucion,
            "fallos": self.fallos,
        }


def _evaluar_casos(
    casos: list[datos.CasoEval],
    proveedor: Proveedor,
    plantilla: prompts.Plantilla,
) -> tuple[list[ResultadoClasificacion], list[list[deterministas.Puntaje]]]:
    """Clasifica cada caso y le aplica los scorers deterministas."""
    resultados: list[ResultadoClasificacion] = []
    puntajes: list[list[deterministas.Puntaje]] = []
    for caso in casos:
        resultado = clasificar(caso.entrada, proveedor=proveedor, plantilla=plantilla)
        resultados.append(resultado)
        puntajes.append(deterministas.puntuar(resultado, caso))
    return resultados, puntajes


def _recolectar_fallos(
    casos: list[datos.CasoEval],
    resultados: list[ResultadoClasificacion],
    puntajes: list[list[deterministas.Puntaje]],
) -> list[dict[str, Any]]:
    """Un registro por caso que fallo algun scorer, con el motivo.

    Se incluye el id y no el texto completo de la queja: el reporte puede acabar
    en un artefacto de CI y las entradas de usuario no deberian propagarse mas de
    lo necesario. El mismo criterio de retencion que se aplica a las trazas en
    ``riesgos.md``.
    """
    fallos: list[dict[str, Any]] = []
    for caso, resultado, lista in zip(casos, resultados, puntajes, strict=True):
        fallidos = [p for p in lista if not p.aprobado]
        if not fallidos:
            continue
        fallos.append(
            {
                "id": caso.id,
                "scorers_fallidos": [{"nombre": p.nombre, "motivo": p.motivo} for p in fallidos],
                "obtenido": (
                    resultado.clasificacion.model_dump(mode="json")
                    if resultado.clasificacion
                    else None
                ),
                "esperado": caso.esperado,
                "intentos": resultado.intentos,
            }
        )
    return fallos


def _evaluar_juez(
    casos: list[datos.CasoEval],
    resultados: list[ResultadoClasificacion],
    juez: modulo_juez.Juez,
) -> tuple[modulo_juez.ResultadoCalibracion, float, str, list[modulo_juez.VeredictoJuez]]:
    """Calibra el juez y solo despues lo aplica al eval.

    El orden es intencional y no es negociable: **calibrar primero**. Si se aplica
    primero y se calibra despues, el numero del eval ya existe y la tentacion de
    reportarlo pese al kappa es demasiado grande. Con este orden, la calibracion
    aparece en el log antes que cualquier resultado.
    """
    calibracion = modulo_juez.calibrar(juez)
    logger.info(
        "Calibracion del juez: kappa=%.3f acuerdo=%.0f%% n=%d (%s)",
        calibracion.acuerdo.kappa,
        calibracion.acuerdo.porcentaje_acuerdo * 100,
        calibracion.acuerdo.n,
        calibracion.acuerdo.interpretacion,
    )

    veredictos: list[modulo_juez.VeredictoJuez] = []
    for caso, resultado in zip(casos, resultados, strict=True):
        if resultado.clasificacion is None:
            continue
        veredictos.append(juez.juzgar(caso.entrada, resultado.clasificacion.resumen))

    tasa = sum(v.aprobado for v in veredictos) / len(veredictos) if veredictos else 0.0
    linea = modulo_juez.resultado_reportable(calibracion, tasa)
    return calibracion, tasa, linea, veredictos


def ejecutar_eval(
    *,
    etiqueta_prompt: str = "v2",
    proveedor: Proveedor | None = None,
    juez: modulo_juez.Juez | None = None,
    ruta_dataset: Any = None,
) -> ResultadoEval:
    """Corre el eval y devuelve el resultado, sin decidir nada ni escribir nada.

    Separar "medir" de "decidir" y de "reportar" es lo que hace testeable el
    gate: los tests llaman a esta funcion y a ``decidir`` por separado, sin tocar
    el filesystem ni ``sys.exit``. Es la misma estructura de
    ``scripts/promote.py``, donde la politica vive en funciones puras.
    """
    inicio = time.perf_counter()
    casos = datos.cargar_casos(ruta_dataset)
    plantilla = prompts.cargar_prompt(etiqueta_prompt)
    proveedor = proveedor or crear_proveedor()

    resultados, puntajes = _evaluar_casos(casos, proveedor, plantilla)
    metricas = deterministas.agregar(puntajes)
    # El promedio de intentos no es un scorer (no es binario) pero es la senal
    # mas directa de un prompt que hace trabajar de mas al modelo.
    metricas["intentos_promedio"] = sum(r.intentos for r in resultados) / len(resultados)

    resultado = ResultadoEval(
        etiqueta_prompt=plantilla.etiqueta,
        huella_prompt=plantilla.huella,
        proveedor=getattr(proveedor, "nombre", "?"),
        modelo=getattr(proveedor, "modelo", "?"),
        n_casos=len(casos),
        metricas=metricas,
        fallos=_recolectar_fallos(casos, resultados, puntajes),
        distribucion=datos.distribucion_de_categorias(casos),
    )

    # El costo del juez se SUMA al del clasificador. Contabilizarlo aparte (o no
    # contabilizarlo) es como un eval con juez de LLM acaba costando el triple de
    # lo que su reporte dice.
    consumibles: list[Any] = list(resultados)
    if juez is not None:
        calibracion, tasa, linea, veredictos = _evaluar_juez(casos, resultados, juez)
        resultado.calibracion_juez = calibracion.como_dict()
        resultado.kappa_juez = calibracion.acuerdo.kappa
        resultado.tasa_aprobacion_juez = tasa
        resultado.linea_juez = linea
        consumibles += veredictos

    # Costos. Se calculan siempre: un eval sin su costo al lado invita a correr
    # el eval mas caro posible en cada PR.
    try:
        tabla = costos.cargar_precios()
        por_modelo = costos.costo_de_resultados(consumibles, tabla=tabla)
        resultado.costo_usd = sum(c.usd_total for c in por_modelo.values())
        resultado.detalle_costos = [costos.formatear_costo(c) for c in por_modelo.values()]
    except FileNotFoundError as exc:
        logger.warning("No se pudo estimar el costo: %s", exc)
        resultado.detalle_costos = [f"costo no estimado: {exc}"]

    resultado.segundos = time.perf_counter() - inicio
    return resultado


@dataclass(frozen=True)
class Veredicto:
    """Decision del gate, con el detalle de cada umbral."""

    paso: bool
    incumplimientos: list[str]

    @property
    def motivo(self) -> str:
        if self.paso:
            return "todos los umbrales se cumplieron"
        return "; ".join(self.incumplimientos)


def decidir(
    resultado: ResultadoEval,
    *,
    umbral_json: float = UMBRAL_JSON_VALIDO,
    umbral_categoria: float = UMBRAL_CATEGORIA_CORRECTA,
    umbral_pii: float = UMBRAL_SIN_PII,
    umbral_resumen: float = UMBRAL_RESUMEN_EN_LIMITE,
) -> Veredicto:
    """Compara las metricas con los umbrales. Funcion pura, por eso es testeable.

    Nota sobre el juez: **no** participa del gate por defecto. Un juez con kappa
    de 0.4 bloqueando un despliegue es peor que no tener gate, porque produce
    rechazos que nadie sabe interpretar y el equipo aprende a saltarse el gate.
    Se incorpora cuando su kappa supera el corte declarado en
    ``rubricas/juez-resumen.md``, y no antes.
    """
    incumplimientos: list[str] = []
    comprobaciones = (
        ("json_valido", umbral_json),
        ("categoria_correcta", umbral_categoria),
        ("salida_sin_pii", umbral_pii),
        ("resumen_dentro_del_limite", umbral_resumen),
    )
    for nombre, umbral in comprobaciones:
        obtenido = resultado.metricas.get(nombre)
        if obtenido is None:
            incumplimientos.append(f"{nombre}: no se midio")
        elif obtenido < umbral:
            incumplimientos.append(f"{nombre}={obtenido:.3f} < umbral {umbral:.3f}")
    return Veredicto(paso=not incumplimientos, incumplimientos=incumplimientos)


def escribir_reporte(resultado: ResultadoEval, veredicto: Veredicto) -> tuple[Any, Any]:
    """Escribe el reporte en JSON y en Markdown. Devuelve las dos rutas.

    Dos formatos porque tienen dos lectores: el JSON lo consume el script de
    comparacion de prompts y cualquier automatizacion; el Markdown lo lee una
    persona en el resumen del PR. Generar los dos del mismo objeto evita que se
    contradigan, que es lo que pasa cuando el reporte legible se escribe a mano.
    """
    rutas.asegurar_directorios()
    sufijo = f"{resultado.etiqueta_prompt}-{resultado.proveedor}".replace(":", "-")
    ruta_json = rutas.REPORTES_LLM_DIR / f"eval-{sufijo}.json"
    ruta_md = rutas.REPORTES_LLM_DIR / f"eval-{sufijo}.md"

    payload = resultado.como_dict()
    payload["veredicto"] = {"paso": veredicto.paso, "motivo": veredicto.motivo}
    ruta_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lineas = [
        f"# Eval del clasificador de quejas — prompt `{resultado.etiqueta_prompt}`",
        "",
        f"- **Veredicto:** {'PASO' if veredicto.paso else 'NO PASO'} — {veredicto.motivo}",
        f"- Proveedor: `{resultado.proveedor}` · modelo: `{resultado.modelo}`",
        f"- Huella del prompt: `{resultado.huella_prompt}`",
        f"- Casos: {resultado.n_casos}",
        f"- Costo estimado: {resultado.costo_usd:.6f} USD",
        "",
        "## Métricas",
        "",
        "| scorer | valor |",
        "|---|---:|",
    ]
    lineas += [f"| {k} | {v:.3f} |" for k, v in sorted(resultado.metricas.items())]

    if resultado.linea_juez:
        lineas += ["", "## Juez", "", resultado.linea_juez]
        if resultado.calibracion_juez:
            desacuerdos = resultado.calibracion_juez.get("desacuerdos")
            lineas += ["", f"Casos en desacuerdo con el humano: `{desacuerdos}`"]

    if resultado.detalle_costos:
        lineas += ["", "## Costos", ""] + [f"- {linea}" for linea in resultado.detalle_costos]

    if resultado.fallos:
        lineas += ["", f"## Fallos ({len(resultado.fallos)} casos)", ""]
        for fallo in resultado.fallos:
            motivos = ", ".join(
                f"{s['nombre']} ({s['motivo']})" if s["motivo"] else s["nombre"]
                for s in fallo["scorers_fallidos"]
            )
            lineas.append(f"- `{fallo['id']}`: {motivos}")

    lineas += [
        "",
        "---",
        "",
        "Generado por `python -m clasificador.evaluar`. "
        "El JSON equivalente está en el mismo directorio.",
        "",
    ]
    ruta_md.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_json, ruta_md


def loguear_en_mlflow(resultado: ResultadoEval, veredicto: Veredicto) -> None:
    """Loguea el eval como un run de MLflow, sin romper si no hay servidor.

    Nota importante que hay que decir en clase: ``mlflow.genai.evaluate()`` y
    ``mlflow.models.evaluate()`` **no son interoperables**. No comparten firma, ni
    tipo de scorers, ni forma del resultado: la primera espera un ``predict_fn``
    y una lista de ``mlflow.genai.scorers.Scorer``, la segunda un modelo y un
    ``model_type`` de ML clasico. No se puede reutilizar un scorer de una en la
    otra, ni comparar sus salidas directamente.

    Aqui se usa ``mlflow.log_metrics`` deliberadamente: son las mismas metricas y
    el mismo tracking server que en la sesion 3, lo que permite ver los runs de
    ML clasico y los de LLMOps en la misma UI. ``mlflow.genai.evaluate()`` es la
    via idiomatica para evals de GenAI (integra tracing, datasets y scorers), y
    se muestra en el material como el siguiente paso; para el eval del gate,
    ``log_metrics`` mantiene el paralelo con el gate del caso guia, que es el
    punto pedagogico de la sesion.
    """
    try:
        import mlflow

        with mlflow.start_run(run_name=f"eval-{resultado.etiqueta_prompt}"):
            mlflow.log_params(
                {
                    "prompt": resultado.etiqueta_prompt,
                    "huella_prompt": resultado.huella_prompt,
                    "proveedor": resultado.proveedor,
                    "modelo": resultado.modelo,
                    "n_casos": resultado.n_casos,
                }
            )
            mlflow.log_metrics({k: float(v) for k, v in resultado.metricas.items()})
            mlflow.log_metric("costo_usd", resultado.costo_usd)
            if resultado.kappa_juez is not None:
                mlflow.log_metric("kappa_juez", resultado.kappa_juez)
            mlflow.set_tag("veredicto", "paso" if veredicto.paso else "no_paso")
    except Exception as exc:
        logger.warning(
            "No se pudo loguear en MLflow (%s: %s). El reporte en disco ya se escribio: "
            "el eval no depende del servidor.",
            type(exc).__name__,
            exc,
        )


def _construir_juez(nombre: str | None) -> modulo_juez.Juez | None:
    """Construye el juez segun la opcion de linea de comandos."""
    if nombre in (None, "ninguno"):
        return None
    if nombre == "fake":
        return modulo_juez.JuezFake()
    return modulo_juez.JuezLLM(crear_proveedor(nombre))


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada. Devuelve el exit code en lugar de llamar a ``sys.exit``."""
    analizador = argparse.ArgumentParser(description=__doc__, add_help=True)
    analizador.add_argument("--prompt", default="v2", help="v1, v2 o una URI prompts:/...")
    analizador.add_argument("--proveedor", default=None, help="fake, eco, openai")
    analizador.add_argument("--juez", default="fake", help="fake, openai o ninguno")
    analizador.add_argument("--sin-juez", action="store_true", help="no corre el juez")
    analizador.add_argument("--umbral-categoria", type=float, default=UMBRAL_CATEGORIA_CORRECTA)
    analizador.add_argument("--umbral-json", type=float, default=UMBRAL_JSON_VALIDO)
    analizador.add_argument("--sin-mlflow", action="store_true", help="no loguea a MLflow")
    analizador.add_argument("-v", "--verbose", action="store_true")
    args = analizador.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)-8s %(name)s: %(message)s",
    )
    tracing.configurar(tracing.EXPERIMENTO_EVALS)

    try:
        proveedor = crear_proveedor(args.proveedor)
        juez = None if args.sin_juez else _construir_juez(args.juez)
        resultado = ejecutar_eval(etiqueta_prompt=args.prompt, proveedor=proveedor, juez=juez)
    except (datos.DatasetInvalido, FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR DE INFRAESTRUCTURA: {exc}", file=sys.stderr)
        print("El eval no pudo medir. Esto NO es una regresion de calidad.", file=sys.stderr)
        return ERROR_INFRA

    veredicto = decidir(
        resultado,
        umbral_json=args.umbral_json,
        umbral_categoria=args.umbral_categoria,
    )
    ruta_json, ruta_md = escribir_reporte(resultado, veredicto)
    if not args.sin_mlflow:
        loguear_en_mlflow(resultado, veredicto)

    print(f"\nEval del prompt '{resultado.etiqueta_prompt}' (huella {resultado.huella_prompt})")
    print(f"Proveedor: {resultado.proveedor} / modelo: {resultado.modelo}")
    print(f"Casos: {resultado.n_casos}   Distribucion: {resultado.distribucion}")
    print("\nMetricas:")
    for nombre, valor in sorted(resultado.metricas.items()):
        print(f"  {nombre:<28} {valor:.3f}")
    if resultado.linea_juez:
        print(f"\n{resultado.linea_juez}")
    for linea in resultado.detalle_costos:
        print(f"\n{linea}")
    print(f"\nReporte: {ruta_md}")
    print(f"         {ruta_json}")

    if veredicto.paso:
        print(f"\nPASO — {veredicto.motivo}")
        return EXITO
    print(f"\nNO PASO — {veredicto.motivo}")
    print("El CI debe fallar aqui. Revisa la lista de fallos del reporte.")
    return FALLO_UMBRAL


if __name__ == "__main__":
    sys.exit(main())
