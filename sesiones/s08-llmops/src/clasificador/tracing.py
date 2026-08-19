"""Configuracion explicita del tracing de MLflow, con modo degradado real.

Problema que resuelve
---------------------
Un LLM es una caja negra que ademas **compone**: prompt de sistema, plantilla
renderizada, llamada al modelo, parseo, reintento. Cuando el resultado es malo,
la pregunta no es "cual es el error" sino "en cual de los cinco pasos se rompio".
Sin trazas, la respuesta se busca con ``print`` y suerte. Por eso el tracing va
**primero** en la sesion: sin trazas no hay depuracion, y sin depuracion los
evals dicen que algo esta mal pero no donde.

Por que este modulo existe (hallazgo medido)
--------------------------------------------
``@mlflow.trace`` exporta la traza al tracking server. Si ``MLFLOW_TRACKING_URI``
apunta a un servidor que no esta levantado —el caso por defecto en clase y en
CI— la exportacion entra en el reintento con backoff de MLflow y **la funcion
decorada se queda colgada**. Se verifico en este repo: con el server caido, una
funcion trivial decorada con ``@mlflow.trace`` no retorno en 2 minutos.

Eso es inaceptable en dos escenarios: los tests (que deben pasar sin red) y la
clase (donde nadie quiere levantar el server en el minuto cinco). La solucion no
es quitar el decorador —es la pieza que se ensena— sino **decidir explicitamente
el destino de las trazas al arrancar**:

- ``local`` (default): backend de archivos dentro del repo. Funciona sin red y
  las trazas se pueden ver luego con ``mlflow ui``.
- ``servidor``: el tracking server del curso, en el puerto 5001.
- ``off``: ``mlflow.tracing.disable()``. El decorador queda como no-op de coste
  cero. Es el modo de los tests.

Leccion generalizable: la observabilidad no puede ser un punto de fallo de lo
observado. Un exporter sincrono contra un colector caido convierte un problema de
monitoreo en una caida de la aplicacion. En un despliegue real esto se resuelve
con exportacion asincrona y por lotes (es lo que hace el SDK de OpenTelemetry) y
con un timeout agresivo, no confiando en que el colector siempre responda.
"""

from __future__ import annotations

import logging
import os
from typing import Final

import mlflow

from clasificador import rutas

logger = logging.getLogger(__name__)

#: Nombre del experimento. Sigue la convencion ``s0X-proposito`` de
#: ``taxi.config.EXPERIMENTOS``. No se agrega a ese dict porque la sesion 8 vive
#: fuera del paquete del caso guia, pero la convencion de nombres es la misma:
#: si cada sesion inventa su formato, la UI de MLflow deja de ser navegable.
EXPERIMENTO: Final[str] = "s08-llmops-clasificador-quejas"
EXPERIMENTO_EVALS: Final[str] = "s08-llmops-evals"

#: Backend local: **SQLite**, no un directorio de archivos.
#:
#: Hallazgo verificado en mlflow 3.15.1 y que invalida bastante material publicado:
#: el backend de sistema de archivos (``file:./mlruns``, el default historico de
#: MLflow) esta en **modo mantenimiento** y ya no se limita a advertir: lanza una
#: excepcion::
#:
#:     MlflowException: The filesystem tracking backend (e.g., './mlruns') is in
#:     maintenance mode and will not receive further updates. Please migrate to a
#:     database backend (e.g., 'sqlite:///mlflow.db')...
#:
#: Se puede desactivar con ``MLFLOW_ALLOW_FILE_STORE=true``, y no se hace: optar
#: por salirse de una advertencia de deprecacion para que el material siga
#: funcionando es enseñar a acumular deuda. Se usa SQLite, que es lo que la propia
#: excepcion recomienda y lo que ya usa ``make mlflow`` en este repo.
#:
#: El nombre del archivo es distinto de ``mlflow.db`` a proposito: borrar las
#: trazas de la sesion 8 no debe borrar los runs del caso guia.
_ARCHIVO_LOCAL: Final[str] = "mlruns-llmops.db"

MODOS: Final[tuple[str, ...]] = ("local", "servidor", "off")

#: Si ``configurar()`` ya corrio. Ver ``asegurar_configurado``.
_configurado: bool = False


def modo_configurado() -> str:
    """Modo de tracing segun ``LLMOPS_TRACING``. Default: ``local``."""
    modo = (os.getenv("LLMOPS_TRACING") or "local").strip().lower()
    if modo not in MODOS:
        logger.warning("LLMOPS_TRACING=%r no es valido; se usa 'local'. Validos: %s", modo, MODOS)
        return "local"
    return modo


def configurar(experimento: str = EXPERIMENTO, modo: str | None = None) -> str:
    """Configura el destino de las trazas y devuelve el modo efectivo.

    Es idempotente y se llama al inicio de cada script de la sesion. No se hace
    en el import de ``clasificador`` a proposito: importar un modulo no deberia
    tener el efecto secundario de configurar telemetria global.

    Args:
        experimento: experimento de MLflow donde aterrizan las trazas.
        modo: fuerza el modo. ``None`` lee ``LLMOPS_TRACING``.

    Returns:
        El modo efectivo: ``"local"``, ``"servidor"`` u ``"off"``.
    """
    global _configurado
    _configurado = True
    efectivo = modo or modo_configurado()

    if efectivo == "off":
        mlflow.tracing.disable()
        logger.info("Tracing DESACTIVADO: @mlflow.trace queda como no-op.")
        return "off"

    mlflow.tracing.enable()
    if efectivo == "servidor":
        uri = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5001")
    else:
        # Anclado a la raiz del repo y no al cwd: correr el script desde otra
        # carpeta no debe crear un segundo backend vacio. ``as_posix()`` para que
        # la URI de SQLite sea valida tambien en Windows.
        ruta = (rutas.REPO_ROOT / _ARCHIVO_LOCAL).resolve()
        uri = f"sqlite:///{ruta.as_posix()}"

    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(experimento)
    logger.info("Tracing en modo '%s' -> %s (experimento %s)", efectivo, uri, experimento)
    return efectivo


