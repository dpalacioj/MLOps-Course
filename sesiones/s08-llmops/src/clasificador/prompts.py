"""Gestion de prompts: archivos en Git como fuente de verdad, registry para publicar.

Problema que resuelve
---------------------
Un prompt es codigo: cambia el comportamiento del sistema en produccion. Si vive
en un string dentro de una funcion, o peor, en la caja de texto de una UI, se
pierden las tres cosas que la sesion 3 dio por sentadas para los modelos:

1. **Historial**: quien cambio que palabra y por que.
2. **Referencia estable**: "el prompt que atiende produccion" sin decir cual.
3. **Rollback**: volver al anterior sin reconstruir nada.

Decision de diseno: dos capas, y el orden importa
-------------------------------------------------
- **Los archivos de ``prompts/`` son la fuente de verdad.** Estan en Git, pasan
  por code review y se diffean como cualquier otro archivo. Cambiar un prompt es
  un commit.
- **El Prompt Registry de MLflow es el mecanismo de publicacion.** Da versiones
  inmutables, aliases (``@production``) y el enlace con los runs de eval.

El orden inverso —el registry como fuente de verdad y los archivos como copia—
es tentador porque la UI es comoda, y es la razon por la que muchos equipos
acaban con un prompt en produccion que no esta en ningun commit. Ese es el mismo
anti-patron que copiar el modelo con ``shutil.copytree`` en la sesion 4.

Modo degradado
--------------
``cargar_prompt`` intenta el registry y cae al archivo local si no hay servidor.
En clase esto no es opcional: levantar el tracking server para poder renderizar
un prompt es una barrera que hace que el material no se corra.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from clasificador import rutas
from clasificador.esquema import (
    CATEGORIAS_VALIDAS,
    MAX_PALABRAS_RESUMEN,
    SEVERIDAD_MAX,
    SEVERIDAD_MIN,
)

logger = logging.getLogger(__name__)

#: Nombre del prompt en el registry. Un solo nombre por tarea, igual que un solo
#: nombre de modelo registrado por problema (``taxi.config.MODELO_REGRESION``).
NOMBRE_PROMPT: Final[str] = "clasificador-quejas-taxi"

#: Alias de produccion. Se reutiliza literalmente el del caso guia
#: (``taxi.config.ALIAS_PRODUCCION`` == "champion") para que el eco sea explicito:
#: promover un prompt es la misma operacion que promover un modelo.
ALIAS_PRODUCCION: Final[str] = "champion"
ALIAS_CANDIDATO: Final[str] = "candidate"

#: Versiones locales disponibles. La clave es la etiqueta corta que usan los
#: scripts y el reporte; el valor es el archivo.
VERSIONES_LOCALES: Final[dict[str, str]] = {
    "v1": "v1-minimo.txt",
    "v2": "v2-rubrica.txt",
}

#: Placeholders estilo ``{{ variable }}``, la convencion del Prompt Registry de
#: MLflow. Se implementa el render aqui para que funcione sin servidor, pero la
#: sintaxis es la misma que espera ``PromptVersion.format()``.
_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\{\{\s*(?P<nombre>[a-zA-Z_][\w]*)\s*\}\}")


@dataclass(frozen=True)
class Plantilla:
    """Un prompt cargado, con su procedencia.

    ``procedencia`` y ``huella`` existen para que el reporte del eval pueda
    afirmar **que texto exacto** se evaluo. Un resultado de eval sin la huella del
    prompt no es reproducible: manana el archivo cambio y el numero sigue ahi,
    ahora mintiendo.
    """

    nombre: str
    etiqueta: str
    texto: str
    procedencia: str

    @property
    def huella(self) -> str:
        """SHA-256 corto del texto. Direccion de contenido del prompt."""
        return hashlib.sha256(self.texto.encode("utf-8")).hexdigest()[:12]

    @property
    def variables(self) -> tuple[str, ...]:
        """Placeholders declarados en la plantilla, en orden de aparicion."""
        vistas: list[str] = []
        for coincidencia in _PLACEHOLDER.finditer(self.texto):
            nombre = coincidencia.group("nombre")
            if nombre not in vistas:
                vistas.append(nombre)
        return tuple(vistas)

    def renderizar(self, **valores: Any) -> str:
        """Sustituye los placeholders y falla si falta alguno.

        Fallar es el punto. Un ``str.format`` con ``KeyError`` silenciado o un
        ``.replace`` parcial deja un ``{{contexto}}`` literal en el prompt que el
        modelo recibe: el sistema no se cae, simplemente responde peor y nadie
        sabe por que. Ese bug es carisimo de encontrar sin trazas.
        """
        faltantes = [v for v in self.variables if v not in valores]
        if faltantes:
            raise ValueError(
                f"faltan variables para renderizar el prompt {self.etiqueta}: "
                f"{', '.join(faltantes)}"
            )

        def sustituir(coincidencia: re.Match[str]) -> str:
            return str(valores[coincidencia.group("nombre")])

        return _PLACEHOLDER.sub(sustituir, self.texto)


def contexto_por_defecto() -> dict[str, Any]:
    """Variables del prompt derivadas del **contrato**, no escritas a mano.

    Si el enum de ``esquema.py`` gana una categoria y el prompt la lista a mano,
    el modelo nunca la usara y el eval lo reportara como fallo del modelo. Derivar
    el texto del contrato elimina esa clase de desincronizacion, que es de las
    mas comunes y de las mas confusas de depurar.
    """
    return {
        "categorias": ", ".join(CATEGORIAS_VALIDAS),
        "max_palabras": MAX_PALABRAS_RESUMEN,
        "severidad_min": SEVERIDAD_MIN,
        "severidad_max": SEVERIDAD_MAX,
    }


def ruta_de(etiqueta: str) -> Path:
    """Ruta del archivo de la version local indicada."""
    if etiqueta not in VERSIONES_LOCALES:
        raise KeyError(
            f"version de prompt desconocida: {etiqueta!r}. "
            f"Disponibles: {', '.join(sorted(VERSIONES_LOCALES))}"
        )
    return rutas.PROMPTS_DIR / VERSIONES_LOCALES[etiqueta]


def cargar_local(etiqueta: str = "v2") -> Plantilla:
    """Carga una version del prompt desde ``prompts/``. Nunca toca la red."""
    ruta = ruta_de(etiqueta)
    if not ruta.is_file():
        raise FileNotFoundError(f"no existe el archivo de prompt: {ruta}")
    return Plantilla(
        nombre=NOMBRE_PROMPT,
        etiqueta=etiqueta,
        texto=ruta.read_text(encoding="utf-8").strip(),
        procedencia=f"archivo:{ruta.name}",
    )


def registrar(
    etiqueta: str,
    *,
    mensaje: str | None = None,
    alias: str | None = None,
) -> str | None:
    """Registra una version local en el Prompt Registry de MLflow.

    API vigente en MLflow 3.15 (verificada contra el paquete instalado y la
    documentacion oficial)::

        version = mlflow.genai.register_prompt(name=..., template=..., commit_message=..., tags=...)
        mlflow.genai.set_prompt_alias(name=..., alias="champion", version=version.version)
        plantilla = mlflow.genai.load_prompt("prompts:/<nombre>@champion")

    Returns:
        El numero de version registrada, o ``None`` si no habia servidor. Devolver
        ``None`` en lugar de propagar es la misma decision que
        ``registry.version_por_alias``: "no hay servidor" es un estado esperado en
        clase, y quien llama decide que hacer.
    """
    plantilla = cargar_local(etiqueta)
    try:
        import mlflow
        import mlflow.genai as genai

        from clasificador import tracing

        # Destino EXPLICITO. Sin esto, register_prompt escribe en el ./mlflow.db
        # del caso guia (ver tracing.uri_registry).
        mlflow.set_tracking_uri(tracing.uri_registry())
        mlflow.set_registry_uri(tracing.uri_registry())

        version = genai.register_prompt(
            name=NOMBRE_PROMPT,
            template=plantilla.texto,
            commit_message=mensaje or f"version local {etiqueta} ({plantilla.huella})",
            # Los tags son la evidencia de procedencia: permiten volver del
            # registry al commit. Sin ellos, una version del registry es un texto
            # huerfano.
            tags={
                "etiqueta_local": etiqueta,
                "archivo": VERSIONES_LOCALES[etiqueta],
                "huella_sha256": plantilla.huella,
                "sesion": "s08",
            },
        )
        numero = str(version.version)
        if alias:
            genai.set_prompt_alias(name=NOMBRE_PROMPT, alias=alias, version=int(numero))
            logger.info("Prompt %s@%s -> version %s", NOMBRE_PROMPT, alias, numero)
        return numero
    except Exception as exc:
        logger.warning(
            "No se pudo registrar el prompt %s (%s: %s). "
            "Se sigue con el archivo local; el material no depende del servidor.",
            etiqueta,
            type(exc).__name__,
            exc,
        )
        return None


def cargar_prompt(referencia: str = "v2") -> Plantilla:
    """Carga un prompt del registry o del disco, en ese orden de preferencia.

    Args:
        referencia: una etiqueta local (``"v1"``, ``"v2"``) o una URI del
            registry (``"prompts:/clasificador-quejas-taxi@champion"``).

    En produccion la referencia deberia ser **siempre** una URI del registry con
    alias: es lo que permite cambiar el prompt sin redeployar. En clase la
    etiqueta local es lo que permite avanzar sin infraestructura. Los dos caminos
    conviven aqui para que la diferencia entre ambos sea visible en lugar de
    quedar escondida en un ``if`` de configuracion.
    """
    if not referencia.startswith("prompts:/"):
        return cargar_local(referencia)

    try:
        import mlflow
        import mlflow.genai as genai

        from clasificador import tracing

        mlflow.set_tracking_uri(tracing.uri_registry())
        mlflow.set_registry_uri(tracing.uri_registry())
        version: Any = genai.load_prompt(referencia)
        return Plantilla(
            nombre=getattr(version, "name", NOMBRE_PROMPT),
            etiqueta=f"registry:{getattr(version, 'version', '?')}",
            texto=str(version.template).strip(),
            procedencia=referencia,
        )
    except Exception as exc:
        logger.warning(
            "No se pudo cargar %s del registry (%s). Se cae al archivo local 'v2'.",
            referencia,
            type(exc).__name__,
        )
        return cargar_local("v2")
