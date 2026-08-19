"""Instrumentacion Prometheus del servicio de inferencia.

Problema que resuelve: sin metricas, la unica forma de saber que la API esta mal
es que alguien se queje. Con metricas, el servicio contesta preguntas
operativas —cuanto tarda, cuanto trafico recibe, cuanto falla, que version esta
respondiendo— de forma continua y agregable.

--------------------------------------------------------------------------------
Prometheus mide el SERVICIO. Evidently mide los DATOS y el MODELO.
--------------------------------------------------------------------------------
Es la distincion central de la sesion 7 y son dos preguntas distintas:

- **Prometheus / Grafana** responden "el servicio esta sano?": latencia p95,
  throughput, error rate, saturacion. Son series temporales numericas, baratas de
  calcular en el request path, con alertas de minutos. Un p95 de 400 ms es un
  problema de ingenieria.
- **Evidently** responde "el modelo sigue siendo valido?": drift de las features
  respecto a la referencia, drift de las predicciones, calidad de los datos y —
  cuando llegan las etiquetas— degradacion de la metrica. Se calcula por lotes,
  fuera del request path, comparando distribuciones. Un drift del 40% de las
  columnas es un problema de ciencia de datos.

Confundirlas produce dos errores tipicos: creer que un dashboard verde de
Prometheus significa que el modelo funciona (puede estar sirviendo basura en 20
ms), o intentar calcular un test KS por request (caro, y estadisticamente sin
sentido con n=1).

Puente entre ambas: el label ``model_version`` de estas metricas es lo que
permite comparar latencia y distribucion de predicciones antes y despues de una
promocion. Sin ese label, un cambio de modelo es invisible en Grafana.

--------------------------------------------------------------------------------
Convenciones de nombres
--------------------------------------------------------------------------------
Se siguen las de Prometheus, no las del idioma del curso: los nombres de metrica
son parte del contrato operativo y se consultan en PromQL.

- unidades base en el nombre (``_segundos``, no milisegundos);
- sufijo ``_total`` en los counters;
- cardinalidad acotada. Ningun label lleva id de request, zona ni timestamp: un
  label con 265 valores por 265 mas la version explota la base de series. La
  regla practica es decenas de valores por label, no miles.
"""

from __future__ import annotations

from typing import Final

from prometheus_client import Counter, Gauge, Histogram

# =============================================================================
# Metricas
# =============================================================================
#: Predicciones servidas, por version del modelo y por clase del target binario.
#: La clase se etiqueta a proposito: la distribucion de `largo` vs `corto` es una
#: senal temprana de prediction drift observable en tiempo real y sin etiquetas.
#: Si el ratio pasa de 20% a 60% de un dia para otro, algo cambio en los datos de
#: entrada aunque la latencia siga perfecta.
PREDICCIONES: Final[Counter] = Counter(
    "taxi_predicciones_total",
    "Predicciones servidas por la API.",
    ["model_version", "clase"],
)