def uri_registry() -> str:
    """URI del backend donde viven los prompts registrados.

    Se resuelve **explicitamente** y nunca se deja al default global de MLflow.
    Razon concreta y verificada: con ``LLMOPS_TRACING=off`` nadie llama a
    ``mlflow.set_tracking_uri``, asi que ``mlflow.genai.register_prompt`` acaba
    escribiendo en el ``./mlflow.db`` del **caso guia** — el mismo que usa
    ``make mlflow`` para los modelos de las sesiones 3 a 6. Registrar un prompt de
    la sesion 8 no debe tocar el backend del caso guia.

    Nota sobre el modo ``off``: desactivar el tracing no significa renunciar al
    registry. Son dos cosas distintas —una es telemetria ambiental, la otra es un
    acto explicito del usuario— asi que en modo ``off`` el registry cae al backend
    **local**. La alternativa (rechazar el registro) obligaria a activar el tracing
    para poder registrar un prompt, que no tiene relacion.
    """
    if modo_configurado() == "servidor":
        return os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5001")
    ruta = (rutas.REPO_ROOT / _ARCHIVO_LOCAL).resolve()
    return f"sqlite:///{ruta.as_posix()}"


def asegurar_configurado() -> None:
    """Configura el tracing si nadie lo hizo todavia. Idempotente y barato.

    Existe para cerrar una trampa concreta y verificada. Los scripts de la sesion
    llaman a ``configurar()`` al arrancar, pero un estudiante que importa
    ``clasificar`` en un notebook o en un script propio no lo hace, y entonces
    ``@mlflow.trace`` usa la configuracion global de MLflow: crea un ``mlruns/`` en
    el cwd y, si ``MLFLOW_TRACKING_URI`` apunta a un servidor caido, **se cuelga**
    en el reintento del exporter. Es decir: el camino que el estudiante toma por
    defecto es el que falla peor.

    Con esto, ``LLMOPS_TRACING`` se respeta siempre, venga la llamada de donde
    venga.

    Por que no se hace en el ``import`` del paquete: importar un modulo no deberia
    tener el efecto secundario de configurar telemetria global. Hacerlo en la
    primera llamada a la funcion instrumentada es distinto —ahi el efecto ya es
    inevitable— y mantiene los imports libres de efectos.
    """
    if not _configurado:
        configurar()


def anotar_traza(**atributos: object) -> None:
    """Agrega metadatos a la traza en curso, sin fallar si no hay ninguna.

    Sirve para colgar de la traza lo que hace falta para depurar y para facturar:
    version del prompt, modelo, numero de intentos, tokens. Sin esto la traza
    dice que se llamo al modelo pero no con que version del prompt, que es
    justamente lo que se quiere comparar entre dos ejecuciones.

    Se traga las excepciones a proposito: una anotacion de telemetria no puede
    tumbar la peticion del usuario. El mismo principio que el modo degradado.

    Se comprueba ``is_tracing_enabled()`` antes de llamar porque, con el tracing
    desactivado, ``update_current_trace`` emite un WARNING por invocacion. En un
    eval de 36 casos eso son 36 lineas de ruido que entierran la salida util. Un
    log que nadie lee porque grita demasiado es equivalente a no tener log.
    """
    try:
        from mlflow.tracing.provider import is_tracing_enabled

        if not is_tracing_enabled():
            return
        mlflow.update_current_trace(tags={k: str(v) for k, v in atributos.items()})
    except Exception as exc:  # pragma: no cover - defensa de telemetria
        logger.debug("No se pudo anotar la traza: %s", exc)


def activar_autolog() -> None:
    """Activa el autolog de OpenAI si la libreria esta instalada.

    ``mlflow.openai.autolog()`` instrumenta las llamadas del SDK sin tocar el
    codigo de la app: captura mensajes, parametros, tokens y latencia. Es la via
    de menor friccion para instrumentar codigo existente, y se complementa con
    ``@mlflow.trace`` en las funciones propias, que es lo que da los spans de la
    logica de negocio (renderizado del prompt, parseo, reintento) que el autolog
    no puede conocer.

    Sobre estandares: MLflow 3.x construye su tracing sobre OpenTelemetry, asi
    que las trazas se pueden exportar a otros backends. Las *GenAI semantic
    conventions* de OTel —los nombres canonicos de atributos como el modelo o el
    conteo de tokens— viven ahora en un repositorio propio y **siguen siendo
    experimentales**: son la direccion correcta, no una garantia de estabilidad.
    Planear una migracion sobre ellas hoy es asumir que los nombres cambian.
    """
    try:
        import openai  # noqa: F401
    except ImportError:
        logger.info("openai no instalado: se omite el autolog (el modo fake no lo necesita).")
        return
    mlflow.openai.autolog()
    logger.info("Autolog de OpenAI activado.")
