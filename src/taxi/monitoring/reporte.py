"""Presentacion y traduccion del resultado de drift.

Problema que resuelve
---------------------
Tres cosas que no deben vivir dentro de la logica de deteccion:

1. **La forma del ``dict()`` de Evidently.** Es un detalle de implementacion de
   una libreria de terceros, y cambia entre versiones. En 0.6 el resumen estaba
   en ``report.as_dict()["metrics"][0]["result"]["drift_by_columns"]``; en 0.7 el
   metodo se llama ``dict()`` y devuelve
   ``{"metrics": [...], "tests": [...]}`` con la columna dentro de
   ``config["column"]``. Parsear esa estructura en cada sitio donde se necesita
   —incluido el snippet que el estudiante copia— significa que la siguiente
   version de la libreria rompe varios lugares a la vez.

   Aqui la traduccion ocurre en una sola funcion (``desde_evidently``). Si sale
   Evidently 0.8 y vuelve a mover el dict, se cambia **un archivo** y ni el check
   ni el CI ni los tests se enteran. Ese aislamiento es el patron *adapter*, y es
   la leccion de diseno del modulo: se depende de la interfaz que uno controla,
   no de la que controla el proveedor.

2. **El formato de consola.** Un check que imprime un dict de 200 lineas no se
   lee. La tabla se genera aqui.

3. **La serializacion para el CI.** El JSON es el contrato con el pipeline: un
   job posterior lee ``hay_drift`` y ``fraccion_con_drift`` sin volver a calcular
   nada y sin parsear HTML.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from taxi.monitoring.estadistico import (
    TIPO_CATEGORICA,
    TIPO_NUMERICA,
    ResultadoColumna,
    ResultadoDrift,
)

logger = logging.getLogger(__name__)

#: Tipo del ``config`` de la metrica por columna de Evidently 0.7. Se compara por
#: sufijo para no depender del prefijo con version (``evidently:metric_v2:``).
SUFIJO_VALUE_DRIFT: str = "ValueDrift"
#: Metrica agregada de Evidently con el conteo de columnas con drift.
SUFIJO_DRIFTED_COUNT: str = "DriftedColumnsCount"

#: Metodos de Evidently cuyo score ES un p-valor. Importa para el sentido de la
#: comparacion: con un p-valor hay drift si score < umbral; con una distancia
#: (Wasserstein, Jensen-Shannon), si score >= umbral. Confundirlos invierte el
#: veredicto, y es un error facil de cometer al leer el dict a mano.
METODOS_P_VALOR: frozenset[str] = frozenset(
    {
        "chisquare",
        "chi-square p_value",
        "ks",
        "k-s p_value",
        "z",
        "fisher_exact",
        "g-test",
        "t_test",
        "anderson_darling",
        "cramer_von_mises",
        "mannw",
        "ed",
        "es",
        "t_test p_value",
    }
)


# =============================================================================
# Traduccion desde Evidently
# =============================================================================
def _es(config: Mapping[str, Any], sufijo: str) -> bool:
    tipo = str(config.get("type", ""))
    return tipo.rsplit(":", 1)[-1] == sufijo


def _estado_de_tests(bruto: Mapping[str, Any]) -> dict[str, bool]:
    """Mapa ``columna -> fallo el test`` a partir de la seccion ``tests``.

    Se prefiere esta fuente sobre comparar el score con el umbral a mano: es la
    decision que Evidently mismo tomo, con el sentido de comparacion correcto
    para el metodo que uso. Solo aparece si el Report se construyo con
    ``include_tests=True``; si no esta, el fallback compara score y umbral.

    ``status`` es un enum ``TestStatus`` que hereda de ``str`` (verificado en
    0.7.21), asi que ``str(...)`` da ``"FAIL"`` o ``"SUCCESS"``. Se normaliza
    igualmente por si deja de ser un str-enum.
    """
    estado: dict[str, bool] = {}
    for test in bruto.get("tests", []) or []:
        params = (test.get("metric_config") or {}).get("params") or {}
        if not _es(params, SUFIJO_VALUE_DRIFT):
            continue
        columna = params.get("column")
        if columna is None:
            continue
        crudo = test.get("status")
        texto = getattr(crudo, "value", crudo)
        estado[str(columna)] = str(texto).upper().endswith("FAIL")
    return estado


def desde_evidently(
    bruto: Mapping[str, Any],
    *,
    columnas_numericas: Sequence[str] = (),
    columnas_categoricas: Sequence[str] = (),
    umbral_columnas: float = 0.30,
) -> ResultadoDrift:
    """Traduce el ``dict()`` de un snapshot de Evidently a la estructura interna.

    Tolerante a claves faltantes **a proposito**: una version nueva de la
    libreria que renombre o elimine un campo debe producir un resultado con menos
    detalle y un aviso visible, no una excepcion en medio del pipeline de
    monitoreo. Un monitoreo que se cae por un cambio de dependencia deja al
    sistema sin senal justo cuando menos se nota.

    Args:
        bruto: salida de ``Report.run(...).dict()``.
        columnas_numericas: para clasificar el tipo en el reporte.
        columnas_categoricas: idem.
        umbral_columnas: fraccion de columnas con drift que dispara la alerta.

    Returns:
        ``ResultadoDrift`` con ``motor="evidently"``.
    """
    avisos: list[str] = []
    metricas = bruto.get("metrics")
    if not isinstance(metricas, list):
        avisos.append(
            "el dict de Evidently no trae la clave 'metrics': la version instalada "
            "cambio el formato. Revisa taxi.monitoring.reporte.desde_evidently."
        )
        metricas = []

    fallo_por_columna = _estado_de_tests(bruto)
    numericas = set(columnas_numericas)
    categoricas = set(columnas_categoricas)
    columnas: list[ResultadoColumna] = []

    for metrica in metricas:
        if not isinstance(metrica, Mapping):
            continue
        config = metrica.get("config") or {}
        if not _es(config, SUFIJO_VALUE_DRIFT):
            continue
        nombre = config.get("column")
        if nombre is None:
            avisos.append("una metrica ValueDrift no trae 'column'; se omite")
            continue
        columna = str(nombre)
        metodo = str(config.get("method", "desconocido"))
        umbral = config.get("threshold")
        score = metrica.get("value")
        score_num = float(score) if isinstance(score, (int, float)) else None

        if columna in fallo_por_columna:
            drift = fallo_por_columna[columna]
            motivo = f"test de Evidently: {'FAIL' if drift else 'SUCCESS'} (metodo {metodo})"
        else:
            drift, motivo = _veredicto_por_score(score_num, umbral, metodo)

        if columna in numericas:
            tipo = TIPO_NUMERICA
        elif columna in categoricas:
            tipo = TIPO_CATEGORICA
        else:
            tipo = "desconocido"

        columnas.append(
            ResultadoColumna(
                columna=columna,
                tipo=tipo,
                metodo=f"evidently:{metodo}",
                drift=drift,
                motivo=motivo,
                # Evidently reporta UN score por columna. Cuando el metodo es un
                # test clasico ese score es el p-valor; cuando es una distancia,
                # es el tamano de efecto. Se rellena el campo que corresponde y
                # el otro queda en None en lugar de inventarlo.
                p_valor=score_num if metodo in METODOS_P_VALOR else None,
                tamano_efecto=None if metodo in METODOS_P_VALOR else score_num,
                nombre_efecto="" if metodo in METODOS_P_VALOR else metodo,
                umbral_efecto=float(umbral) if isinstance(umbral, (int, float)) else None,
            )
        )

    if not columnas:
        avisos.append("Evidently no reporto ninguna metrica ValueDrift")

    return ResultadoDrift(
        motor="evidently",
        criterio="evidently",
        columnas=tuple(columnas),
        umbral_columnas=umbral_columnas,
        avisos=tuple(avisos),
    )


def _veredicto_por_score(
    score: float | None,
    umbral: Any,
    metodo: str,
) -> tuple[bool, str]:
    """Fallback cuando el Report se corrio sin ``include_tests=True``."""
    if score is None or not isinstance(umbral, (int, float)):
        return False, f"sin score o sin umbral en el dict de Evidently (metodo {metodo})"
    if metodo in METODOS_P_VALOR:
        detectado = score < float(umbral)
        return detectado, f"p={score:.4g} vs alfa={float(umbral):.4g} (metodo {metodo})"
    detectado = score >= float(umbral)
    return detectado, f"score={score:.4g} vs umbral={float(umbral):.4g} (metodo {metodo})"


def columnas_con_drift_segun_evidently(bruto: Mapping[str, Any]) -> tuple[int | None, float | None]:
    """Extrae ``DriftedColumnsCount`` (conteo y fraccion) tal como lo calcula Evidently.

    Se expone para poder **contrastarla** con la fraccion que calcula el curso:
    si las dos difieren, casi siempre es porque el conjunto de columnas evaluadas
    no es el mismo (Evidently incluye el target si esta en el DataDefinition).
    Descubrir eso comparando dos numeros es mas rapido que leer el HTML.
    """
    for metrica in bruto.get("metrics", []) or []:
        if not isinstance(metrica, Mapping):
            continue
        if not _es(metrica.get("config") or {}, SUFIJO_DRIFTED_COUNT):
            continue
        valor = metrica.get("value")
        if isinstance(valor, Mapping):
            cuenta = valor.get("count")
            fraccion = valor.get("share")
            return (
                int(cuenta) if isinstance(cuenta, (int, float)) else None,
                float(fraccion) if isinstance(fraccion, (int, float)) else None,
            )
    return None, None


# =============================================================================
# Presentacion
# =============================================================================
_ENCABEZADOS: tuple[str, ...] = (
    "columna",
    "tipo",
    "metodo",
    "estadistico",
    "p_valor",
    "efecto",
    "umbral",
    "psi",
    "js",
    "drift",
)


def _celda(valor: object) -> str:
    if valor is None:
        return "-"
    if isinstance(valor, bool):
        return "SI" if valor else "no"
    if isinstance(valor, float):
        return f"{valor:.4g}"
    return str(valor)


def tabla(resultado: ResultadoDrift) -> str:
    """Tabla de ancho fijo con una fila por columna evaluada.

    Se construye a mano en lugar de con `rich` o `tabulate` por una razon
    concreta: esta salida se lee tanto en una terminal como en el log de un job
    de CI, y los codigos de color de una libreria de tablas ensucian el segundo.
    """
    filas: list[tuple[str, ...]] = [_ENCABEZADOS]
    for col in sorted(resultado.columnas, key=lambda c: (not c.drift, c.columna)):
        filas.append(
            (
                _celda(col.columna),
                _celda(col.tipo),
                _celda(col.metodo),
                _celda(col.estadistico),
                _celda(col.p_valor),
                _celda(col.tamano_efecto),
                _celda(col.umbral_efecto),
                _celda(col.psi),
                _celda(col.jensen_shannon),
                _celda(col.drift),
            )
        )

    anchos = [max(len(fila[i]) for fila in filas) for i in range(len(_ENCABEZADOS))]
    lineas = [
        "  ".join(celda.ljust(anchos[i]) for i, celda in enumerate(filas[0])),
        "  ".join("-" * ancho for ancho in anchos),
    ]
    lineas.extend(
        "  ".join(celda.ljust(anchos[i]) for i, celda in enumerate(fila)) for fila in filas[1:]
    )
    return "\n".join(lineas)


def resumen(resultado: ResultadoDrift) -> str:
    """Resumen legible: tabla, motivos de las columnas con drift y veredicto."""
    partes = [
        f"Motor: {resultado.motor} | criterio: {resultado.criterio}",
        "",
        tabla(resultado),
        "",
        (
            f"Columnas con drift: {len(resultado.con_drift)}/{len(resultado.columnas)} "
            f"= {resultado.fraccion_con_drift:.0%} (umbral {resultado.umbral_columnas:.0%})"
        ),
    ]
    if resultado.con_drift:
        partes.append("")
        partes.append("Por que:")
        partes.extend(f"  - {c.columna}: {c.motivo}" for c in resultado.con_drift)
    sin_drift_explicado = [
        c for c in resultado.columnas if not c.drift and "significativo" in c.motivo
    ]
    if sin_drift_explicado:
        partes.append("")
        partes.append("Significativas pero NO relevantes (la trampa del p-valor con n grande):")
        partes.extend(f"  - {c.columna}: {c.motivo}" for c in sin_drift_explicado)
    if resultado.avisos:
        partes.append("")
        partes.append("Avisos:")
        partes.extend(f"  - {aviso}" for aviso in resultado.avisos)
    partes.append("")
    partes.append("VEREDICTO: ALERTA DE DRIFT" if resultado.hay_drift else "VEREDICTO: sin alerta")
    return "\n".join(partes)


# =============================================================================
# Serializacion
# =============================================================================
def a_json(
    resultado: ResultadoDrift,
    destino: Path,
    *,
    metadatos: Mapping[str, Any] | None = None,
) -> Path:
    """Escribe el resultado como JSON para que lo consuma el CI.

    ``sort_keys=True`` y una linea final: el archivo se puede versionar y
    diferenciar entre corridas sin ruido de ordenamiento.
    """
    contenido: dict[str, Any] = dict(resultado.a_dict())
    if metadatos:
        contenido["metadatos"] = dict(metadatos)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(contenido, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    logger.info("Resultado de drift en %s", destino)
    return destino


def metricas_para_tracking(resultado: ResultadoDrift) -> dict[str, float]:
    """Metricas planas para loguear en MLflow (o en cualquier otro backend).

    Nombres en snake_case y con prefijo por columna, que es lo que permite
    graficar la serie de una feature a lo largo de las corridas. Se filtran los
    ``None``: MLflow rechaza metricas no numericas y hacerlo aqui evita un
    try/except en el llamador.
    """
    metricas: dict[str, float] = {
        "drift_fraccion_columnas": float(resultado.fraccion_con_drift),
        "drift_columnas_con_drift": float(len(resultado.con_drift)),
        "drift_columnas_totales": float(len(resultado.columnas)),
        "drift_alerta": 1.0 if resultado.hay_drift else 0.0,
    }
    for col in resultado.columnas:
        base = col.columna.replace(" ", "_")
        for sufijo, valor in (
            ("efecto", col.tamano_efecto),
            ("p_valor", col.p_valor),
            ("psi", col.psi),
            ("js", col.jensen_shannon),
        ):
            if valor is not None:
                metricas[f"drift_{base}_{sufijo}"] = float(valor)
        metricas[f"drift_{base}_detectado"] = 1.0 if col.drift else 0.0
    return metricas
