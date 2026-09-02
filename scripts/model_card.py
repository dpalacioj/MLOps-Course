#!/usr/bin/env python
"""Genera docs/model-card.md desde el modelo registrado.

Problema que resuelve
---------------------
Una model card escrita a mano es documentacion, y la documentacion escrita a
mano miente en cuanto el sistema cambia. Nadie actualiza el RMSE del markdown
cuando promueve la version 8. A los tres meses el documento dice cosas falsas
con total autoridad, que es peor que no tener documento: alguien va a tomar una
decision con esos numeros.

Esta model card se **genera**. Los numeros salen del Model Registry, los hashes
del `metadata.json` de la ingesta y el contrato de features del propio codigo
(`resumen_contrato()`). Lo unico escrito a mano es lo que no se puede derivar:
uso previsto, limitaciones y consideraciones eticas, que son juicios humanos y
deben ser explicitos.

Por que importa mas alla del papeleo: el uso NO previsto y las limitaciones son
la unica defensa contra que alguien tome un modelo entrenado en un contexto y lo
use en otro. Y desde el EU AI Act, parte de esto dejo de ser buena practica para
volverse requisito documental.

Modo degradado
--------------
El script funciona sin MLflow disponible. En clase la model card se genera antes
de levantar el server, y un script que explota porque no encuentra el tracking
server no se usa. Sin MLflow se emite la card con un aviso visible en lugar de
metricas, en vez de fallar o —peor— de inventar ceros.

Uso
---
    python scripts/model_card.py
    python scripts/model_card.py --alias champion --salida docs/model-card.md
    taxi model-card
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from taxi import config
from taxi.data.contract import resumen_contrato
from taxi.models import evaluate, registry

logger = logging.getLogger(__name__)

RUTA_SALIDA_DEFECTO = config.PROJECT_ROOT / "docs" / "model-card.md"
RUTA_METADATA = config.RAW_DIR / "metadata.json"

AVISO_SIN_MLFLOW = (
    "> **AVISO — modo degradado.** No se pudo consultar el Model Registry en "
    "`{uri}`, así que las secciones de identificación y métricas están "
    "incompletas. Esta card documenta el **contrato** del sistema (features, "
    "particiones, limitaciones), no una versión concreta del modelo. "
    "Levanta MLflow (`make mlflow`) y vuelve a generarla antes de usarla como "
    "evidencia."
)


# =============================================================================
# Recoleccion de datos
# =============================================================================
def leer_metadata_particiones() -> dict[str, dict[str, Any]]:
    """Lee ``data/raw/metadata.json``, que la ingesta escribe con el SHA-256.

    El hash es lo que hace verificable la afirmacion "el modelo se entreno con
    estos datos". Sin el, la seccion de datos de entrenamiento es una promesa;
    con el, es una comprobacion: cualquiera puede recalcular el sha256 del
    parquet y confirmarlo.
    """
    if not RUTA_METADATA.exists():
        logger.warning("No existe %s: corre `taxi data` para generarlo", RUTA_METADATA)
        return {}
    try:
        return json.loads(RUTA_METADATA.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("%s no es JSON valido", RUTA_METADATA)
        return {}


def recolectar_version(
    nombre: str,
    alias: str,
) -> tuple[dict[str, Any] | None, dict[str, float]]:
    """Consulta el registry y devuelve (info de la version, metricas del run).

    Nunca lanza: si MLflow no responde, devuelve ``(None, {})`` y el llamador
    entra en modo degradado.
    """
    try:
        with registry.fallar_rapido():
            return _consultar_registry(nombre, alias)
    except Exception as exc:
        logger.warning("MLflow no disponible (%s): %s", type(exc).__name__, exc)
        return None, {}


def _consultar_registry(
    nombre: str,
    alias: str,
) -> tuple[dict[str, Any] | None, dict[str, float]]:
    """Lee la version y sus metricas del registry. Puede lanzar."""
    cli = registry.cliente()
    mv = registry.version_por_alias(nombre, alias, cliente_mlflow=cli)
    if mv is None:
        logger.warning("No hay version con alias @%s en %s", alias, nombre)
        return None, {}
    metricas = registry.metricas_de_version(nombre, mv.version, cliente_mlflow=cli)
    info: dict[str, Any] = {
        "nombre": nombre,
        "alias": alias,
        "version": str(mv.version),
        "run_id": mv.run_id or "desconocido",
        "creada": _formatear_epoch(getattr(mv, "creation_timestamp", None)),
        "descripcion": (mv.description or "").strip(),
        "tags": dict(getattr(mv, "tags", {}) or {}),
        "uri": config.uri_modelo(nombre, alias),
    }
    return info, metricas


def _formatear_epoch(milisegundos: int | None) -> str:
    if not milisegundos:
        return "desconocida"
    return datetime.fromtimestamp(milisegundos / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


def _separar_metricas(metricas: Mapping[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    """Divide las metricas del run en globales y por subgrupo."""
    subgrupos = {
        k: v
        for k, v in metricas.items()
        if k.startswith(("rmse_hora_", "rmse_dist_", "holdout_rmse_hora_", "holdout_rmse_dist_"))
    }
    globales = {k: v for k, v in metricas.items() if k not in subgrupos and not k.startswith("n_")}
    return globales, subgrupos


# =============================================================================
# Render
# =============================================================================
# NOTA de convencion: el resto del codigo Python del repo va sin tildes para
# evitar problemas de encoding. Aqui las cadenas de contenido SI llevan tildes,
# porque no son codigo: son el texto de un documento Markdown que leen personas
# (y potencialmente un auditor). El archivo se escribe con encoding utf-8
# explicito. Los docstrings, comentarios y mensajes de log siguen sin tildes.
def _tabla(filas: Sequence[tuple[str, ...]], encabezados: tuple[str, ...]) -> str:
    if not filas:
        return "_Sin datos disponibles._\n"
    lineas = [
        "| " + " | ".join(encabezados) + " |",
        "|" + "|".join(["---"] * len(encabezados)) + "|",
    ]
    lineas += ["| " + " | ".join(f) + " |" for f in filas]
    return "\n".join(lineas) + "\n"


def _seccion_identificacion(info: dict[str, Any] | None) -> str:
    if info is None:
        return (
            "| campo | valor |\n|---|---|\n"
            f"| Nombre registrado | `{config.MODELO_REGRESION}` |\n"
            "| Versión | **no determinada** (registry no disponible) |\n"
            f"| Referencia de producción | `{config.uri_modelo()}` |\n"
        )
    filas = [
        ("Nombre registrado", f"`{info['nombre']}`"),
        ("Versión", f"**{info['version']}**"),
        ("Alias", f"`@{info['alias']}`"),
        ("URI de referencia", f"`{info['uri']}`"),
        ("Run de MLflow", f"`{info['run_id']}`"),
        ("Registrada el", info["creada"]),
        (
            f"`{config.TAG_VALIDACION}`",
            info["tags"].get(config.TAG_VALIDACION, "_ausente_"),
        ),
    ]
    if info["descripcion"]:
        filas.append(("Descripción", info["descripcion"]))
    return _tabla(filas, ("campo", "valor"))


def _seccion_datos(metadata: Mapping[str, dict[str, Any]]) -> str:
    grupos = [
        ("Entrenamiento", list(config.PARTICIONES_TRAIN)),
        ("Validación (selección de hiperparámetros)", [config.PARTICION_VALID]),
        ("Holdout (juez del gate de promoción)", [config.PARTICION_TEST]),
        ("Producción simulada (monitoreo)", list(config.PARTICIONES_PRODUCCION)),
    ]
    filas: list[tuple[str, ...]] = []
    for rol, particiones in grupos:
        for particion in particiones:
            registro = metadata.get(particion.nombre_archivo, {})
            sha = registro.get("sha256")
            filas.append(
                (
                    rol,
                    particion.etiqueta,
                    f"`{particion.nombre_archivo}`",
                    f"`{sha[:16]}...`" if sha else "_no descargada_",
                )
            )
    tabla = _tabla(filas, ("rol", "partición", "archivo", "SHA-256 (16 primeros)"))
    completo = "\n".join(
        f"- `{archivo}`: `{registro.get('sha256', 'desconocido')}`"
        for archivo, registro in sorted(metadata.items())
    )
    detalle = (
        f"\n<details><summary>SHA-256 completos</summary>\n\n{completo}\n\n</details>\n"
        if completo
        else ""
    )
    return tabla + detalle


def _seccion_contrato() -> str:
    contrato = resumen_contrato()
    filas = [(clave, ", ".join(f"`{c}`" for c in columnas)) for clave, columnas in contrato.items()]
    return _tabla(filas, ("grupo", "columnas"))


def _seccion_metricas(globales: Mapping[str, float], subgrupos: Mapping[str, float]) -> str:
    if not globales and not subgrupos:
        return (
            "_No disponibles: el registry no respondió. Las métricas de esta "
            "sección se leen del run que produjo la versión registrada._\n"
        )
    partes = ["#### Globales\n"]
    partes.append(
        _tabla(
            [(f"`{k}`", f"{v:.4f}") for k, v in sorted(globales.items())],
            ("métrica", "valor"),
        )
    )
    partes.append(
        "\n#### Por subgrupo\n\n"
        "Un RMSE global mejor puede esconder una degradación en un segmento "
        "minoritario. El gate de promoción compara estos valores entre candidato "
        "y champion y rechaza el candidato si alguno se degrada más de "
        f"{evaluate.UMBRAL_DEGRADACION_SUBGRUPO:.0%}. Los subgrupos con menos de "
        f"{evaluate.MIN_FILAS_SUBGRUPO} observaciones no se usan para decidir "
        "porque su error está dominado por el ruido de muestreo.\n\n"
    )
    partes.append(
        _tabla(
            [(f"`{k}`", f"{v:.4f}") for k, v in sorted(subgrupos.items())],
            ("subgrupo", "RMSE"),
        )
        if subgrupos
        else "_El run registrado no logueó métricas por subgrupo._\n"
    )
    franjas = ", ".join(f"`{n}` ({a}-{b} h)" for n, (a, b) in evaluate.FRANJAS_HORARIAS.items())
    rangos = ", ".join(f"`{n}` ([{a}, {b}) millas)" for n, a, b in evaluate.RANGOS_DISTANCIA)
    partes.append(f"\nDefinición de los subgrupos:\n\n- Franjas horarias: {franjas}\n")
    partes.append(f"- Rangos de distancia: {rangos}\n")
    return "".join(partes)


def construir_card(
    info: dict[str, Any] | None,
    metricas: Mapping[str, float],
    metadata: Mapping[str, dict[str, Any]],
) -> str:
    """Arma el Markdown completo de la model card."""
    globales, subgrupos = _separar_metricas(metricas)
    generada = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    aviso = "" if info else AVISO_SIN_MLFLOW.format(uri=config.MLFLOW_TRACKING_URI) + "\n\n"
    particiones_train = ", ".join(p.etiqueta for p in config.PARTICIONES_TRAIN)
    valid = config.PARTICION_VALID.etiqueta
    test = config.PARTICION_TEST.etiqueta
    # Separador de miles con espacio: el formato "," de Python es la convencion
    # anglosajona y en un documento en espanol se lee mal.
    filas_por_particion = f"{config.FILAS_POR_PARTICION:,}".replace(",", " ")

    return f"""# Model Card — {config.MODELO_REGRESION}

