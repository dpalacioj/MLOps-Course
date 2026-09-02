#!/usr/bin/env python
"""Genera los notebooks de la sesion 2 con nbformat, sin outputs.

Por que un generador y no notebooks editados a mano: un `.ipynb` es JSON con
metadatos y outputs embebidos, y editarlo a mano produce diffs ilegibles y
conflictos de merge en cada cohorte. Un generador deja el contenido en un archivo de
texto revisable en un PR y garantiza que los notebooks se publican **sin outputs**
(lo que exige el hook de nbstripout: los outputs traen rutas absolutas y datos).

Uso:
    uv run python sesiones/s02-datos/notebooks/_generar_notebooks.py
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


# Preambulo comun: los notebooks viven tres niveles por debajo de la raiz y
# necesitan importar tanto `taxi` (src/) como `tests.conftest` (los fixtures rotos).
PREAMBULO = """
# Preambulo: hacer importables `taxi` (src/) y `tests.conftest` (los fixtures).
# En un notebook del proyecto propio esto no hace falta si el paquete esta
# instalado con `uv sync` (que es lo correcto); aqui se hace explicito para que el
# notebook funcione tambien sin instalar nada.
import sys
from pathlib import Path

RAIZ = Path.cwd()
while not (RAIZ / "pyproject.toml").exists() and RAIZ != RAIZ.parent:
    RAIZ = RAIZ.parent