#: Latencia de la llamada de inferencia (no del request HTTP completo).
#: Los buckets se eligen para inferencia sklearn/xgboost en CPU, que en este
#: modelo vive en el orden de 1-20 ms. Buckets mal elegidos son el error mas
#: comun: con los de por defecto (0.005 .. 10) casi todo cae en el primero y el
#: p95 deja de tener resolucion justo donde importa.
LATENCIA_INFERENCIA: Final[Histogram] = Histogram(
    "taxi_inferencia_duracion_segundos",
    "Duracion de la llamada de inferencia, en segundos.",
    ["model_version"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

#: Errores por tipo. El tipo es un conjunto CERRADO (ver ``TIPOS_ERROR``): usar
#: el nombre de la excepcion como label deja que una libreria de terceros defina
#: la cardinalidad de tus metricas, y ademas puede filtrar internals a un
#: endpoint publico.
ERRORES: Final[Counter] = Counter(
    "taxi_errores_total",
    "Errores atendidos por la API, agrupados por tipo.",
    ["tipo"],
)

#: Info metric: el valor no significa nada (siempre 1), la informacion esta en
#: los labels. Es el patron estandar de Prometheus para exponer metadatos.
#:
#: Se usa Gauge y no el tipo ``Info`` de la libreria por una razon concreta: al
#: promover un modelo hay que dejar de reportar la version vieja, y un Gauge se
#: puede limpiar con ``.clear()`` antes de fijar la nueva. Con ``Info`` quedarian
#: dos series activas y las consultas por ``model_version`` devolverian dos
#: valores.
MODELO_INFO: Final[Gauge] = Gauge(
    "taxi_modelo_info",
    "Modelo cargado por el proceso. Valor siempre 1; la informacion esta en los labels.",
    ["model_name", "model_version", "model_uri"],
)

#: Tipos de error posibles. Cerrado y en un solo lugar.
TIPOS_ERROR: Final[tuple[str, ...]] = (
    "validacion",  # 422: el request no cumple el contrato
    "modelo_no_disponible",  # 503: no hay modelo cargado
    "inferencia",  # 500: el modelo fallo al predecir
    "interno",  # 500: cualquier otra excepcion no prevista
)

# Se pre-inicializan las series de error en 0 al importar el modulo.
#
# Por que: un Counter con labels no existe en `/metrics` hasta que alguien llama
# a `.labels(...)`. Antes del primer error, `rate(taxi_errores_total[5m])` no
# devuelve "0", devuelve *nada*, y el panel de Grafana muestra "No data" — que es
# indistinguible de "el exporter esta caido". Pre-inicializar convierte la
# ausencia de errores en un cero explicito.
for _tipo in TIPOS_ERROR:
    ERRORES.labels(tipo=_tipo)


# =============================================================================
# API de instrumentacion
# =============================================================================
def fijar_modelo(nombre: str, version: str, uri: str) -> None:
    """Publica la identidad del modelo cargado y prepara sus series.

    Se llama desde el lifespan al cargar el modelo y despues de cualquier
    recarga. El ``clear()`` es lo que evita arrastrar la version anterior.
    """
    MODELO_INFO.clear()
    MODELO_INFO.labels(model_name=nombre, model_version=version, model_uri=uri).set(1)

    # Mismo argumento que con los errores: sin esto, el panel de latencia esta
    # vacio hasta la primera prediccion y el de distribucion por clase muestra
    # una sola clase hasta que aparezca la otra.
    LATENCIA_INFERENCIA.labels(model_version=version)
    for clase in ("largo", "corto"):
        PREDICCIONES.labels(model_version=version, clase=clase)


def registrar_prediccion(*, version: str, viaje_largo: bool, cantidad: int = 1) -> None:
    """Cuenta predicciones servidas.

    ``cantidad`` existe para los lotes: un lote de 100 son 100 predicciones para
    el throughput, aunque haya sido un solo request.
    """
    PREDICCIONES.labels(model_version=version, clase="largo" if viaje_largo else "corto").inc(
        cantidad
    )


def observar_latencia(*, version: str, segundos: float) -> None:
    """Registra la duracion de una llamada de inferencia.

    Se recibe en segundos aunque la API responda milisegundos: la unidad base es
    parte de la convencion de Prometheus y mezclar unidades entre metricas es una
    fuente segura de dashboards mal escalados.
    """
    LATENCIA_INFERENCIA.labels(model_version=version).observe(segundos)


def registrar_error(tipo: str) -> None:
    """Cuenta un error de uno de los tipos declarados en ``TIPOS_ERROR``."""
    if tipo not in TIPOS_ERROR:
        # No se lanza excepcion: la instrumentacion nunca debe tumbar el request
        # que estaba instrumentando. Se agrupa en "interno" y sigue.
        tipo = "interno"
    ERRORES.labels(tipo=tipo).inc()
