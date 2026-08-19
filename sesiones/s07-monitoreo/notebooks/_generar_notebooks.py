#!/usr/bin/env python
"""Genera los notebooks de la sesion 7 con nbformat, sin outputs.

Por que un generador y no notebooks editados a mano: un `.ipynb` es JSON con
metadatos y outputs embebidos, y editarlo a mano produce diffs ilegibles y
conflictos de merge en cada clase. Generarlo desde un script deja el contenido en
un archivo de texto revisable en un PR y garantiza que los notebooks se publican
**sin outputs** (que es lo que exige el pre-commit del repo: los outputs traen
rutas absolutas, tokens y datos).

Uso:
    python sesiones/s07-monitoreo/notebooks/_generar_notebooks.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

AQUI = Path(__file__).resolve().parent


def md(texto: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(texto.strip("\n"))


def code(texto: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(texto.strip("\n"))


def notebook(celdas: list[nbf.NotebookNode], titulo: str) -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    nb.cells = celdas
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
        "titulo": titulo,
    }
    return nb


# =============================================================================
# 01 — Drift real: enero vs julio
# =============================================================================
NB1 = [
    md(
        """
# S07 · 01 — Drift real: enero contra julio

**Objetivo.** Medir drift sobre datos reales de la NYC TLC, con las particiones fijas
del curso, y llegar a la pregunta que no tiene respuesta automática:
*¿esto es drift que exige reentrenar, o es estacionalidad que conviene modelar?*

**Requisitos.** Haber corrido `uv run taxi data` al menos una vez (descarga y cachea
las particiones). Todo lo demás sale de `data/processed/`.

**Ruta del notebook.**

1. Cargar la referencia (2023-01..03) y dos periodos de "producción": 2023-07 y 2024-01.
2. Comparar distribuciones a ojo, con gráficas.
3. Calcular KS, chi-cuadrado, PSI y Jensen-Shannon **a mano** con `scipy`.
4. Ver por qué `p < 0.05` falla, variando `n` sobre los mismos datos.
5. Repetir el análisis con Evidently 0.7 y comparar los dos motores.
6. Decidir: ¿drift o estacionalidad? La evidencia se construye, no se copia.
7. Medir la degradación real del RMSE del modelo de enero sobre julio.
"""
    ),
    code(
        """
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 30)

from taxi import config
from taxi.features import contract as fc
from taxi.models import train
from taxi.monitoring import estadistico as est
from taxi.monitoring import reporte

print("referencia :", [p.etiqueta for p in config.PARTICIONES_TRAIN])
print("produccion :", [p.etiqueta for p in config.PARTICIONES_PRODUCCION])
print("umbral de columnas con drift:", config.UMBRAL_DRIFT_COLUMNAS)
"""
    ),
    md(
        """
## 1. Cargar los datos reales

`train.cargar_split` usa el cache de `data/processed/` si ya está materializado. La
primera vez descarga de la TLC; a partir de ahí es lectura de parquet.

Fíjate en qué se carga: **no hay ni una línea de `np.random`**. Es la diferencia
entre practicar y jugar.
"""
    ),
    code(
        """
referencia = train.cargar_split(list(config.PARTICIONES_TRAIN))
julio = train.cargar_particion(config.Particion(2023, 7))
enero_siguiente = train.cargar_particion(config.Particion(2024, 1))

for nombre, df in [
    ("referencia 2023-01..03", referencia),
    ("produccion 2023-07", julio),
    ("produccion 2024-01", enero_siguiente),
]:
    print(f"{nombre:24s} {len(df):>8,} filas")

COLUMNAS_NUM = [*fc.FEATURES_NUMERICAS, fc.TARGET_REGRESION]
COLUMNAS_CAT = list(fc.FEATURES_CATEGORICAS)
print("\\nnumericas :", COLUMNAS_NUM)
print("categoricas:", COLUMNAS_CAT)
"""
    ),
    md(
        """
## 2. Mirar antes de medir

Un test estadístico no sustituye mirar los datos. Este paso existe porque los
resúmenes numéricos esconden cambios de forma: dos distribuciones pueden tener la
misma media y ser distintas en todo lo demás.
"""
    ),
    code(
        """
resumen = pd.DataFrame(
    {
        "ref_2023Q1": referencia[COLUMNAS_NUM].mean(),
        "jul_2023": julio[COLUMNAS_NUM].mean(),
        "ene_2024": enero_siguiente[COLUMNAS_NUM].mean(),
    }
)
resumen["delta_jul_%"] = 100 * (resumen["jul_2023"] / resumen["ref_2023Q1"] - 1)
resumen["delta_ene24_%"] = 100 * (resumen["ene_2024"] / resumen["ref_2023Q1"] - 1)
resumen.round(3)
"""
    ),
    code(
        """
# Histogramas y CDF empiricas. La CDF es la que hay que mirar para el KS: el
# estadistico D es literalmente la maxima separacion vertical entre las dos curvas.
fig, ejes = plt.subplots(2, 2, figsize=(13, 8))

for eje, columna in zip(ejes[0], ["trip_distance", fc.TARGET_REGRESION]):
    limite = referencia[columna].quantile(0.99)
    bins = np.linspace(0, limite, 60)
    eje.hist(referencia[columna], bins=bins, density=True, alpha=0.55, label="ref 2023Q1")
    eje.hist(julio[columna], bins=bins, density=True, alpha=0.55, label="jul 2023")
    eje.set_title(f"{columna} — densidad")
    eje.legend()