<!-- ARCHIVO GENERADO. No lo edites a mano: `taxi model-card` lo sobrescribe.
     Si necesitas cambiar el texto, edita scripts/model_card.py. -->

_Generada automáticamente el {generada} por `scripts/model_card.py`._

{aviso}## 1. Identificación y versión

{_seccion_identificacion(info)}
El modelo se referencia siempre por **alias**, nunca por número de versión ni por
ruta de archivo. Mover el alias es la operación de despliegue y, en sentido
inverso, la de rollback.

## 2. Uso previsto

Estimar la **duración en minutos** de un viaje en taxi verde (Green Taxi) de la
ciudad de Nueva York, a partir de la zona de origen, la zona de destino, la
distancia declarada y el momento del día.

Casos de uso contemplados:

- Mostrar un tiempo estimado de llegada (ETA) al pasajero en el momento de la
  solicitud.
- Planificación de capacidad y análisis agregado de demanda por franja horaria.
- Caso de estudio del curso de MLOps: es el objeto sobre el que se practica
  tracking, registry, promoción, despliegue y monitoreo.

## 3. Uso NO previsto

Esta sección es la más importante de la card y la que más se omite. Un modelo
usado fuera de su contexto de entrenamiento falla de forma silenciosa.

- **No es un modelo de tarificación.** No estima costo y no debe alimentar un
  cálculo de precio: no vio información de tarifas, peajes ni recargos.