for p in (str(RAIZ), str(RAIZ / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

print("raiz:", RAIZ.name)
"""


# =============================================================================
# 01 — El dolor de los datos
# =============================================================================
NB1 = [
    md(
        """
# S02 · 01 — El dolor de los datos: todo verde, todo mal

**Este es "el dolor" de la sesión 2.** No se abre Pandera hasta la sección 3.

**Objetivo.** Cambiar **una sola cosa** en el dato de entrada —`trip_distance` de
millas a kilómetros— y comprobar que el `pipeline` **no falla**: entrena, reporta un
RMSE perfectamente creíble y sirve predicciones. Después, ver qué tipo de
comprobación sí lo atrapa, y **cuál es su límite honesto**.

**Por qué importa.** Los errores de datos casi nunca lanzan excepciones. Degradan
métricas. Un `pipeline` que se cae es un problema de una tarde; un `pipeline` que
sigue funcionando con datos que cambiaron de significado es un problema que se
descubre meses después, cuando alguien pregunta por qué las predicciones no tienen
sentido.

**Requisito.** Nada. Este notebook usa los `fixtures` sintéticos deterministas de
[`tests/conftest.py`](../../../tests/conftest.py), así que **no necesita red**. La
sección 5 sí usa el parquet real: si no lo tienes, corre `make data` o salta esa
sección (el notebook lo detecta y avisa).

**Ruta del notebook.**

1. El fallo silencioso: entrenar en millas y en "km", y comparar las dos métricas.
2. Segundo acto: una categoría nueva que el `encoder` descarta sin decir nada.
3. Los tres niveles de check, y cuál atrapa cada cosa.
4. Qué va en el contrato y qué va en el test.
5. **El límite honesto**: el mismo cambio de unidades sobre el parquet **real**
   pasa el contrato. Y qué sí lo detecta (puente a la S07).
"""
    ),
    code(PREAMBULO),
    # -------------------------------------------------------------------------
    md(
        """
---

## 1. El fallo silencioso: millas contra kilómetros

Los `fixtures` de este notebook son los mismos que usa la suite de tests del
repositorio. Se **generan en código** con semilla fija, en lugar de leerse de un CSV
commiteado, por tres razones que están escritas en
[`tests/conftest.py`](../../../tests/conftest.py):

- un CSV de mil filas es **opaco**: nadie sabe qué propiedad tiene;
- se desactualiza en silencio cuando el contrato cambia;
- no explica **por qué** cada `fixture` roto está roto.

Generarlo con semilla fija da reproducibilidad bit a bit *y* documenta la intención.
"""
    ),
    code(
        """
import pandas as pd

from tests.conftest import MILLAS_A_KM, generar_crudos

# El "proveedor" nos manda datos correctos, en MILLAS (es lo que documenta la NYC TLC).
crudo_millas = generar_crudos(filas=4_000, semilla=11)

# Y un dia, sin avisar, cambia de unidad. UNA columna. Nada mas.
crudo_km = crudo_millas.copy()
crudo_km["trip_distance"] = crudo_millas["trip_distance"] * MILLAS_A_KM

comparacion = pd.DataFrame(
    {
        "millas": crudo_millas["trip_distance"].describe(),
        "km (el dato roto)": crudo_km["trip_distance"].describe(),
    }
)
print(comparacion.round(2))
print()
print("dtypes iguales:", crudo_millas.dtypes.equals(crudo_km.dtypes))
print("nulos nuevos:", int(crudo_km.isna().sum().sum() - crudo_millas.isna().sum().sum()))
print("filas iguales:", len(crudo_millas) == len(crudo_km))
"""
    ),
    md(
        """
**Mira la tabla antes de seguir.** El tipo no cambió. No apareció ningún nulo. El
número de filas es el mismo. La mediana pasó de ~3,4 a ~5,5 millas y **las dos son
plausibles para un taxi**.

No hay nada que un `try/except` pueda atrapar. No hay nada que `mypy` pueda ver: el
tipo sigue siendo `float64`. Un `float` no lleva sus unidades encima.
"""
    ),
    code(
        """
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import Ridge
from sklearn.metrics import root_mean_squared_error

from taxi.config import DURACION_MAX_MIN, DURACION_MIN_MIN
from taxi.features import contract as fc


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    # El mismo orden que taxi.data.loaders.preparar_particion, sin descargar nada.
    df = df.copy()
    delta = df[fc.COL_DROPOFF] - df[fc.COL_PICKUP]
    df[fc.TARGET_REGRESION] = delta.dt.total_seconds() / 60.0
    dentro = df[fc.TARGET_REGRESION].between(DURACION_MIN_MIN, DURACION_MAX_MIN)
    return fc.construir_features(df[dentro].reset_index(drop=True))


def entrenar_y_medir(train: pd.DataFrame, test: pd.DataFrame) -> float:
    dv = DictVectorizer()
    x_tr = dv.fit_transform(fc.a_diccionarios(train))
    x_te = dv.transform(fc.a_diccionarios(test))
    modelo = Ridge(alpha=1.0).fit(x_tr, train[fc.TARGET_REGRESION])
    return float(root_mean_squared_error(test[fc.TARGET_REGRESION], modelo.predict(x_te)))


# El conjunto de evaluacion llega SIEMPRE en millas: es el mundo real, que no cambio.
test = preparar(generar_crudos(filas=1_500, semilla=99))

rmse_ok = entrenar_y_medir(preparar(crudo_millas), test)
rmse_roto = entrenar_y_medir(preparar(crudo_km), test)

print(f"RMSE del modelo entrenado en millas : {rmse_ok:6.3f} min")
print(f"RMSE del modelo entrenado en 'km'   : {rmse_roto:6.3f} min")
print()
print(f"degradacion: {100 * (rmse_roto - rmse_ok) / rmse_ok:.1f}%")
print()
print("Ninguna excepcion. Ningun aviso. Dos numeros creibles.")
"""
    ),
    md(
        """
### Lo que acaba de pasar, y por qué es el peor caso posible

El modelo entrenado con la columna equivocada **funciona**. Predice minutos. Su RMSE
es del mismo orden que el del modelo correcto. Si lo registras en MLflow, la métrica
se ve bien. Si lo despliegas, la API responde `200` en 8 ms.

Y es un modelo que aprendió que "3,4 unidades de distancia" significa una cosa,
cuando en producción va a recibir otra.

**Mide y compara** la degradación que te salga. Después piensa en la pregunta
incómoda: *¿cuánta degradación haría falta para que alguien lo notase sin un
contrato?* Con una diferencia de un 10 % y sin nada con lo que comparar, la respuesta
honesta es que probablemente nadie.

> **La asimetría que define esta sesión.** Un fallo ruidoso cuesta una tarde de
> `debugging`. Un fallo silencioso cuesta meses de decisiones tomadas con
> predicciones malas, más el tiempo de descubrir que el problema estaba en los datos
> y no en el modelo. El contrato de datos convierte lo segundo en lo primero.
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 2. Segundo acto: la categoría nueva que desaparece

El cambio de unidades es el caso canónico, pero hay uno todavía más silencioso, y le
pasa a todo el mundo: **una categoría que no existía cuando entrenaste**.

El caso guía usa `DictVectorizer` para las features categóricas, y lo hace a
propósito (está explicado en
[`src/taxi/features/contract.py`](../../../src/taxi/features/contract.py)): el par
origen-destino `PU_DO` tiene miles de valores posibles y varios aparecen **solo** en
producción.

`DictVectorizer` ignora las claves que no vio en `fit`. Eso es el comportamiento
deseado —no queremos que la API explote porque llegó una ruta nueva— pero tiene un
precio que hay que ver con los ojos.
"""
    ),
    code(
        """
dv = DictVectorizer()
train = preparar(generar_crudos(filas=2_000, semilla=3))
dv.fit(fc.a_diccionarios(train))
print("features aprendidas en fit:", len(dv.get_feature_names_out()))

# Un solo viaje, con una zona que NUNCA aparecio en entrenamiento.
viaje_nuevo = {
    "PU_DO": "999_999",
    "PULocationID": "999",
    "DOLocationID": "999",
    "trip_distance": 4.2,
    "hora_pickup": 9,
    "dia_semana_pickup": 2,
}
fila = dv.transform([viaje_nuevo])

nombres = dv.get_feature_names_out()
activas = [(nombres[j], float(fila[0, j])) for j in fila.nonzero()[1]]
print()
print("valores no cero de la fila transformada:", activas)
print()
print("Ni excepcion, ni warning. Las tres features categoricas valen 0.")
print("El modelo predice usando SOLO la distancia y la hora, y no lo dice.")
"""
    ),
    md(
        """
### La pregunta del segundo acto

El modelo va a devolver un número. Va a ser un número razonable. Y va a estar
calculado ignorando el 50 % de las features del viaje.

**¿Cuántas predicciones así puede estar sirviendo tu API ahora mismo?** Sin
instrumentación, la respuesta es que no lo sabes. Y hay tres formas distintas de
enterarse, cada una con su sitio en el curso:

| Cómo | Cuándo se enteras | Sesión |
|---|---|---|
| El **contrato** rechaza el lote si la zona está fuera de `1-265` | en la frontera, antes de entrenar | esta (§3) |
| Una **métrica** que cuenta categorías no vistas por `request` | en producción, en tiempo real | S07 (Prometheus) |
| El **drift** de la distribución de `PU_DO` contra la referencia | por lotes, comparando periodos | S07 (Evidently) |

Las tres, no una. Un contrato valida **la forma** del dato que entra; no puede
saber que la zona 42 dejó de existir en el mundo.

**Nota sobre alternativas:** con `OneHotEncoder(handle_unknown="ignore")` pasa
exactamente lo mismo (por eso existe ese parámetro). Con
`handle_unknown="error"` la API se cae en la primera ruta nueva. Ninguna de las dos
opciones es gratis: o degradas en silencio, o rompes en voz alta. Lo que no vale es
no haber elegido.
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 3. Los tres niveles de check

**Ahora sí** abrimos el contrato. Está implementado y documentado en
[`src/taxi/data/contract.py`](../../../src/taxi/data/contract.py); este notebook
**ejercita** lo que ya está ahí.

La clase `ViajesCrudos` distingue tres niveles a propósito, porque responden
preguntas distintas:

| Nivel | Cómo se escribe | Qué atrapa | Ejemplo del contrato |
|---|---|---|---|
| **1. Por fila** | `pa.Field(ge=..., le=...)` | registros corruptos individuales | `PULocationID` en `1-265`, `trip_distance >= 0` |
| **2. Por distribución** | `@pa.dataframe_check` sobre una **fracción** o un agregado | problemas **sistemáticos**: un cambio de unidades, una ingesta cortada | `outliers_de_distancia_son_marginales`, `volumen_minimo` |
| **3. Entre columnas** | `@pa.dataframe_check` con dos o más columnas | incoherencias que no se ven mirando una columna sola | `velocidad_implicita_plausible`, `dropoff_posterior_a_pickup` |

Y la decisión de diseño que más cuesta aceptar: **la cota del nivel 1 es ancha a
propósito.**
"""
    ),
    code(
        """
import pandera.errors as pae

from taxi.data import contract as dc


def diagnosticar(df: pd.DataFrame, etiqueta: str) -> None:
    # Devuelve QUE check fallo, no solo que fallo. Es la diferencia entre un
    # contrato que ensena y uno que solo bloquea.
    try:
        dc.validar_crudos(df)
        print(f"{etiqueta:42s} PASA")
    except pae.SchemaErrors as exc:
        checks = sorted({str(c) for c in exc.failure_cases["check"]})
        print(f"{etiqueta:42s} FALLA -> {checks}")
    except pae.SchemaError as exc:
        print(f"{etiqueta:42s} FALLA -> {exc.check}")


base = generar_crudos(filas=2_000, semilla=7)

diagnosticar(base, "crudo valido (control positivo)")
print()

print("--- Nivel 1: por fila ---")
d = base.copy()
d.loc[d.index[0], "trip_distance"] = -3.0
diagnosticar(d, "distancia negativa (imposible)")

d = base.copy()
d.loc[d.index[:3], "DOLocationID"] = 999
diagnosticar(d, "zona 999 (fuera del rango 1-265 de la TLC)")

d = base.copy()
d.loc[d.index[:1], "trip_distance"] = 120_098.84
diagnosticar(d, "1 outlier de 120.098 millas")

print()
print("--- Nivel 2: por distribucion ---")
d = base.copy()
cuantas = int(len(d) * 0.02)
d.loc[d.index[:cuantas], "trip_distance"] = 150.0
diagnosticar(d, "el 2% supera las 100 millas")

d = base.copy()
d["trip_distance"] = d["trip_distance"] * MILLAS_A_KM
diagnosticar(d, "millas -> km (el fallo de la seccion 1)")

diagnosticar(base.head(50), "solo 50 filas (ingesta cortada)")

print()
print("--- Nivel 3: entre columnas ---")
d = base.copy()
d[fc.COL_DROPOFF] = d[fc.COL_PICKUP] + pd.Timedelta(seconds=20)
diagnosticar(d, "velocidad implicita de ~300 mph")

d = base.copy()
d.loc[d.index[:2], fc.COL_DROPOFF] = d.loc[d.index[:2], fc.COL_PICKUP] - pd.Timedelta(minutes=5)
diagnosticar(d, "el viaje termina antes de empezar")
"""
    ),
    md(
        """
### La fila que hay que mirar dos veces

> `1 outlier de 120.098 millas` → **PASA**

Esto no es un descuido: es la decisión más importante del contrato, y viene de un bug
real. El contrato original exigía `trip_distance <= 100` **por fila**, y el parquet
real de la TLC de 2023-01 trae **37 viajes de más de 100 millas** (uno de 120.098) en
**68.211** filas. Resultado: `taxi data` fallaba con `SchemaErrors` en la primera
partición y bloqueaba el curso entero.

Un contrato que rechaza el lote completo por 37 filas de 68.211 es un contrato que el
equipo **aprende a desactivar**, y un contrato desactivado protege exactamente cero.

La cota por fila se queda en lo que ninguna fila válida puede violar (no negativa, no
absurda por órdenes de magnitud) y **la señal de "esto es sistemático" se mueve al
nivel 2**, que es donde pertenece:

```python
# 0,054% de los viajes de 2023-01 supera las 100 millas (medido).
# El umbral de 0,3% deja 5x de margen y sigue atrapando una inflacion sistematica.
MAX_FRACCION_OUTLIERS: float = 0.003
```

**La regla que hay que llevarse:** *un puñado de registros absurdos es ruido de
captura y se filtra; que el 1 % de los viajes pase de 100 millas significa que la
columna cambió de significado.* Son dos preguntas distintas y necesitan dos checks
distintos.

Los tests que fijan esto están en
[`tests/data/test_niveles_de_check.py`](../../../tests/data/test_niveles_de_check.py),
incluido uno que protege el umbral de que alguien lo baje por debajo del ruido real.
"""
    ),
    code(
        """
# El filtro NO es silencioso, y eso tambien es una decision.
# `preparar_particion` cuenta cuantas filas descarta y avisa si pasa del 35%.
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", force=True)

from taxi.data import loaders  # noqa: E402

print(
    "Lee el log de loaders.preparar_particion: registra CUANTAS filas descarto y",
    "avisa si descarta mas del 35%.",
)
print()
print("Por que importa: un filtro silencioso es tan peligroso como no tener filtro.")
print("Si manana se descarta el 40% de los datos, alguien tiene que enterarse.")
print()
print("Fuente:", Path(loaders.__file__).relative_to(RAIZ))
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 4. Qué va en el contrato y qué va en el test

Se confunden constantemente, y la distinción es simple:

- **El contrato describe el dato válido.** Es una afirmación sobre el mundo:
  *"`PULocationID` está entre 1 y 265"*. Vive en `src/`, se versiona con el código y
  se ejecuta **en la frontera** del `pipeline`: donde el dato entra, no donde se usa.
- **El test verifica cómo se comporta el pipeline ante el dato inválido.** Es una
  afirmación sobre tu código: *"si llega la zona 999, la validación **falla**"*. Vive
  en `tests/`, se ejecuta en el CI y **nunca** en producción.

Dicho de otra forma: el contrato es la regla, el test es la prueba de que la regla
está encendida.

**Por qué hacen falta los dos.** Un contrato sin tests se degrada: basta que alguien
relaje un rango para desbloquear un `pipeline` un viernes por la tarde, y nadie lo
nota. Con tests, esa relajación rompe un test con nombre explícito. Es literalmente
lo que dice el encabezado de
[`tests/data/test_contrato_datos.py`](../../../tests/data/test_contrato_datos.py).
"""
    ),
    code(
        """
# El control negativo, que es el test que casi nadie escribe:
# el contrato NO debe inventar fallos.
for semilla in (1, 2, 3, 4, 5):
    dc.validar_crudos(generar_crudos(semilla=semilla))
print("5 lotes independientes del fixture valido: los tres niveles pasan.")
print()
print("Un contrato que falla con datos buenos se desactiva en la primera semana.")
print("Sin este test, 'mi contrato detecta el fallo' no demuestra nada:")
print("un contrato que rechaza TODO tambien detecta el fallo.")
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 5. El límite honesto, y el puente a la sesión 7

Aquí es donde este notebook se separa de la mayoría del material que hay por ahí.
Todo lo anterior funcionó sobre un `fixture` **sintético**. Vamos a repetir el
experimento sobre el parquet **real** de la TLC.

Aviso de resultado, para que la sorpresa sea la correcta: **el contrato va a pasar**.
"""
    ),
    code(
        """
from taxi.config import RAW_DIR

PARQUET = RAW_DIR / "green_tripdata_2023-01.parquet"
print("parquet real presente:", PARQUET.exists())
if not PARQUET.exists():
    print()
    print("Corre `make data` (o `uv run taxi data`) para esta seccion.")
    print("Sin el parquet, salta a la seccion 6.")
"""
    ),
    code(
        """
real = pd.read_parquet(PARQUET)
real_km = real.copy()
real_km["trip_distance"] = real["trip_distance"] * MILLAS_A_KM

print(f"filas: {len(real):,}")
print(f"mediana en millas: {real['trip_distance'].median():.2f}")
print(f"mediana en 'km'  : {real_km['trip_distance'].median():.2f}")
print()
frac_millas = float((real["trip_distance"] > 100).mean())
frac_km = float((real_km["trip_distance"] > 100).mean())
print(f"fraccion > 100 en millas: {frac_millas:.6f}  ({int(frac_millas * len(real))} viajes)")
print(f"fraccion > 100 en 'km'  : {frac_km:.6f}  ({int(frac_km * len(real))} viajes)")
print(f"umbral del contrato     : {dc.MAX_FRACCION_OUTLIERS}")
print()
diagnosticar(real, "parquet REAL en millas")
diagnosticar(real_km, "parquet REAL en 'km'")
"""
    ),
    md(
        """
### Por qué pasa, y por qué hay que decirlo en voz alta

El contrato **no atrapa** el cambio de unidades sobre el lote real. La razón es
exacta y está escrita en
[`tests/data/test_contrato_datos.py`](../../../tests/data/test_contrato_datos.py):

> *"El contrato no compara unidades (no puede: el número no las lleva). Lo que
> detecta es que los viajes largos legítimos, al convertirse a km, se salen del
> límite de 100. **Si el dataset no tuviera cola larga, este contrato NO atraparía el
> cambio de unidades**, y conviene que eso quede escrito."*

El `fixture` sintético tiene una cola diseñada de viajes de 70-95 millas, así que en
km se sale de rango y el check de nivel 2 se dispara. El parquet real de green taxi
es abrumadoramente urbano: su mediana es 1,85 millas y su p99 no llega a 15. Al pasar
a km, la mediana va a ~2,98 y **sigue siendo perfectamente plausible para un taxi**.

**Un factor de 1,6 está en el borde de lo que un contrato estático puede detectar
sobre un solo lote.** Eso no es un defecto del contrato: es su definición. Un
contrato mira **un** lote, aislado, y decide si está bien formado. Para detectar un
cambio de escala moderado hace falta lo único que el contrato no tiene: **una
referencia con la que comparar**.

Y eso es monitoreo de `drift`, que es la sesión 7.
"""
    ),
    code(
        """
# Lo que SI detecta el cambio de unidades: comparar contra una referencia.
# Este es literalmente el primer instrumento de la sesion 7.
from scipy.stats import ks_2samp

referencia = real["trip_distance"].sample(20_000, random_state=1)
actual = real_km["trip_distance"].sample(20_000, random_state=2)

r = ks_2samp(referencia, actual)
print("KS entre la referencia (millas) y el lote actual (km):")
print(f"  D = {r.statistic:.4f}   <- tamano de efecto, acotado en [0, 1]")
print(f"  p = {r.pvalue:.3g}")
print()
print("Un D de ese orden es enorme. El contrato no lo vio; el drift no tiene dudas.")
print()
print("Y el control negativo, que es lo que hace creible al detector:")
mitad_a = real["trip_distance"].sample(20_000, random_state=10)
mitad_b = real["trip_distance"].sample(20_000, random_state=20)
r0 = ks_2samp(mitad_a, mitad_b)
print(f"  dos muestras del MISMO dato: D = {r0.statistic:.4f}  (ruido del instrumento)")
"""
    ),
    md(
        """
### El puente S02 → S07, que es lo que hay que llevarse de este notebook

| | Contrato de datos (S02) | Monitoreo de `drift` (S07) |
|---|---|---|
| Qué mira | **un** lote, aislado | **dos** distribuciones: referencia vs actual |
| Qué pregunta responde | ¿este dato está bien formado? | ¿este dato se parece al que usé para entrenar? |
| Cuándo actúa | en la **frontera**, antes de entrenar o servir | por lotes, después, de forma continua |
| Qué hace al fallar | detiene el `pipeline` (falla rápido y ruidoso) | alerta, y alguien **investiga** |
| Qué **no** puede ver | un cambio de escala moderado, una categoría que dejó de existir en el mundo | un registro individual corrupto |

**No compiten. Se complementan, y un curso que enseñe solo una de las dos deja
justamente el hueco por el que se cuelan los incidentes reales.**

Si te quedas solo con el contrato, un factor de 1,6 se te pasa. Si te quedas solo con
el `drift`, entrenas con nulos y con zonas que no existen mientras esperas a que se
acumule un lote para comparar.

---

## 6. Autoverificación del notebook

1. El cambio de unidades no lanzó ninguna excepción y `mypy` habría pasado en verde.
   ¿Por qué? ¿Qué información falta en un `float64`?
2. ¿Por qué el contrato **acepta** un viaje de 120.098 millas y **rechaza** que el
   2 % de los viajes pase de 100? Explícalo en términos de las dos preguntas
   distintas que responden.
3. Bajas `MAX_FRACCION_OUTLIERS` de `0.003` a `0.0001`. ¿Qué gana el contrato y qué
   pierde? (Pista: mide la fracción real de 2023-01, que salió en la §5.)
4. El contrato pasó sobre el parquet real en km. Nombra **dos** cosas distintas que sí
   lo habrían detectado, y di en qué momento del ciclo de vida actúa cada una.
5. Tu API recibe una zona que no existía en entrenamiento. ¿Devuelve un error o una
   predicción? ¿Cuál de las dos opciones quieres, y de qué depende la respuesta?

## 7. Ejercicios (10 min)

1. Cambia el factor de conversión de `1.60934` a `1.15` (millas a millas náuticas) y
   vuelve a correr la §3. ¿A partir de qué factor el contrato deja de detectarlo con
   el `fixture` sintético? **Mide el umbral**, no lo estimes.
2. Escribe un check de **nivel 3** nuevo: que la relación entre `total_amount` y
   `trip_distance` sea plausible. Piensa el rango antes de mirar los datos, y después
   mídelo. ¿Coincidió?
3. Rompe un check a propósito en `src/taxi/data/contract.py` (relaja un rango) y corre
   `uv run pytest tests/data -q`. ¿Qué test se cae y qué dice su nombre?
   **Deshaz el cambio.**
4. Añade un cuarto `fixture` roto a `tests/conftest.py` —un `timestamp` en el
   futuro— y el test que verifica que el contrato lo rechaza. Si el contrato **no** lo
   rechaza, has encontrado un hueco: escríbelo.

Siguiente: [`02-validacion-temporal-y-leakage.ipynb`](02-validacion-temporal-y-leakage.ipynb) ·
Volver: [README de la sesión](../README.md)
"""
    ),
]


# =============================================================================
# 02 — Validacion temporal y leakage
# =============================================================================
NB2 = [
    md(
        """
# S02 · 02 — Validación temporal y las tres formas de `leakage`

**Objetivo.** Ver, con números medidos sobre el caso guía, que una validación mal
montada produce una métrica **optimista** que no se sostiene al desplegar; y
reconocer las tres formas en que la información del futuro se cuela en un modelo.

**Por qué está en la sesión de datos y no en una de modelado.** El `leakage` no es un
error de modelado: es un error de **construcción del dataset**. Se comete al decidir
qué columna es una feature y cómo se calcula, y se paga en producción. Es un problema
de datos como código.

**Requisito.** El parquet del caso guía en `data/raw/`. Si no lo tienes, corre
`make data`. La primera celda avisa.

**Ruta del notebook.**

1. La regla, y por qué un `split` aleatorio miente con datos temporales.
2. `TimeSeriesSplit` frente a `KFold(shuffle=True)`: dos métricas, mismos datos.
3. **Leakage 1** — escalar o imputar **antes** del `split`.
4. **Leakage 2** — features con información del futuro:
   `shift(1).rolling(7)` frente a `rolling(7)`.
5. **Leakage 3** — el `target` codificado dentro de una feature.
6. Cómo se detecta un `leakage` que no sabías que tenías.

> **API vigente.** Este notebook usa `root_mean_squared_error` de scikit-learn.
> `mean_squared_error(..., squared=False)` **ya no existe**: el parámetro `squared`
> fue deprecado en 1.4 y **eliminado** en 1.6. La versión de este material es
> `scikit-learn 1.9.0`, verificada en agosto de 2026. La mayoría de los tutoriales
> que hay en la web usan la forma que ya no ejecuta.
"""
    ),
    code(PREAMBULO),
    code(
        """
import numpy as np
import pandas as pd

from taxi.config import (
    PARTICIONES_TRAIN,
    PARTICION_TEST,
    PARTICION_VALID,
    RAW_DIR,
    SEMILLA,
)
from taxi.features import contract as fc

PARTICIONES = [*PARTICIONES_TRAIN, PARTICION_VALID, PARTICION_TEST]
faltan = [p.etiqueta for p in PARTICIONES if not (RAW_DIR / p.nombre_archivo).exists()]
print("particiones:", [p.etiqueta for p in PARTICIONES])
if faltan:
    print("FALTAN:", faltan, "-> corre `make data`")
else:
    print("todas presentes.")
print()
print("semilla del curso:", SEMILLA)
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 1. La regla

> **En producción, el modelo siempre predice sobre el futuro.** Cualquier validación
> que no respete eso mide algo que no va a ocurrir.

Con `train_test_split(shuffle=True)` sobre datos con eje temporal, el `split` puede
poner julio en `train` y marzo en `test`. El modelo aprende de julio para predecir
marzo. En producción eso **nunca** pasa: solo tienes datos hasta hoy.

```
Split aleatorio (MAL con datos temporales):
  train:  [ene] [mar] [jul] [sep]
  test:   [feb] [may] [oct] [dic]        <- mezcla pasado y futuro

Split temporal (BIEN):
  train:  [ene feb mar abr] --------->
  test:                       [may]      <- el periodo inmediatamente siguiente
```

Y esa es exactamente la decisión del caso guía
([ADR 001](../../../docs/adr/001-caso-guia-y-particiones.md)): `train` 2023-01..03,
`valid` 2023-04, `holdout` 2023-05. Nada de aleatorio, y el `holdout` con un rol
exclusivo.

Vamos a construir una serie diaria de demanda —**viajes por día**— a partir del
parquet del caso guía. Es un problema de negocio real (dimensionar la flota) y tiene
la propiedad que necesitamos: un eje temporal explícito y lags con sentido.
"""
    ),
    code(
        """
marcos = [
    pd.read_parquet(RAW_DIR / p.nombre_archivo, columns=[fc.COL_PICKUP, "trip_distance"])
    for p in PARTICIONES
]
crudo = pd.concat(marcos, ignore_index=True)

crudo["fecha"] = crudo[fc.COL_PICKUP].dt.floor("D")
# El parquet real trae unas pocas filas con timestamps de otros meses (errores de
# captura del proveedor). Se recorta a las particiones DECLARADAS: si no, la serie
# tiene dias sueltos de 2022 con 3 viajes y los lags salen absurdos.
INICIO, FIN = pd.Timestamp("2023-01-01"), pd.Timestamp("2023-06-01")
antes = len(crudo)
crudo = crudo[(crudo["fecha"] >= INICIO) & (crudo["fecha"] < FIN)]
print(f"filas: {antes:,} -> {len(crudo):,} (descartadas {antes - len(crudo):,} fuera de rango)")

diario = (
    crudo.groupby("fecha")
    .agg(viajes=("trip_distance", "size"), distancia_media=("trip_distance", "mean"))
    .reset_index()
    .sort_values("fecha")
    .reset_index(drop=True)
)
print(f"serie diaria: {len(diario)} dias, de {diario.fecha.min().date()} a {diario.fecha.max().date()}")
print(diario.head(3).to_string(index=False))
"""
    ),
    code(
        """
# Features. Fijate en como se calculan los lags: es el punto de la seccion 4.
d = diario.copy()
d["dia_semana"] = d["fecha"].dt.dayofweek
d["mes"] = d["fecha"].dt.month
d["es_fin_de_semana"] = (d["dia_semana"] >= 5).astype(int)

# CORRECTO: shift(1) primero. El valor de "ayer" y la media de los "7 dias
# anteriores", ambos disponibles la manana en que hay que predecir hoy.
d["viajes_lag_1"] = d["viajes"].shift(1)
d["viajes_lag_7"] = d["viajes"].shift(7)
d["viajes_media_7"] = d["viajes"].shift(1).rolling(7).mean()

# INCORRECTO, y lo dejamos aqui para medirlo en la seccion 4:
# rolling(7) SIN shift incluye el dia de hoy, que es lo que estamos prediciendo.
d["media_7_con_leakage"] = d["viajes"].rolling(7).mean()

d = d.dropna().reset_index(drop=True)
print(f"{len(d)} dias utilizables (los primeros 7 se pierden por los lags)")
print(d[["fecha", "viajes", "viajes_lag_1", "viajes_media_7", "media_7_con_leakage"]].head(3).to_string(index=False))
"""
    ),
    md(
        """
> **Los primeros 7 días se pierden y eso es correcto.** Un modelo con lag de 7 días
> no puede predecir el día 3 de la serie: esa información no existía. `dropna()` aquí
> no es limpieza, es honestidad. Rellenar esos lags con la media —o con `fillna(0)`—
> inventaría un pasado que no ocurrió, y el modelo lo aprendería como real.
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 2. `TimeSeriesSplit` frente a `KFold(shuffle=True)`

`TimeSeriesSplit` entrena siempre con el pasado y evalúa con el periodo siguiente.
Cada `fold` usa más datos de entrenamiento que el anterior:

```
Fold 1: [==== TRAIN ====][= TEST =]
Fold 2: [====== TRAIN ======][= TEST =]
Fold 3: [======== TRAIN ========][= TEST =]
Fold 4: [========== TRAIN ==========][= TEST =]
Fold 5: [============ TRAIN ============][= TEST =]
```

Es exactamente lo que va a pasar en producción: reentrenas con todo lo que tienes y
predices lo siguiente.
"""
    ),
    code(
        """
from sklearn.model_selection import KFold, TimeSeriesSplit, cross_val_score
from xgboost import XGBRegressor

FEATURES = [
    "dia_semana",
    "mes",
    "es_fin_de_semana",
    "viajes_lag_1",
    "viajes_lag_7",
    "viajes_media_7",
]
X, y = d[FEATURES], d["viajes"]


def modelo() -> XGBRegressor:
    return XGBRegressor(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        random_state=SEMILLA,  # semilla explicita, no el estado global
        n_jobs=1,
    )


tscv = TimeSeriesSplit(n_splits=5)
print("Los folds de TimeSeriesSplit:")
for i, (i_tr, i_te) in enumerate(tscv.split(X), 1):
    print(
        f"  fold {i}: train [{d.fecha.iloc[i_tr[0]].date()} -> {d.fecha.iloc[i_tr[-1]].date()}]"
        f" ({len(i_tr):3d} dias)  |  test [{d.fecha.iloc[i_te[0]].date()}"
        f" -> {d.fecha.iloc[i_te[-1]].date()}] ({len(i_te)} dias)"
    )
"""
    ),
    code(
        """
# La misma metrica, los mismos datos, el mismo modelo. Solo cambia el esquema de CV.
kf = KFold(n_splits=5, shuffle=True, random_state=SEMILLA)

rmse_ts = -cross_val_score(modelo(), X, y, cv=tscv, scoring="neg_root_mean_squared_error")
rmse_kf = -cross_val_score(modelo(), X, y, cv=kf, scoring="neg_root_mean_squared_error")

print(f"{'':22s}{'por fold':>34s}{'media':>10s}")
print(f"{'TimeSeriesSplit':22s}{str(rmse_ts.round(1)):>34s}{rmse_ts.mean():>10.1f}")
print(f"{'KFold(shuffle=True)':22s}{str(rmse_kf.round(1)):>34s}{rmse_kf.mean():>10.1f}")
print()
sesgo = 100 * (rmse_ts.mean() - rmse_kf.mean()) / rmse_ts.mean()
print(f"El KFold aleatorio reporta un RMSE {sesgo:.1f}% MEJOR.")
print()
print("Y ese es el numero que NO vas a ver en produccion.")
"""
    ),
    md(
        """
### Cómo leer estos números, sin exagerar

**Mide y compara los tuyos.** Dos cosas que hay que decir con precisión, porque es
fácil sacar la lección equivocada:

1. **El `KFold` aleatorio es optimista, y la dirección del sesgo no es casual.** Al
   mezclar días, cada `fold` de `test` está rodeado de días *vecinos* que están en
   `train`. Con lags autocorrelacionados, eso es casi tener la respuesta. En
   producción no tienes vecinos futuros: tienes el pasado y nada más.
2. **La magnitud depende del dataset**, y en esta serie es moderada, no espectacular.
   Con series muy autocorrelacionadas o con tendencia fuerte, el sesgo es mucho mayor.
   Si te encuentras un tutorial donde la diferencia es de un factor 3, probablemente
   el dato esté construido para que lo sea.

Y el punto que sostiene todo: **con `TimeSeriesSplit` no puedes engañarte, con
`KFold` sí.** El valor de la validación temporal no es dar mejores números; es dar
números que se sostengan al desplegar. La métrica correcta suele ser la peor.

> **Un matiz que la mayoría del material omite:** `TimeSeriesSplit` tampoco es
> automáticamente correcto. Si tu feature usa una ventana de 30 días, el `fold` de
> `test` puede contener información derivada de días que están en `train`
> (contaminación por la ventana). La solución es un `gap` entre `train` y `test`:
> `TimeSeriesSplit(n_splits=5, gap=30)`. Pruébalo en el ejercicio 2.
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 3. Leakage 1 — escalar o imputar **antes** del `split`

El más común, y el más fácil de cometer sin darse cuenta:

```python
# MAL
X_escalado = StandardScaler().fit_transform(X)     # fit sobre TODO, test incluido
X_tr, X_te = X_escalado[:corte], X_escalado[corte:]

# BIEN
pipe = Pipeline([("escala", StandardScaler()), ("modelo", Ridge())])
pipe.fit(X_tr, y_tr)          # el fit del scaler ocurre DENTRO de cada fold
```

Al hacer `fit` del `scaler` sobre todo el `dataset`, la media y la desviación que se
usan para transformar `train` **contienen información de `test`**. Lo mismo con
`SimpleImputer` (la media que rellena viene del futuro), con `SelectKBest` (las
features se eligen mirando `test`) y con `PCA`.

Vamos a medirlo. Y el resultado va a ser más interesante de lo que parece.
"""
    ),
    code(
        """
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import root_mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

rng = np.random.default_rng(SEMILLA)
d_nulos = d.copy()
# Nulos "de captura" en una feature: el 12% de los dias falta el conteo de ayer.
faltan_idx = rng.choice(len(d_nulos), size=int(len(d_nulos) * 0.12), replace=False)
d_nulos.loc[faltan_idx, "viajes_lag_1"] = np.nan

Xn, yn = d_nulos[FEATURES], d_nulos["viajes"]
corte = len(d_nulos) - 30  # ultimos 30 dias como holdout temporal

# --- MAL: imputar y escalar ANTES del split ---
imputador_global = SimpleImputer(strategy="mean")
escalador_global = StandardScaler()
Xn_todo = escalador_global.fit_transform(imputador_global.fit_transform(Xn))
mal = Ridge(alpha=1.0).fit(Xn_todo[:corte], yn.iloc[:corte])
rmse_mal = root_mean_squared_error(yn.iloc[corte:], mal.predict(Xn_todo[corte:]))

# --- BIEN: dentro de un Pipeline, ajustado solo con train ---
pipe = Pipeline(
    [
        ("imputa", SimpleImputer(strategy="mean")),
        ("escala", StandardScaler()),
        ("modelo", Ridge(alpha=1.0)),
    ]
)
pipe.fit(Xn.iloc[:corte], yn.iloc[:corte])
rmse_bien = root_mean_squared_error(yn.iloc[corte:], pipe.predict(Xn.iloc[corte:]))

print(f"RMSE con fit sobre TODO (leakage) : {rmse_mal:8.2f}")
print(f"RMSE con Pipeline (correcto)      : {rmse_bien:8.2f}")
print()
print("Y ahora la parte importante: los estadisticos que se usaron.")
print(f"  media de viajes_lag_1 con fit sobre TODO  : {imputador_global.statistics_[3]:8.2f}")
print(f"  media de viajes_lag_1 con fit solo en train: {pipe.named_steps['imputa'].statistics_[3]:8.2f}")
"""
    ),
    md(
        """
### El resultado incómodo, y por qué es la lección de verdad

Compara los dos RMSE. **Probablemente la diferencia sea pequeña**, o incluso
favorable al método correcto por casualidad.

Eso no invalida nada: **lo hace peor**. Piénsalo:

> **El `leakage` que no mueve tu métrica es el que sobrevive al `code review`.**

Si un `leakage` te regalara siempre un RMSE espectacular, lo detectarías: nadie se
cree un RMSE de 0,01. El peligroso es este: te contamina el estimador un poco, no lo
suficiente para levantar sospechas, y te deja creyendo que tu validación mide
generalización cuando no la mide.

Por eso la defensa **no es medir**: es **estructural**. Mira las dos últimas líneas
de la salida: las medias son **distintas**. Ese es el hecho objetivo. La media que se
usó para rellenar los nulos de `train` en el caso "mal" está calculada con días que
están en `test`.

**La regla, y no admite excepciones:** toda transformación que **aprende** algo del
dato (`scaler`, `imputer`, `encoder`, selección de features, `PCA`) va **dentro de un
`Pipeline`**, para que su `fit` ocurra dentro de cada `fold` y solo con `train`. No es
una buena práctica de estilo: es lo único que hace la validación válida.
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 4. Leakage 2 — features con información del futuro

El caso `shift(1).rolling(7)` frente a `rolling(7)`. La diferencia son ocho
caracteres y cambia por completo lo que el modelo puede saber.

```python
# CORRECTO: la media de los 7 dias ANTERIORES a hoy
d["viajes"].shift(1).rolling(7).mean()

# LEAKAGE: la media de una ventana que INCLUYE hoy,
# y hoy es exactamente lo que estamos prediciendo
d["viajes"].rolling(7).mean()
```

Antes de medirlo, la prueba que hay que hacer siempre y que no necesita ningún
modelo: **mirar las dos columnas en una fila concreta.**
"""
    ),
    code(
        """
# La comprobacion aritmetica. No hace falta entrenar nada para ver el problema.
i = 40
fila = d.loc[i]
ventana_correcta = d["viajes"].iloc[i - 7 : i]      # los 7 dias ANTERIORES
ventana_leak = d["viajes"].iloc[i - 6 : i + 1]      # 6 anteriores + HOY

print(f"dia {fila.fecha.date()}: viajes = {fila.viajes:.0f}   <- el target")
print()
print(f"  viajes_media_7      = {fila.viajes_media_7:8.2f}   (media de {ventana_correcta.tolist()})")
print(f"  media_7_con_leakage = {fila.media_7_con_leakage:8.2f}   (media de {ventana_leak.tolist()})")
print()
print("La segunda contiene el target dividido por 7. El modelo solo tiene que")
print("multiplicar por 7 y restar los otros seis.")
print()
print("correlacion con el target:")
print(f"  viajes_media_7      : {d['viajes'].corr(d['viajes_media_7']):.4f}")
print(f"  media_7_con_leakage : {d['viajes'].corr(d['media_7_con_leakage']):.4f}")
"""
    ),
    code(
        """
FEATURES_LEAK = [
    "dia_semana",
    "mes",
    "es_fin_de_semana",
    "viajes_lag_1",
    "viajes_lag_7",
    "media_7_con_leakage",  # <- el unico cambio
]

rmse_correcto = -cross_val_score(
    modelo(), d[FEATURES], y, cv=tscv, scoring="neg_root_mean_squared_error"
)
rmse_futuro = -cross_val_score(
    modelo(), d[FEATURES_LEAK], y, cv=tscv, scoring="neg_root_mean_squared_error"
)

print(f"RMSE con shift(1).rolling(7)  (correcto) : {rmse_correcto.mean():7.1f}")
print(f"RMSE con rolling(7)           (leakage)  : {rmse_futuro.mean():7.1f}")
print()
print("La 'mejora' es gratis en validacion y es imposible en produccion:")
print("la manana en que tienes que predecir hoy, el conteo de hoy no existe todavia.")
"""
    ),
    md(
        """
### La pregunta que detecta este `leakage` sin medir nada

Para **cada** feature, una sola pregunta:

> **¿Este valor estaba disponible en el momento en que hay que hacer la predicción?**

Si la respuesta es "no" o "no estoy seguro", es `leakage`. No hace falta entrenar
nada.

Y su versión operativa, que es la que hay que llevarse al proyecto: **anota, junto a
cada feature, el instante en que su valor queda disponible.** Con eso, la pregunta se
responde comparando dos `timestamps` en lugar de discutiéndola en un PR.

Ejemplos del caso guía, para calibrar el olfato:

| Feature | ¿Disponible al predecir? | Por qué |
|---|---|---|
| `hora_pickup`, `dia_semana_pickup` | **sí** | se derivan del momento de la recogida, que ya ocurrió |
| `PULocationID`, `DOLocationID` | **sí** | el destino se declara al subir al taxi |
| `trip_distance` | **sí**, con matiz: es la distancia registrada del viaje. Para predecir la duración *antes* de empezar, habría que usar la distancia **estimada** de la ruta, no la real | es el tipo de matiz que hay que escribir en la `dataset card` |
| `lpep_dropoff_datetime` | **no** | es literalmente el `target`, disfrazado |
| `total_amount`, `fare_amount` | **no** | la tarifa se calcula **con** la duración del viaje |
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 5. Leakage 3 — el `target` codificado dentro de una feature

El más difícil de ver, porque la feature parece razonable y hasta tiene nombre de
negocio. Un ejemplo real y muy frecuente en este dominio: **la velocidad media del
viaje**.

```python
df["velocidad_media"] = df["trip_distance"] / (df["duration"] / 60)
```

Parece una feature legítima —"qué tan rápido va el tráfico"— y es un desastre: para
calcularla hace falta `duration`, que es **el `target`**. En producción, la mañana en
que quieres predecir cuánto va a durar el viaje, no puedes calcular su velocidad
media.

Vamos a medirlo sobre el problema real del caso guía: predecir la duración de un
viaje.
"""
    ),
    code(
        """
from taxi.config import DURACION_MAX_MIN, DURACION_MIN_MIN


def preparar_viajes(particion, filas: int = 40_000) -> pd.DataFrame:
    df = pd.read_parquet(RAW_DIR / particion.nombre_archivo)
    delta = df[fc.COL_DROPOFF] - df[fc.COL_PICKUP]
    df[fc.TARGET_REGRESION] = delta.dt.total_seconds() / 60.0
    valido = (
        df[fc.TARGET_REGRESION].between(DURACION_MIN_MIN, DURACION_MAX_MIN)
        & df["trip_distance"].le(100)
        & df["trip_distance"].gt(0)
    )
    df = df[valido].sample(n=min(filas, int(valido.sum())), random_state=SEMILLA)
    df = fc.construir_features(df.reset_index(drop=True))
    # La feature envenenada: el target esta en el denominador.
    df["velocidad_media"] = df["trip_distance"] / (df[fc.TARGET_REGRESION] / 60)
    return df


tren = preparar_viajes(PARTICIONES_TRAIN[0])   # 2023-01
prueba = preparar_viajes(PARTICION_VALID)      # 2023-04, el mes SIGUIENTE
print(f"train: {len(tren):,} viajes de {PARTICIONES_TRAIN[0]}")
print(f"test : {len(prueba):,} viajes de {PARTICION_VALID}")
"""
    ),
    code(
        """
from sklearn.feature_extraction import DictVectorizer


def rmse_con(features: list[str]) -> float:
    dv = DictVectorizer()
    x_tr = dv.fit_transform(tren[features].to_dict(orient="records"))
    x_te = dv.transform(prueba[features].to_dict(orient="records"))
    m = Ridge(alpha=1.0).fit(x_tr, tren[fc.TARGET_REGRESION])
    return float(root_mean_squared_error(prueba[fc.TARGET_REGRESION], m.predict(x_te)))


base = rmse_con(fc.FEATURES)
envenenado = rmse_con([*fc.FEATURES, "velocidad_media"])

print(f"RMSE con las features del curso            : {base:6.2f} min")
print(f"RMSE anadiendo 'velocidad_media' (LEAKAGE) : {envenenado:6.2f} min")
print()
print(f"'mejora' del {100 * (base - envenenado) / base:.1f}%, imposible de reproducir en produccion")
print()
print("Y ahora la parte que hay que mirar dos veces:")
corr = float(tren["velocidad_media"].corr(tren[fc.TARGET_REGRESION]))
print(f"  corr(velocidad_media, duration) = {corr:.3f}   <- BAJA")
"""
    ),
    md(
        """
### La correlación **no** te habría avisado

Mira el último número. La correlación de Pearson entre `velocidad_media` y el
`target` es baja —del orden de 0,1— y sin embargo la feature regala un ~24 % de
"mejora" en RMSE.

**Mide la tuya**, pero espera lo mismo: la relación es `duration = distancia /
velocidad`, es decir **inversa y no lineal**, y Pearson mide relación *lineal*. Un
modelo de árboles o una regresión con el resto de features la explota sin problema;
un coeficiente de correlación no la ve.

Esto desmonta el atajo más popular para detectar `leakage`. La conclusión no es que
mirar correlaciones sea inútil —atrapa el caso burdo, una copia directa del
`target`— sino que **una correlación baja no es evidencia de ausencia de `leakage`**.

Lo único que sí lo habría detectado, y sin ejecutar nada, es la pregunta de la §4:
*¿de dónde sale este número?* De `duration`. Y `duration` es lo que estamos
prediciendo. Fin del análisis.

### Otras formas del mismo error, para reconocerlas

| Feature sospechosa | Por qué codifica el `target` |
|---|---|
| `velocidad_media = distancia / duracion` | el `target` está en el denominador |
| `total_amount` en el caso guía | la tarifa se calcula **con** el tiempo del viaje |
| `target encoding` de una categórica calculado sobre **todo** el `dataset` | la media del `target` por categoría incluye las filas de `test`. La forma correcta es `expanding` con `shift(1)`, o dentro de un `Pipeline` con validación anidada |
| Un `id` que se asignó **después** del evento | los `id` correlativos codifican el orden temporal, y a veces el resultado |
| `dias_hasta_el_evento` | solo se conoce cuando el evento ya ocurrió |
| Una columna con nulos **solo** en las filas negativas | el patrón de nulos es el `target` |

La última merece atención: si `motivo_de_cancelacion` está vacío exactamente cuando
el pedido no se canceló, la **presencia** del nulo es la etiqueta. El modelo lo
aprende en el primer `split` y tu AUC es 0,99.
"""
    ),
    # -------------------------------------------------------------------------
    md(
        """
---

## 6. Cómo detectar un `leakage` que no sabías que tenías

Cinco señales, de la más barata a la más cara. Las tres primeras se responden sin
entrenar nada.

1. **La pregunta del `timestamp`.** Para cada feature: ¿estaba disponible en el
   instante de la predicción? Es la más barata y la **única fiable** de la lista.
   Atrapó los tres `leakages` de este notebook sin ejecutar nada.
2. **Correlación individual sospechosa.** Útil solo en el caso burdo: una feature con
   correlación > 0,9 es una copia del `target`. **Pero una correlación baja no
   demuestra nada** — lo acabamos de medir en la §5: 0,1 de correlación y un 24 % de
   mejora falsa, porque la relación era inversa y Pearson mide relación lineal.
3. **La métrica es demasiado buena.** Si tu RMSE mejora un 60 % al añadir una feature
   nueva, la hipótesis por defecto no es "encontré una gran feature": es "tengo
   `leakage`". Compáralo siempre con un `baseline` tonto (predecir la media, o el
   valor de ayer).
4. **`feature_importances_` con un dominador absoluto.** Si una feature explica el
   80 % del modelo, mírala con lupa. Ojo: la importancia de los árboles es engañosa
   con features correlacionadas, así que sirve como señal de alarma, no como prueba.
5. **`Backtesting` honesto.** Entrena con datos hasta una fecha, predice el periodo
   siguiente, y compara **como si fuera producción**. Es lo que hace el `holdout` fijo
   del curso (2023-05), y por eso ese mes no se usa para nada más.

Y el orden importa: las señales 2, 3 y 4 son **heurísticas** que se te pueden pasar,
como acabamos de comprobar. La 1 es un razonamiento y no falla. **Audita features, no
correlaciones.**
"""
    ),
    code(
        """
# El baseline tonto, que es la comprobacion mas rentable de todo el notebook.
corte = len(d) - 30
y_test = d["viajes"].iloc[corte:]

# Baseline 1: predecir la media del train
pred_media = np.full(len(y_test), d["viajes"].iloc[:corte].mean())
# Baseline 2: predecir "lo mismo que ayer" (persistencia)
pred_ayer = d["viajes_lag_1"].iloc[corte:].to_numpy()
# El modelo
m = modelo().fit(d[FEATURES].iloc[:corte], d["viajes"].iloc[:corte])
pred_modelo = m.predict(d[FEATURES].iloc[corte:])

print(f"{'baseline: la media':28s} RMSE {root_mean_squared_error(y_test, pred_media):7.1f}")
print(f"{'baseline: como ayer':28s} RMSE {root_mean_squared_error(y_test, pred_ayer):7.1f}")
print(f"{'modelo (XGBoost + lags)':28s} RMSE {root_mean_squared_error(y_test, pred_modelo):7.1f}")
print()
print("Si tu modelo no le gana a 'como ayer', no tienes un modelo:")
print("tienes un problema mas facil de lo que creias, o un bug.")
print()
print("Y si le gana por un factor de 5, sospecha de leakage antes de celebrar.")
"""
    ),
    md(
        """
---

## 7. Resumen

| Riesgo | Cómo se comete | Cómo se evita |
|---|---|---|
| `Split` aleatorio con datos temporales | `train_test_split(shuffle=True)`, `KFold(shuffle=True)` | corte temporal + `TimeSeriesSplit`, con `gap` si tus ventanas son largas |
| Escalar / imputar antes del `split` | `fit_transform` sobre todo el `dataset` | **`Pipeline`**. Sin excepciones |
| Features del futuro | `rolling(7)` sin `shift(1)`, agregados sobre toda la serie | `shift(1).rolling(...)`, y la pregunta del `timestamp` por feature |
| `Target` dentro de una feature | ratios que dividen por el `target`, `target encoding` global, nulos informativos | auditar cada feature contra "¿cómo se calcula este número?" |
| Creerse la métrica | no tener con qué comparar | `baseline` tonto + `holdout` fijo que no se toca |

**La frase de la sesión:** un `split` mal hecho no produce un error. Produce una
métrica que se cae el día del despliegue, cuando ya nadie recuerda cómo se validó.

## 8. Autoverificación

1. Tienes datos de enero a diciembre y usas `KFold(shuffle=True)`. Describe una fila
   concreta que acabe en `test` con sus vecinas en `train`, y qué información le
   regala eso al modelo.
2. `SimpleImputer(strategy="mean")` fuera del `Pipeline`, con `split` temporal
   correcto. ¿Hay `leakage`? ¿Cuál exactamente, y en qué dirección sesga?
3. `d["viajes"].shift(1).rolling(7).mean()` frente a `d["viajes"].rolling(7).mean()`.
   Explica la diferencia refiriéndote a una fila concreta, no en abstracto.
4. Tu AUC sube de 0,72 a 0,97 al añadir una feature. Enumera, en orden, las tres cosas
   que compruebas antes de dar la buena noticia.
5. Tu `dataset` **no** tiene eje temporal (una encuesta transversal, por ejemplo).
   ¿Se puede tener `leakage`? ¿Cuál de los tres tipos sigue siendo posible?

## 9. Ejercicios (10 min)

1. Añade `viajes_lag_14` y `viajes_media_30` (bien calculados) y mide si el RMSE
   mejora. ¿Cuántos días útiles pierdes? ¿Merece la pena con 144 días de serie?
2. Corre `TimeSeriesSplit(n_splits=5, gap=7)` y compara con `gap=0`. ¿Por qué el
   `gap` importa cuando tus features usan una ventana de 7 días?
3. Implementa el `target encoding` de `dia_semana` de las **dos** formas —global y con
   `shift(1).expanding()`— y mide la diferencia en `TimeSeriesSplit`. Interpreta el
   resultado, incluso si es pequeño (§3 explica por qué eso es lo interesante).
4. Coge **tu** `dataset` del proyecto y escribe la tabla de la §4: una fila por
   feature, con el instante en que su valor queda disponible. Es material directo para
   tu `dataset-card.md` del hito 1.

Volver: [README de la sesión](../README.md) ·
[`01-el-dolor-de-los-datos.ipynb`](01-el-dolor-de-los-datos.ipynb)
"""
    ),
]


def main() -> None:
    for nombre, celdas, titulo in [
        ("01-el-dolor-de-los-datos.ipynb", NB1, "S02 01 - El dolor de los datos"),
        (
            "02-validacion-temporal-y-leakage.ipynb",
            NB2,
            "S02 02 - Validacion temporal y leakage",
        ),
    ]:
        nb = notebook(celdas, titulo)
        nbf.validate(nb)
        destino = AQUI / nombre
        with destino.open("w", encoding="utf-8") as fh:
            nbf.write(nb, fh)
        print(f"{nombre}: {len(nb.cells)} celdas")


if __name__ == "__main__":
    main()