for eje, columna in zip(ejes[1], ["trip_distance", fc.TARGET_REGRESION]):
    for etiqueta, serie in [
        ("ref 2023Q1", referencia[columna]),
        ("jul 2023", julio[columna]),
        ("ene 2024", enero_siguiente[columna]),
    ]:
        x = np.sort(serie.to_numpy())
        eje.plot(x, np.arange(1, len(x) + 1) / len(x), label=etiqueta)
    eje.set_xlim(0, referencia[columna].quantile(0.99))
    eje.set_title(f"{columna} — CDF empirica")
    eje.legend()

plt.tight_layout()
plt.show()
"""
    ),
    code(
        """
# Las categoricas: top de zonas de origen, en proporcion. Ojo con las categorias
# NUEVAS, que son las que un test categorico diluye entre las demas celdas.
top = referencia["PULocationID"].value_counts(normalize=True).head(12).index
comparacion = pd.DataFrame(
    {
        "ref_2023Q1": referencia["PULocationID"].value_counts(normalize=True).reindex(top),
        "jul_2023": julio["PULocationID"].value_counts(normalize=True).reindex(top),
        "ene_2024": enero_siguiente["PULocationID"].value_counts(normalize=True).reindex(top),
    }
).fillna(0.0)
comparacion.plot.bar(figsize=(12, 4), title="PULocationID — proporcion de las 12 zonas mas frecuentes")
plt.tight_layout()
plt.show()

nuevas = set(enero_siguiente["PULocationID"]) - set(referencia["PULocationID"])
print("zonas presentes en 2024-01 y ausentes en la referencia:", sorted(nuevas))
"""
    ),
    md(
        """
## 3. KS, chi-cuadrado, PSI y Jensen-Shannon a mano

Ahora sin librería de monitoreo: solo `scipy`. El objetivo es que quede claro qué
hace un detector de drift por dentro, cuál es su binning y dónde se toman las
decisiones.
"""
    ),
    code(
        """
from scipy import stats

filas = []
for columna in COLUMNAS_NUM:
    ref, act = referencia[columna], julio[columna]
    resultado = stats.ks_2samp(ref.to_numpy(), act.to_numpy())
    filas.append(
        {
            "columna": columna,
            "test": "KS",
            "estadistico": resultado.statistic,
            "p_valor": resultado.pvalue,
            "efecto (D o V)": resultado.statistic,
            "psi": est.psi(ref, act),
            "js": est.distancia_jensen_shannon(ref, act),
        }
    )

for columna in COLUMNAS_CAT:
    ref, act = referencia[columna], julio[columna]
    # Se reutiliza el helper del modulo: agrupa categorias raras para que las
    # frecuencias esperadas del chi-cuadrado sean validas.
    parcial = est.evaluar_categorica(ref, act, columna=columna)
    filas.append(
        {
            "columna": columna,
            "test": "chi2",
            "estadistico": parcial.estadistico,
            "p_valor": parcial.p_valor,
            "efecto (D o V)": parcial.tamano_efecto,
            "psi": parcial.psi,
            "js": parcial.jensen_shannon,
        }
    )

pd.DataFrame(filas).set_index("columna").round(5)
"""
    ),
    md(
        """
**Lee la columna `p_valor`.** Con este volumen de datos casi todos son
indistinguibles de cero. Si el criterio fuera `p < 0.05`, la conclusión sería "drift
en todo", y eso no te dice qué hacer.

Compara ahora con la columna de efecto: ahí sí hay orden de magnitud entre columnas.
"""
    ),
    code(
        """
# El veredicto del modulo, con las tres politicas, sobre los mismos datos.
for criterio in est.CRITERIOS:
    resultado = est.detectar_drift(
        referencia,
        julio,
        columnas_numericas=COLUMNAS_NUM,
        columnas_categoricas=COLUMNAS_CAT,
        criterio=criterio,
        umbral_columnas=config.UMBRAL_DRIFT_COLUMNAS,
    )
    marcadas = [c.columna for c in resultado.con_drift]
    print(f"criterio={criterio:8s} -> {len(marcadas)}/{len(resultado.columnas)} columnas: {marcadas}")
"""
    ),
    md(
        """
## 4. Por qué `p < 0.05` falla: el mismo cambio, distinta n

Experimento controlado sobre los datos reales: se toma **la misma diferencia** entre
enero y julio y se submuestrean tamaños crecientes. El tamaño de efecto (`D`) se
mantiene estable —es una propiedad de las distribuciones— y el p-valor se derrumba,
que es una propiedad del tamaño de muestra.
"""
    ),
    code(
        """
columna = "trip_distance"
rng = np.random.default_rng(config.SEMILLA)
tamanos = [200, 1_000, 5_000, 20_000, 50_000, min(len(referencia), len(julio))]

filas = []
for n in tamanos:
    a = referencia[columna].sample(n=n, random_state=config.SEMILLA).to_numpy()
    b = julio[columna].sample(n=n, random_state=config.SEMILLA).to_numpy()
    r = stats.ks_2samp(a, b)
    filas.append(
        {
            "n": n,
            "D (efecto)": r.statistic,
            "p_valor": r.pvalue,
            "D critico 5%": 1.36 * np.sqrt(2 / n),
            "alerta si p<0.05": r.pvalue < 0.05,
            "alerta si D>=umbral": r.statistic >= est.umbral_de(columna, est.TIPO_NUMERICA),
        }
    )
pd.DataFrame(filas).set_index("n").round(6)
"""
    ),
    code(
        """