- **No sirve para otra ciudad ni para otro tipo de servicio.** Fue entrenado con
  Green Taxi de Nueva York. Yellow Taxi, FHV (Uber/Lyft) y cualquier otra ciudad
  tienen distribuciones distintas de zonas, distancias y tráfico.
- **No sirve para viajes fuera del rango entrenado**: duraciones menores a
  {config.DURACION_MIN_MIN:.0f} min o mayores a {config.DURACION_MAX_MIN:.0f} min
  se excluyeron del entrenamiento, y distancias sobre 100 millas se rechazan por
  contrato.
- **No debe usarse para decisiones sobre personas**: asignación de conductores,
  evaluación de desempeño, control disciplinario o cualquier consecuencia
  laboral. El modelo no fue diseñado, medido ni auditado para eso.
- **No es un sistema en tiempo real consciente del tráfico.** No recibe estado
  actual de la vía, clima ni incidentes; ante un evento excepcional su error
  crece y el modelo no lo sabe.

## 4. Datos de entrenamiento

Fuente: **NYC Taxi and Limousine Commission (TLC) Trip Record Data**, datos
públicos. Las particiones son **fijas y del pasado** por decisión de diseño (ver
`docs/adr/001-caso-guia-y-particiones.md`): un pipeline que calcula el mes con
`datetime.now()` se rompe cuando el proveedor no ha publicado todavía.