# Control negativo del experimento: dos mitades de la MISMA particion.
# Si el detector marcara drift aqui, el detector estaria roto.
mitad_a = referencia.sample(frac=0.5, random_state=1)
mitad_b = referencia.drop(mitad_a.index)

control = est.detectar_drift(
    mitad_a,
    mitad_b,
    columnas_numericas=COLUMNAS_NUM,
    columnas_categoricas=COLUMNAS_CAT,
)
print(reporte.resumen(control))
"""
    ),
    md(
        """
El control negativo es el test que más gente olvida y el único que demuestra que el
detector informa algo en lugar de solo alertar.

Ojo con lo que **no** demuestra: bajo la hipótesis nula verdadera, el criterio por
p-valor también se porta bien (su tasa de error es alfa, por construcción). Corre la
celda siguiente y compruébalo. El problema del p-valor no está en el nulo: está en
las alternativas ciertas pero triviales, que es lo que midió el barrido de `n` del
paso 4.

Y el control negativo sirve para algo más útil todavía: **calibrar los umbrales**. El
efecto medido entre dos mitades de la referencia es el ruido del instrumento. Un
umbral por debajo de ese ruido produce falsos positivos garantizados.
"""
    ),
    code(
        """
control_malo = est.detectar_drift(
    mitad_a,
    mitad_b,
    columnas_numericas=COLUMNAS_NUM,
    columnas_categoricas=COLUMNAS_CAT,
    criterio="p_valor",
)
print("falsas alarmas con criterio p_valor sobre el nulo:", [c.columna for c in control_malo.con_drift])
"""
    ),
    code(
        """
# Calibracion: ruido del instrumento vs umbral configurado vs senal observada.
base = est.linea_base_nula(
    referencia,
    columnas_numericas=COLUMNAS_NUM,
    columnas_categoricas=COLUMNAS_CAT,
)


def efectos(df_actual: pd.DataFrame) -> dict:
    resultado = est.detectar_drift(
        referencia,
        df_actual,
        columnas_numericas=COLUMNAS_NUM,
        columnas_categoricas=COLUMNAS_CAT,
    )
    return {c.columna: c.tamano_efecto for c in resultado.columnas}


calibracion = pd.DataFrame(
    {
        "ruido (nulo)": pd.Series(base),
        "umbral configurado": pd.Series(
            {
                c: est.umbral_de(
                    c, est.TIPO_NUMERICA if c in COLUMNAS_NUM else est.TIPO_CATEGORICA
                )
                for c in base
            }
        ),
        "senal vs 2023-07": pd.Series(efectos(julio)),
        "senal vs 2024-01": pd.Series(efectos(enero_siguiente)),
    }
).round(4)
calibracion["umbral > ruido?"] = calibracion["umbral configurado"] > calibracion["ruido (nulo)"]
calibracion
"""
    ),
    md(
        """
Mira la fila de `PU_DO`. El par origen-destino tiene miles de niveles, y la V de
Cramér tiene **sesgo positivo** cuando hay muchas celdas con conteos bajos: sobre dos
mitades del mismo mes marca un efecto de ~0.12, aunque ahí no pasa absolutamente
nada. Un umbral de 0.10 para esa columna —que es el default razonable para una
categórica— habría alertado sobre datos idénticos.

Por eso `UMBRALES_POR_FEATURE` lleva 0.15 para `PU_DO`: **el umbral se fijó después
de medir el ruido, no antes**. Ese orden es la diferencia entre un umbral defendible
y un número copiado de un blog. Está documentado en
[ADR 003](../../../docs/adr/003-umbrales-de-drift.md).
"""
    ),
    md(
        """
## 5. El mismo análisis con Evidently 0.7

La API cambió por completo respecto a la de los tutoriales que circulan. Ver la tabla
de migración en el README de la sesión (§4.2). Lo esencial:

- `from evidently import DataDefinition, Dataset, Report`
- `Dataset.from_pandas(df, data_definition=esquema)`
- `report.run(actual, referencia)` — **primero el actual**
- `snapshot.dict()`, no `as_dict()`
"""
    ),
    code(
        """
from evidently import DataDefinition, Dataset, Report
from evidently.presets import DataDriftPreset, DataSummaryPreset

esquema = DataDefinition(numerical_columns=COLUMNAS_NUM, categorical_columns=COLUMNAS_CAT)
columnas = COLUMNAS_NUM + COLUMNAS_CAT

ds_ref = Dataset.from_pandas(referencia[columnas], data_definition=esquema)
ds_act = Dataset.from_pandas(julio[columnas], data_definition=esquema)

report = Report([DataDriftPreset(), DataSummaryPreset()], include_tests=True)
evaluacion = report.run(ds_act, ds_ref)  # (current, reference)

destino = config.REPORTS_DIR / "notebook_drift_2023Q1_vs_2023-07.html"
destino.parent.mkdir(parents=True, exist_ok=True)
evaluacion.save_html(str(destino))
print("HTML en:", destino.relative_to(config.PROJECT_ROOT))
"""
    ),
    code(
        """
bruto = evaluacion.dict()
print("claves del dict:", list(bruto.keys()))

# Asi se ve una metrica por columna. El `value` NO siempre es un p-valor: depende
# del `method`. Ver la tabla del README (seccion 4.3).
for metrica in bruto["metrics"][:4]:
    print(metrica["metric_name"], "->", metrica["value"])
"""
    ),
    code(
        """
# La traduccion a la estructura del curso vive en UNA funcion. Si Evidently cambia
# el formato otra vez, se toca solo ese archivo.
resultado_evidently = reporte.desde_evidently(
    bruto,
    columnas_numericas=COLUMNAS_NUM,
    columnas_categoricas=COLUMNAS_CAT,
    umbral_columnas=config.UMBRAL_DRIFT_COLUMNAS,
)
print(reporte.resumen(resultado_evidently))
"""
    ),
    code(
        """
# Y el check completo, que es lo que corre el CI: HTML + JSON + exit code.
from taxi.monitoring import check_drift as cd

resultado_check = cd.ejecutar_check(
    actual=(config.Particion(2023, 7),),
    mlflow_tracking=False,  # ponlo en True si tienes el servidor de MLflow arriba
)
print(cd.formatear(resultado_check))
print("\\nexit code:", resultado_check.codigo_salida)
"""
    ),
    md(
        """
## 6. La pregunta difícil: ¿drift o estacionalidad?

Aquí termina lo mecánico y empieza el juicio profesional. El detector dice "las
distribuciones cambiaron". No dice qué hacer, y las dos lecturas posibles llevan a
acciones opuestas:

| Lectura | Qué implica | Acción |
|---|---|---|
| **Drift genuino y permanente** | el mundo cambió y no va a volver | reentrenar con datos recientes |
| **Estacionalidad recurrente** | el mundo cambia todos los julios y vuelve | modelar el patrón; reentrenar no lo arregla |

Reentrenar en respuesta a un patrón estacional es perseguir la propia cola: el modelo
se ajusta a julio, llega septiembre y vuelve a "driftear". Peor: cada reentrenamiento
es un cambio en producción, con su riesgo de regresión.

**Evidencia que distingue las dos hipótesis.** Si el cambio fuera estacional, dos
eneros deberían parecerse más entre sí que un enero y un julio. Eso es comprobable
con las particiones que ya tienes.
"""
    ),
    code(
        """
def efecto_por_columna(df_a: pd.DataFrame, df_b: pd.DataFrame) -> pd.Series:
    \"\"\"Tamano de efecto por columna entre dos periodos.\"\"\"
    resultado = est.detectar_drift(
        df_a,
        df_b,
        columnas_numericas=COLUMNAS_NUM,
        columnas_categoricas=COLUMNAS_CAT,
    )
    return pd.Series({c.columna: c.tamano_efecto for c in resultado.columnas})


comparativa = pd.DataFrame(
    {
        "2023Q1 vs 2023-07 (otro mes)": efecto_por_columna(referencia, julio),
        "2023Q1 vs 2024-01 (mismo mes, +1 anio)": efecto_por_columna(referencia, enero_siguiente),
    }
).round(4)
comparativa["mas_grande"] = np.where(
    comparativa.iloc[:, 0] > comparativa.iloc[:, 1], "cambio de mes", "paso del tiempo"
)
comparativa
"""
    ),
    md(
        """
**Cómo se lee esta tabla.**

- Si el efecto contra julio es mucho mayor que contra enero de 2024, el cambio es
  **estacional**: la posición en el año pesa más que el paso del tiempo.
- Si el efecto contra 2024-01 es comparable o mayor, hay un **cambio de tendencia**
  además de la estacionalidad, y ahí sí hay razón para revisar el modelo.
- Puede pasar (y suele pasar) que la respuesta sea **distinta por feature**. Eso es
  información valiosa: dice qué features hay que modelar y cuáles hay que vigilar.

Ninguna de las tres conclusiones sale de un umbral. Sale de mirar la tabla y de saber
que en NYC hay verano.

**Ejercicio de decisión (escríbelo antes de continuar):**

1. Con la tabla anterior, ¿tu diagnóstico es estacionalidad, tendencia o mezcla?
2. Si es estacionalidad, ¿qué feature añadirías? El contrato ya tiene `hora_pickup` y
   `dia_semana_pickup`, pero **no** mes ni indicador de temporada. ¿Basta con `mes`?
   ¿Cuántos ciclos de historia necesitas en el train para que el modelo pueda
   aprenderlo?
3. ¿Qué evidencia adicional pedirías que **no** esté en estos datos? (Pista: 2022-07
   y 2024-07 existen en el portal de la TLC. Dos julios distintos convierten una
   hipótesis en una serie.)
4. Coste de equivocarse en cada dirección: ¿qué pasa si reentrenas y era
   estacionalidad? ¿Y si no reentrenas y era un cambio permanente?
"""
    ),
    code(
        """
# Opcional (requiere red): traer un julio mas para convertir la hipotesis en serie.
# Descomenta si tienes conexion. Dos julios y dos eneros son mejor evidencia que uno.
#
# julio_2024 = train.cargar_particion(config.Particion(2024, 7))
# print(efecto_por_columna(julio, julio_2024).round(4))  # julio vs julio: deberia ser bajo
"""
    ),
    md(
        """
## 7. La prueba que zanja la discusión: ¿se degradó el modelo?

Todo lo anterior mide **entradas**. Lo que importa es la calidad de las
**predicciones**. En este caso guía tenemos el lujo de tener las etiquetas de julio
(son datos históricos), así que podemos medir la degradación real. En producción,
esto solo es posible después del label lag.

Se entrena con la referencia y se evalúa en tres periodos. Mide y compara los números
que salgan; no memorices los de nadie.