{_seccion_datos(metadata)}
Muestreo determinista de {filas_por_particion} filas por partición con
semilla `{config.SEMILLA}`. La división es **temporal**, no aleatoria: se entrena
con meses anteriores y se evalúa con meses posteriores, porque en producción el
modelo siempre predice sobre el futuro. Un split aleatorio sobre datos temporales
mezcla meses y produce métricas optimistas que no se sostienen.

## 5. Contrato de features

{_seccion_contrato()}
Notas que evitan errores concretos:

- `trip_distance` está en **millas**, no en kilómetros. El contrato de datos
  rechaza el rango de kilómetros; es el fallo silencioso más probable de esta
  integración.
- `PULocationID` y `DOLocationID` son identificadores (1-265), no cantidades: se
  tratan como categorías.
- `PU_DO`, `hora_pickup` y `dia_semana_pickup` son **derivadas** por el pipeline.
  El consumidor envía las columnas crudas; la derivación va dentro del artefacto.

Target: `{config.MODELO_REGRESION}` predice `duration` en minutos. El target
binario `viaje_largo` (duración > {config.UMBRAL_VIAJE_LARGO_MIN:.0f} min) es un
segundo problema derivado del mismo dato, registrado como
`{config.MODELO_CLASIFICACION}`.

## 6. Métricas

Leídas del run de MLflow que produjo esta versión. El prefijo indica sobre qué
partición se midió cada una:

- `train_*` → particiones de entrenamiento ({particiones_train})
- `valid_*` → {valid}, la partición con la que se seleccionaron los hiperparámetros
- `holdout_*` → {test}, el holdout fijo. **Aparecen sólo si alguien lo evaluó
  explícitamente** (`taxi train --holdout` o el gate de promoción). Su ausencia no
  es un error: el holdout se mira lo menos posible, y cada consulta se registra.