Antes de ejecutar, **escribe tu predicción**: ¿cuánto peor esperas que sea el RMSE de
julio? ¿Y el de enero de 2024, un año después? Compararla con el resultado es la parte
que enseña.
"""
    ),
    code(
        """
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

pipeline = train.pipeline_lineal()
pipeline.fit(referencia[fc.FEATURES], referencia[fc.TARGET_REGRESION])

periodos = {
    "valid 2023-04 (mes siguiente)": train.cargar_valid(),
    "prod 2023-07 (verano)": julio,
    "prod 2024-01 (un anio despues)": enero_siguiente,
}

filas = []
for nombre, df in periodos.items():
    y_real = df[fc.TARGET_REGRESION]
    y_pred = pipeline.predict(df[fc.FEATURES])
    filas.append(
        {
            "periodo": nombre,
            "n": len(df),
            "rmse": root_mean_squared_error(y_real, y_pred),
            "mae": mean_absolute_error(y_real, y_pred),
            "sesgo (pred - real)": float(np.mean(y_pred - y_real)),
        }
    )

degradacion = pd.DataFrame(filas).set_index("periodo")
base = degradacion.loc["valid 2023-04 (mes siguiente)", "rmse"]
degradacion["rmse vs valid %"] = 100 * (degradacion["rmse"] / base - 1)
degradacion.round(4)
"""
    ),
    code(
        """
# Degradacion por subgrupo. El promedio esconde regresiones locales: es el mismo
# argumento del gate de promocion de S06, aplicado ahora al monitoreo.
from taxi.models import evaluate

for nombre, df in [("2023-04 (valid)", train.cargar_valid()), ("2023-07", julio), ("2024-01", enero_siguiente)]:
    y_pred = pipeline.predict(df[fc.FEATURES])
    por_subgrupo = evaluate.metricas_por_subgrupo(df, df[fc.TARGET_REGRESION], y_pred)
    solo_rmse = {k: round(v, 3) for k, v in por_subgrupo.items() if k.startswith("rmse_")}
    print(f"\\n=== {nombre} ===")
    for clave, valor in sorted(solo_rmse.items()):
        print(f"  {clave:22s} {valor}")
"""
    ),
    md(
        """
## 8. Cierre

Lo que quedó demostrado, en orden:

1. Hay drift real entre enero y julio, y no hizo falta inventarlo. También quedó claro
   que el drift real es **mucho más sutil** que el sintético: con las particiones del
   curso, el veredicto de dataset puede quedar por debajo del umbral aunque columnas
   concretas se muevan. Eso es realista, y es incómodo, que es el punto.
2. El p-valor no distingue "cambió" de "cambió lo suficiente". El tamaño de efecto sí.
3. El control negativo (dos mitades de la misma partición) valida el detector y además
   **calibra los umbrales**. Sin él, un umbral es una superstición.
4. La misma señal admite dos diagnósticos opuestos, y la evidencia para elegir se
   construye comparando periodos comparables.
5. La degradación de RMSE es la que justifica actuar, y solo está disponible después
   del label lag. Con label lag alto hay que decidir con menos información: ahí es
   donde la política de reentrenamiento escrita vale más que cualquier gráfica.

**La conclusión que suele sorprender.** Si en tu ejecución el RMSE de julio empeora
poco y el de enero de 2024 no empeora, tienes delante el caso que este curso quiere
que reconozcas: **hay drift de datos medible y no hay degradación de performance**. La
respuesta correcta ahí no es reentrenar. Es registrar el hallazgo, ajustar los
umbrales con la evidencia y seguir vigilando. Reentrenar "porque el detector se puso
rojo" es exactamente el reflejo que el monitoreo mal entendido produce.

**Siguiente:** `02-observabilidad-del-servicio.ipynb` — la otra mitad del monitoreo,
la que mide el servicio y no los datos.
"""
    ),
]


# =============================================================================
# 02 — Observabilidad del servicio
# =============================================================================
NB2 = [
    md(
        """
# S07 · 02 — Observabilidad del servicio: Prometheus de verdad

**Objetivo.** Entender qué mide Prometheus, qué tipo de métrica usar en cada caso,
cómo se calcula un p95 a partir de buckets y por qué la elección de buckets decide si
ese p95 significa algo.

**La distinción que sostiene toda la sesión:**

- **Prometheus mide el SERVICIO**: latencia, throughput, errores, saturación.
  Continuo, barato, alertas en minutos.
- **Evidently mide los DATOS y el MODELO**: distribuciones, drift, calidad. Por lotes,
  fuera del request path, alertas en horas o días.

Un dashboard verde de Prometheus **no** significa que el modelo funcione: el servicio
puede devolver basura en 8 ms con cero errores HTTP.

**Requisitos.** Nada externo: `prometheus_client` trae su propio registro en memoria y
todo este notebook corre sin levantar servidores.
"""
    ),
    code(
        """
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Summary,
    generate_latest,
)

# Registro propio, NO el global (`REGISTRY`). Motivo: registrar dos veces una
# metrica con el mismo nombre en el registro global lanza
# `Duplicated timeseries in CollectorRegistry`, y en un notebook que se re-ejecuta
# celda por celda eso pasa siempre. Un registro local se puede recrear.
registro = CollectorRegistry()
print("registro limpio:", registro)
"""
    ),
    md(
        """
## 1. Los cuatro tipos de métrica

| Tipo | Qué representa | Solo sube? | Preguntas que contesta | PromQL típico |
|---|---|---|---|---|
| **Counter** | total acumulado de eventos | Sí (monótono; se reinicia a 0 si el proceso reinicia) | ¿cuántas predicciones? ¿cuántos errores? ¿a qué ritmo? | `rate(x_total[5m])` |
| **Gauge** | valor instantáneo que sube y baja | No | ¿cuántos requests en vuelo? ¿qué versión está cargada? | `x`, `max_over_time(x[1h])` |
| **Histogram** | observaciones repartidas en buckets acumulativos | Sí (cada bucket es un counter) | ¿cuál es el p95 de latencia? ¿qué fracción bajo 100 ms? | `histogram_quantile(0.95, ...)` |
| **Summary** | cuantiles calculados **en el proceso** | Sí | igual que Histogram, pero... | no se puede agregar entre instancias |

**Por qué el curso usa Histogram y no Summary.** Los cuantiles de un `Summary` se
calculan dentro de cada proceso. Con tres réplicas de la API detrás de un balanceador
tendrías tres p95 y **no existe forma matemática de combinarlos** en el p95 global (el
promedio de tres percentiles no es un percentil). El `Histogram` expone los buckets
crudos, que sí se suman entre réplicas, y el cuantil se calcula al consultar. El
precio es que el resultado es una **interpolación**, no el valor exacto.

Regla práctica: si la métrica se va a agregar entre instancias —y en un servicio con
más de una réplica siempre se va a agregar— usa `Histogram`.
"""
    ),
    code(
        """
# Un ejemplo de cada uno, en el registro local.
peticiones = Counter(
    "demo_peticiones_total",
    "Peticiones atendidas.",
    ["ruta", "codigo"],
    registry=registro,
)
en_vuelo = Gauge("demo_en_vuelo", "Peticiones en curso.", registry=registro)
latencia = Histogram(
    "demo_latencia_segundos",
    "Latencia de la peticion, en segundos.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=registro,
)
resumen = Summary("demo_resumen_segundos", "Ejemplo de Summary.", registry=registro)

# Convenciones de nombres (son parte del contrato operativo, se consultan en PromQL):
#   - unidad base en el nombre: _segundos, nunca milisegundos;
#   - sufijo _total en los counters;
#   - labels de cardinalidad ACOTADA: decenas de valores, no miles.
print("metricas creadas")
"""
    ),
    code(
        """
import numpy as np

rng = np.random.default_rng(42)

# Trafico simulado: mezcla log-normal (el cuerpo, ~4 ms, que es el orden de una
# inferencia sklearn en CPU) mas una cola lenta (el 3% que duele). Toda
# distribucion de latencia real tiene esta forma: asimetrica y con cola larga.
muestras = np.concatenate(
    [
        rng.lognormal(mean=np.log(0.004), sigma=0.40, size=970),
        rng.lognormal(mean=np.log(0.045), sigma=0.55, size=30),
    ]
)

for segundos in muestras:
    en_vuelo.inc()
    latencia.observe(segundos)
    resumen.observe(segundos)
    peticiones.labels(ruta="/predict", codigo="200").inc()
    en_vuelo.dec()

peticiones.labels(ruta="/predict", codigo="422").inc(11)
print(f"observaciones: {len(muestras)}  media: {muestras.mean() * 1000:.1f} ms")
print(f"p50 real: {np.percentile(muestras, 50) * 1000:.1f} ms")
print(f"p95 real: {np.percentile(muestras, 95) * 1000:.1f} ms")
"""
    ),
    md(
        """
## 2. Qué expone realmente `/metrics`

El formato de exposición es texto plano. Vale la pena leerlo entero una vez: casi
todos los malentendidos sobre histogramas se resuelven mirando estas líneas.

Fíjate en tres cosas:

1. El `Histogram` genera **tres** familias de series: `_bucket`, `_sum` y `_count`.
2. Los buckets son **acumulativos**: `le="0.05"` cuenta *todas* las observaciones
   menores o iguales a 0.05, no las que caen entre 0.025 y 0.05.
3. Existe un bucket `le="+Inf"` que iguala a `_count`. Es lo que permite calcular
   fracciones.
"""
    ),
    code(
        """
texto = generate_latest(registro).decode()
for linea in texto.splitlines():
    if linea.startswith("demo_latencia") or linea.startswith("demo_peticiones"):
        print(linea)
"""
    ),
    md(
        """
## 3. Cómo se calcula un p95 a partir de buckets

`histogram_quantile` de PromQL hace exactamente esto:

1. Busca el bucket donde el conteo acumulado cruza el percentil buscado
   (`0.95 * total`).
2. **Interpola linealmente** dentro de ese bucket, asumiendo que las observaciones se
   reparten de forma uniforme entre su borde inferior y su borde superior.

De ahí se siguen dos consecuencias que hay que tener presentes al leer un dashboard:

- el p95 reportado **nunca** es exacto: es una estimación limitada por los bordes;
- si el percentil cae en un bucket muy ancho, el error puede ser enorme;
- si cae en el bucket `+Inf`, `histogram_quantile` devuelve el borde del último
  bucket finito y el valor real puede ser cualquier cosa por encima.

Vamos a implementarlo a mano y comparar con el percentil real.
"""
    ),
    code(
        """