- `mejor_iteracion` → ronda de boosting en la que actuó el early stopping; es la
  evidencia de que el early stopping opera de verdad.

{_seccion_metricas(globales, subgrupos)}
### Criterio de promoción

Un candidato reemplaza al `@{config.ALIAS_PRODUCCION}` sólo si supera los tres
criterios del gate (`scripts/promote.py`):

1. El holdout cumple el contrato de datos de Pandera.
2. `RMSE_candidato <= RMSE_champion * (1 - {config.MEJORA_MINIMA_RELATIVA:.2f})`.
   Se exige un margen y no un simple "menor que" para evitar que dos modelos
   equivalentes roten indefinidamente en producción por ruido de muestreo.
3. Ningún subgrupo se degrada más de
   {evaluate.UMBRAL_DEGRADACION_SUBGRUPO:.0%}.

## 7. Limitaciones conocidas

- **Rutas no vistas.** `PU_DO` tiene miles de valores posibles y en producción
  aparecen pares que no estaban en entrenamiento. `DictVectorizer` los ignora
  silenciosamente: la predicción se apoya sólo en distancia y hora, y su error
  es mayor. No hay señal de esto en la respuesta del modelo.
- **Distancia declarada, no recorrida.** `trip_distance` viene del taxímetro al
  cierre del viaje. Si el consumidor la estima al inicio (por ejemplo, con
  distancia en línea recta), la entrada no es la misma que el modelo vio.
- **Truncamiento del target.** Se entrenó sólo con viajes de
  {config.DURACION_MIN_MIN:.0f} a {config.DURACION_MAX_MIN:.0f} minutos. El
  modelo no puede predecir fuera de ese rango y subestima sistemáticamente los
  viajes largos reales.
- **Sin información de tráfico ni clima.** El error crece en condiciones
  atípicas, que es precisamente cuando un ETA importa más.
- **Deriva temporal.** Entrenado con datos de 2023. Cambios de tarifa, de
  patrones de movilidad o de la definición de zonas degradan el desempeño con el
  tiempo. Es el problema que se monitorea en la sesión de drift.
- **Métricas por subgrupo con poca muestra.** Los subgrupos de menos de
  {evaluate.MIN_FILAS_SUBGRUPO} observaciones se reportan pero no se usan para
  decidir; su error es demasiado ruidoso.

## 8. Consideraciones éticas

- **Sesgo geográfico.** El error no se distribuye igual entre zonas. Las zonas
  con menos viajes en el dataset tienen menos representación y peor estimación,
  y suelen ser las zonas periféricas. Si un ETA peor se traduce en menor
  disponibilidad de servicio, el modelo amplifica una desigualdad
  preexistente en lugar de ser neutral frente a ella. El monitoreo por subgrupo
  del gate es la contramedida mínima, no una solución.
- **Datos personales.** El dataset de la TLC es agregado a nivel de zona y no
  contiene identificadores de pasajero ni de conductor. No se debe enriquecer
  este modelo con datos identificables sin una evaluación de impacto previa.
- **Uso laboral.** Un ETA no es una medida de desempeño. Usarlo para evaluar
  conductores trasladaría a personas el error de un modelo que no fue validado
  para eso (ver sección 3).
- **Transparencia.** El artefacto es trazable de punta a punta: SHA-256 de los
  datos, run de MLflow, versión del registry y tag de validación. Cualquier
  predicción puede rastrearse hasta la versión exacta que la produjo.

## 9. Clasificación tentativa bajo el EU AI Act

**Clasificación propuesta: riesgo mínimo** (fuera de las categorías de riesgo
alto del Anexo III).

Razonamiento: estimar la duración de un viaje no decide sobre el acceso a
empleo, educación, crédito, servicios esenciales, migración ni justicia; no es
identificación biométrica ni infraestructura crítica en el sentido del
reglamento. No hay obligaciones de conformidad de alto riesgo aplicables, y las
de transparencia del Título IV tampoco: el sistema no interactúa como si fuera
humano ni genera contenido sintético.