def cuantil_desde_buckets(bordes: list[float], acumulados: list[float], q: float) -> float:
    \"\"\"Reimplementacion didactica de histogram_quantile de PromQL.

    bordes y acumulados vienen ordenados; acumulados es monotono no decreciente.
    \"\"\"
    total = acumulados[-1]
    if total == 0:
        return float("nan")
    objetivo = q * total
    anterior_borde, anterior_cuenta = 0.0, 0.0
    for borde, cuenta in zip(bordes, acumulados):
        if cuenta >= objetivo:
            if borde == float("inf"):
                # PromQL devuelve el ultimo borde finito. La cola queda invisible.
                return anterior_borde
            if cuenta == anterior_cuenta:
                return borde
            fraccion = (objetivo - anterior_cuenta) / (cuenta - anterior_cuenta)
            return anterior_borde + fraccion * (borde - anterior_borde)
        anterior_borde, anterior_cuenta = borde, cuenta
    return bordes[-1]


def leer_buckets(registro: CollectorRegistry, metrica: str) -> tuple[list[float], list[float]]:
    \"\"\"Extrae (bordes, acumulados) de un Histogram del registro.\"\"\"
    bordes, acumulados = [], []
    for familia in registro.collect():
        if familia.name != metrica:
            continue
        for muestra in familia.samples:
            if muestra.name.endswith("_bucket"):
                bordes.append(float(muestra.labels["le"]))
                acumulados.append(muestra.value)
    orden = np.argsort(bordes)
    return [bordes[i] for i in orden], [acumulados[i] for i in orden]


bordes, acumulados = leer_buckets(registro, "demo_latencia_segundos")
for q in (0.5, 0.9, 0.95, 0.99):
    estimado = cuantil_desde_buckets(bordes, acumulados, q)
    real = float(np.percentile(muestras, q * 100))
    print(
        f"p{int(q * 100):>2}  buckets: {estimado * 1000:7.1f} ms   "
        f"real: {real * 1000:7.1f} ms   error: {100 * (estimado / real - 1):+6.1f}%"
    )
"""
    ),
    md(
        """
## 4. Los buckets mal elegidos son el error más común

Los buckets por defecto de `prometheus_client` van de 5 ms a 10 s. Para una inferencia
sklearn en CPU, que vive en el orden de 1-20 ms, eso significa que **casi todo cae en
el primer bucket** y el p95 pierde toda resolución justo donde importa.

Compáralo con los buckets afinados para este servicio, que son los que están en
`taxi.api.metricas`. Mira **las dos columnas de error**, no solo la del p95: los dos
juegos de buckets comparten bordes alrededor del p95, así que ahí empatan, y la
diferencia aparece en el p50, donde los buckets por defecto tienen un solo escalón
por debajo de 5 ms. Con menos buckets (11 en lugar de 14) los afinados dan más
resolución donde vive este servicio. Ejecuta la celda y compara los números que te
salgan.
"""
    ),
    code(
        """
BUCKETS_DEFECTO = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
BUCKETS_AFINADOS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
BUCKETS_MALOS = (1.0, 5.0, 10.0)  # todo cae en el primero: el p95 no dice nada

reales = {q: float(np.percentile(muestras, q * 100)) for q in (0.5, 0.95)}
filas = []
for nombre, buckets in [
    ("por defecto", BUCKETS_DEFECTO),
    ("afinados (curso)", BUCKETS_AFINADOS),
    ("mal elegidos", BUCKETS_MALOS),
]:
    reg = CollectorRegistry()
    h = Histogram("t_segundos", "tmp", buckets=buckets, registry=reg)
    for s in muestras:
        h.observe(s)
    b, a = leer_buckets(reg, "t_segundos")
    fila = {"buckets": nombre, "n": len(buckets)}
    for q in (0.5, 0.95):
        estimado = cuantil_desde_buckets(b, a, q)
        fila[f"p{int(q * 100)}_ms"] = round(estimado * 1000, 2)
        fila[f"error_p{int(q * 100)}_%"] = round(100 * (estimado / reales[q] - 1), 1)
    filas.append(fila)

for q, valor in reales.items():
    print(f"p{int(q * 100)} real = {valor * 1000:.2f} ms")
print()
for fila in filas:
    print(fila)
"""
    ),
    md(
        """
**Cómo elegir buckets.** Tres criterios, en orden:

1. Que el **objetivo de servicio (SLO)** sea un borde exacto. Si prometes "p95 bajo 50
   ms", tiene que existir `le="0.05"`; así `sum(rate(..._bucket{le="0.05"}[5m])) /
   sum(rate(..._count[5m]))` da directamente la fracción que cumple el SLO, sin
   interpolar.
2. Espaciado aproximadamente logarítmico alrededor de la latencia típica.
3. Pocos buckets: cada uno es una serie temporal más, multiplicada por cada
   combinación de labels. 10-12 es un número razonable; 40 no.

Y un aviso: **cambiar los buckets rompe la comparabilidad histórica** del cuantil.
No es un cambio cosmético.
"""
    ),
    md(
        """
## 5. La instrumentación real del curso

Ya está escrita, en [`src/taxi/api/metricas.py`](../../../src/taxi/api/metricas.py). No
la dupliques: lee lo que hay y entiende por qué cada decisión está tomada así.
"""
    ),
    code(
        """
from taxi.api import metricas

print(metricas.__doc__.split("Convenciones")[0])
print("tipos de error declarados (conjunto CERRADO):", metricas.TIPOS_ERROR)
"""
    ),
    code(
        """
# Se simula un poco de trafico sobre las metricas REALES del servicio y se mira
# la exposicion. Cuidado: esto escribe en el registro global del proceso.
metricas.fijar_modelo("nyc-taxi-duration", "7", "models:/nyc-taxi-duration@champion")
for s in muestras[:200]:
    metricas.observar_latencia(version="7", segundos=float(s))
    metricas.registrar_prediccion(version="7", viaje_largo=bool(s > 0.02))
metricas.registrar_error("validacion")

from prometheus_client import REGISTRY

for linea in generate_latest(REGISTRY).decode().splitlines():
    if linea.startswith("taxi_") and not linea.startswith("taxi_inferencia_duracion_segundos_bucket"):
        print(linea)
"""
    ),
    md(
        """
Tres decisiones de ese módulo que merecen atención, porque son las que se olvidan en
la práctica:

1. **Pre-inicializar las series de error en 0.** Un `Counter` con labels no existe en
   `/metrics` hasta la primera llamada a `.labels(...)`. Antes del primer error,
   `rate(taxi_errores_total[5m])` no devuelve `0`: no devuelve **nada**, y el panel
   muestra "No data", que es indistinguible de "el exporter está caído".
2. **`Gauge` con `.clear()` para la info del modelo**, en lugar del tipo `Info`. Al
   promover un modelo hay que dejar de reportar la versión anterior; con `Info`
   quedarían dos series activas y las consultas por `model_version` devolverían dos
   valores.
3. **`tipo` de error como conjunto cerrado.** Usar el nombre de la excepción como
   label deja que una librería de terceros decida la cardinalidad de tus métricas, y
   además puede filtrar detalles internos a un endpoint público.
"""
    ),
    md(
        """
## 6. Del `/metrics` al dashboard

El dashboard ya está versionado como JSON y se provisiona automáticamente. No se
construye a mano en la UI de Grafana: lo que solo existe en la base de datos de
Grafana no se revisa en un PR y se pierde al reinstalar.
"""
    ),
    code(
        """
import json

from taxi.config import PROJECT_ROOT

ruta = PROJECT_ROOT / "observabilidad" / "grafana" / "dashboards" / "api-modelo.json"
dashboard = json.loads(ruta.read_text(encoding="utf-8"))
print(dashboard["title"], "| uid:", dashboard.get("uid"), "\\n")

for panel in dashboard["panels"]:
    print(f"[{panel['type']}] {panel['title']}")
    for objetivo in panel.get("targets", []) or []:
        print("    ", objetivo.get("expr"))
"""
    ),
    md(
        """
Lee esas expresiones con calma; son el vocabulario mínimo de PromQL para un servicio
de ML:

| Expresión | Qué contesta |
|---|---|
| `rate(taxi_predicciones_total[$__rate_interval])` | throughput (predicciones por segundo) |
| `histogram_quantile(0.95, sum by (le) (rate(..._bucket[...])))` | p95 de latencia. `sum by (le)` **antes** de `histogram_quantile`: agregar cuantiles ya calculados no es válido |
| `sum by (tipo) (rate(taxi_errores_total[...]))` | errores por tipo, no un total opaco |
| `sum by (clase) (rate(taxi_predicciones_total[...]))` | **prediction drift observable en tiempo real**: si la proporción de `largo` pasa de 20% a 60% de un día para otro, algo cambió en la entrada aunque la latencia siga perfecta |
| `taxi_modelo_info` | qué versión responde. Es lo que permite atribuir un cambio de latencia a un despliegue |

La cuarta fila es el puente entre las dos mitades de esta sesión: es una métrica de
Prometheus que habla del modelo, no del servicio. Es barata, está disponible al
instante y **no sustituye** al check de drift; lo complementa como señal temprana.

Para levantarlo todo:

```bash
docker compose up -d          # API + Prometheus + Grafana
curl -s localhost:8000/metrics | head -40
# Grafana en localhost:3000, dashboard "API de inferencia — modelo de duracion"
```
"""
    ),
    md(
        """
## 7. Ejercicios

1. **Añade una métrica que falta.** El servicio no expone el **tamaño del lote** de
   `/predict/lote`. ¿`Counter`, `Gauge` o `Histogram`? Justifica con la pregunta que
   quieres contestar ("¿cuántas filas por lote nos manda el cliente?") y añádela a
   `taxi.api.metricas`.
2. **Un SLO real.** Elige un objetivo de latencia p95 para `/predict` y verifica que
   existe un borde de bucket exacto en ese valor. Escribe la consulta PromQL que
   devuelve la fracción de requests que cumplen el SLO.
3. **Rompe la cardinalidad a propósito.** Añade `PU_DO` como label en un registro
   local, genera 2.000 valores distintos y cuenta las series con
   `len(generate_latest(reg).decode().splitlines())`. Extrapola a 265 zonas × 265
   destinos × 3 versiones de modelo y explica por qué eso tumba el servidor.
4. **Alerta.** Escribe la regla de Prometheus (`alert`, `expr`, `for`) para "el p95 de
   inferencia supera 100 ms durante 5 minutos". Piensa en el `for`: sin él, un pico de
   un scrape genera una página a las 3 a.m.
"""
    ),
]


def main() -> None:
    for nombre, celdas, titulo in [
        ("01-drift-real.ipynb", NB1, "S07 01 - Drift real"),
        ("02-observabilidad-del-servicio.ipynb", NB2, "S07 02 - Observabilidad del servicio"),
    ]:
        nb = notebook(celdas, titulo)
        nbf.validate(nb)
        destino = AQUI / nombre
        with destino.open("w", encoding="utf-8") as fh:
            nbf.write(nb, fh)
        print(f"{nombre}: {len(nb.cells)} celdas")


if __name__ == "__main__":
    main()