Condiciones que cambiarían la clasificación:

- Si el sistema pasara a asignar turnos, rutas o ingresos a conductores, entraría
  en el ámbito de **empleo y gestión de trabajadores** (Anexo III, punto 4) y
  sería de **alto riesgo**: gestión de riesgos, gobernanza de datos,
  documentación técnica, registro de eventos, supervisión humana y evaluación de
  conformidad.
- Si se usara para decidir la prestación de un servicio público esencial, o para
  fijar precios de forma diferenciada entre grupos de personas, habría que
  reevaluarlo.

> Aviso: esta clasificación es un **ejercicio didáctico** del curso, no
> asesoramiento legal. Es una autoevaluación preliminar; una clasificación
> vinculante requiere análisis jurídico del caso de uso concreto y del rol
> (proveedor o responsable del despliegue) de quien lo opera.

## 10. Por qué aliases y no stages

```text
{registry.explicar_por_que_no_stages().rstrip()}
```

Detalle completo en `docs/adr/002-aliases-en-vez-de-stages.md`.
"""


def generar(
    *,
    nombre_modelo: str = config.MODELO_REGRESION,
    alias: str = config.ALIAS_PRODUCCION,
    salida: Path = RUTA_SALIDA_DEFECTO,
) -> tuple[Path, dict[str, Any] | None, dict[str, dict[str, Any]]]:
    """Escribe la model card y devuelve (ruta, info de version, metadata).

    Devolver ``info`` y ``metadata`` en lugar de imprimir aqui permite que tanto
    este script como ``taxi model-card`` reporten el resultado con su propio
    formato sin duplicar la generacion.
    """
    info, metricas = recolectar_version(nombre_modelo, alias)
    metadata = leer_metadata_particiones()
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(construir_card(info, metricas, metadata), encoding="utf-8")
    logger.info("Model card escrita en %s", salida)
    return salida, info, metadata


def informar(
    salida: Path,
    info: dict[str, Any] | None,
    metadata: Mapping[str, dict[str, Any]],
    *,
    alias: str = config.ALIAS_PRODUCCION,
) -> None:
    """Imprime el resultado de ``generar`` con click.secho."""
    try:
        destino = salida.relative_to(config.PROJECT_ROOT)
    except ValueError:
        destino = salida
    if info is None:
        click.secho(
            f"Generada {destino} en MODO DEGRADADO: el registry en "
            f"{config.MLFLOW_TRACKING_URI} no respondio, asi que faltan la version "
            "y las metricas. Levanta MLflow y vuelve a generarla antes de usarla "
            "como evidencia.",
            fg="yellow",
        )
    else:
        click.secho(
            f"Generada {destino} para {info['nombre']} v{info['version']} (@{alias}).",
            fg="green",
        )
    if not metadata:
        click.secho(
            f"Aviso: no se encontro {RUTA_METADATA.name}; la seccion de datos va "
            "sin SHA-256. Corre `taxi data`.",
            fg="yellow",
        )


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--modelo", "nombre_modelo", default=config.MODELO_REGRESION, show_default=True)
@click.option("--alias", default=config.ALIAS_PRODUCCION, show_default=True)
@click.option(
    "--salida",
    type=click.Path(path_type=Path),
    default=RUTA_SALIDA_DEFECTO,
    show_default=True,
    help="Ruta del Markdown a generar.",
)
@click.option("--verbose", "-v", is_flag=True, help="Log en nivel INFO.")
def main(nombre_modelo: str, alias: str, salida: Path, verbose: bool) -> None:
    """Genera la model card del modelo registrado."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)-8s %(name)s: %(message)s",
    )
    ruta, info, metadata = generar(nombre_modelo=nombre_modelo, alias=alias, salida=salida)
    informar(ruta, info, metadata, alias=alias)


if __name__ == "__main__":
    main()
