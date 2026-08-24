# Solución de referencia — Taller S02

> **No publicar antes del taller.**
> Enunciado: [`../taller.md`](../taller.md).

El repositorio del curso cumple los trece criterios. Esta página recorre los trece y
señala **qué archivo** los satisface y **con qué comando** se comprueba, para que la
revisión de los PR sea mecánica.

---

## Criterio 1 — ≥ 6 reglas no triviales, ≥ 2 de cada nivel

Archivo: [`src/taxi/data/contract.py`](../../../src/taxi/data/contract.py).

El contrato `ViajesCrudos` tiene **nueve** reglas, repartidas así:

| Nivel | Regla | Qué protege |
|---|---|---|
| 1 | `lpep_pickup_datetime` / `lpep_dropoff_datetime` `nullable=False` | una descarga cortada deja nulos en el eje temporal |
| 1 | `PULocationID` `ge=1, le=265` | el rango de zonas de la TLC. Atrapa datos de prueba inventados |
| 1 | `DOLocationID` `ge=1, le=265` | ídem |
| 1 | `trip_distance` `ge=0.0, lt=1e6, nullable=False` | cota **ancha a propósito**: ver criterio 6 |
| 2 | `volumen_minimo` (≥ 1.000 filas) | no protege el modelo: protege contra **silenciar un fallo de ingesta** |
| 2 | `outliers_de_distancia_son_marginales` | **el check que atrapa un cambio de unidades** |
| 3 | `dropoff_posterior_a_pickup` | un viaje no puede terminar antes de empezar |
| 3 | `velocidad_implicita_plausible` | coherencia entre distancia y duración |
| — | `Config.strict = False`, `coerce = True` | decisión declarada: el parquet trae ~20 columnas y solo importan 5 |

Y `ViajesProcesados` añade rangos **duros** más `target_no_constante` (que el `target`
binario tenga las dos clases): *"si `viaje_largo` es todo 0, cualquier clasificador da
100 % de accuracy y el estudiante aprende una lección equivocada"*.

**Cómo revisar el PR de un estudiante:** cuenta las reglas por nivel. El fallo nº 1 es
tener seis reglas **todas de nivel 1**. Pregunta directa que lo revela: *"si el
proveedor multiplica una columna por 1,6, ¿cuál de tus reglas se dispara?"* Si la
respuesta es "ninguna", falta el nivel 2.

## Criterio 2 — El contrato pasa sobre la partición real completa

```bash
uv run python -c "
import pandas as pd
from taxi.config import RAW_DIR, PARTICIONES_TRAIN
from taxi.data import contract as dc
df = pd.read_parquet(RAW_DIR / PARTICIONES_TRAIN[0].nombre_archivo)
dc.validar_crudos(df)
print(f'{len(df):,} filas: el contrato pasa sobre el dato real')
"
```

**Salida esperada:** `68,211 filas: el contrato pasa sobre el dato real`.

Este criterio existe porque su versión incumplida fue un bug real: el contrato original
exigía `trip_distance <= 100` **por fila** y `taxi data` fallaba en la primera
partición. Un contrato que no pasa sobre el dato real es un contrato que alguien va a
comentar.

## Criterio 3 — Tres `fixtures` rotos y sus tests

Archivos: [`tests/conftest.py`](../../../tests/conftest.py) y
[`tests/data/test_contrato_datos.py`](../../../tests/data/test_contrato_datos.py).

```bash
uv run pytest tests/data -q
```

Los tres `fixtures`, con el fallo real que reproduce cada uno:

| `Fixture` | Rompe | Fallo real |
|---|---|---|
| `df_crudo_en_kilometros` | unidades | el generador sintético del repo anterior documentaba km y alimentaba un modelo entrenado en millas |
| `df_crudo_zona_invalida` | zona 999 | datos de prueba inventados sin leer el diccionario de datos |
| `df_crudo_con_nulos` | nulos en `trip_distance` | descarga cortada, o `join` sin pareja |

El test es paramétrico, así que los tres se ven en la salida con su motivo.

**Detalle de diseño que hay que hacer notar en la revisión:** los `fixtures` se
**generan en código** con semilla fija, no se leen de un CSV commiteado. El
razonamiento está en el `docstring` del `conftest`: un CSV es opaco, se desactualiza y
no explica por qué está roto.

## Criterio 4 — Ningún `fixture` roto lanza excepción por sí mismo

Es el criterio que más PR devuelve, y no se comprueba leyendo: se comprueba ejecutando.

```bash
uv run python -c "
import sys; sys.path.insert(0, '.')
from tests.conftest import MILLAS_A_KM, generar_crudos
d = generar_crudos(filas=2000)
d['trip_distance'] = d['trip_distance'] * MILLAS_A_KM
print('media:', round(d.trip_distance.mean(), 3), '| dtype:', d.trip_distance.dtype)
print('nulos:', int(d.isna().sum().sum()), '| filas:', len(d))
print('ninguna excepcion: el dato roto es indistinguible sin contrato')
"
```

El `docstring` del `conftest` lo dice explícitamente:

> *"Ninguno de los tres lanza una excepción por sí mismo: los tres entrenan un modelo y
> producen un RMSE plausible. Ese es exactamente el punto del contrato."*

Si el `fixture` de un estudiante hace que `pandas` lance un `KeyError`, está
demostrando que su código atrapa errores ruidosos — que ya los atrapaba.

## Criterio 5 — El control negativo

Archivo: [`tests/data/test_niveles_de_check.py`](../../../tests/data/test_niveles_de_check.py),
`test_el_contrato_no_inventa_fallos`.

```python
def test_el_contrato_no_inventa_fallos() -> None:
    """Tres lotes independientes del fixture valido pasan los tres niveles.

    Un contrato que falla con datos buenos se desactiva en la primera semana.
    """
    for semilla in (1, 2, 3):
        dc.validar_crudos(generar_crudos(semilla=semilla))
```

**Regla de corrección: sin este test, el criterio 3 no vale nada.** Un contrato que
rechaza todo también rechaza los tres `fixtures` rotos. Es el mismo razonamiento que el
control negativo del detector de `drift` de la S07, y conviene señalar el parentesco.

## Criterio 6 — ≥ 1 check de nivel 2, calibrado con datos propios

Archivo: [`src/taxi/data/contract.py`](../../../src/taxi/data/contract.py),
`outliers_de_distancia_son_marginales`.

La tabla de calibración del caso guía, que es el formato que se le pide al estudiante:

| Regla | Valor medido | Umbral fijado | Margen |
|---|---|---|---|
| fracción de viajes > 100 millas | **0,054 %** (37 de 68.211, en 2023-01) | **0,3 %** | 5,5x |

Y el test que **atrapa el umbral por los dos lados**:

```python
proporcion_real_medida = 0.00054
assert proporcion_real_medida * 3 < dc.MAX_FRACCION_OUTLIERS, (
    "el umbral quedo demasiado cerca del ruido real de la TLC"
)
assert dc.MAX_FRACCION_OUTLIERS < 0.01, "un umbral tan alto ya no detecta un cambio de unidades"
```

Eso es lo que distingue un umbral **calibrado** de un número puesto a ojo: dos
aserciones con su razón escrita, una por cada forma de equivocarse.

**Motivo de devolución:** el estudiante copió `0.003` del curso. Se detecta porque su
`dataset` no tiene nada que ver y el número es el mismo.

## Criterio 7 — Descarga con hash

Archivo: [`src/taxi/data/loaders.py`](../../../src/taxi/data/loaders.py).

```bash
cat data/raw/metadata.json | head -20
git ls-files | grep metadata.json
```

Los cinco campos que tiene que llevar: `url`, `sha256`, `bytes`, `fuente`, `licencia`.

Y el mecanismo que le da sentido, que es lo que hay que buscar en el PR del estudiante:
el aviso cuando el hash **no coincide**.

```python
if esperado and actual != esperado:
    logger.warning(
        "HASH DISTINTO para %s ... El proveedor republico el archivo. "
        "Las metricas calculadas con la version anterior ya no son comparables.",
        ...,
    )
```

Un hash que se registra y nunca se compara no sirve de nada. La demostración en vivo
está en [`versionado-de-datos.md`](../versionado-de-datos.md) sección 2.

**Trampa habitual:** el `metadata.json` no aparece en `git ls-files` porque el
`.gitignore` tiene `*.json` global. Es un bug real de este repositorio, y por eso el
`.gitignore` actual lleva `!**/metadata.json`.

## Criterio 8 — Particiones fijas, sin `datetime.now()`

Archivo: [`src/taxi/config.py`](../../../src/taxi/config.py).

```bash
grep -rn "datetime.now\|date.today" src/
# no debe aparecer en la seleccion de particiones
```

El `docstring` del módulo documenta el bug que esto corrige: el módulo de orquestación
calculaba el periodo con `datetime.now()` y pedía `green_tripdata_2025-01.parquet`, *"un
parquet que puede no estar publicado"*. Razonamiento completo en el
[ADR 001](../../../docs/adr/001-caso-guia-y-particiones.md).

## Criterio 9 — `Split` temporal, o la justificación

Archivo: [`src/taxi/config.py`](../../../src/taxi/config.py) — `PARTICIONES_TRAIN`,
`PARTICION_VALID`, `PARTICION_TEST`, `PARTICIONES_PRODUCCION`.

Lo que hay que verificar en el PR, y en este orden:

1. el `holdout` **no** se usa para seleccionar hiperparámetros. Si se usa, el `gate` de
   la S06 deja de medir generalización;
2. las particiones no se solapan;
3. si el `dataset` no tiene eje temporal, **los tres puntos** de la justificación están
   escritos, incluido el de cómo simulará referencia vs producción en la S07.

El punto 3 es el que hay que leer con atención: es donde se decide si el proyecto podrá
completar la fase de monitoreo, que vale un 15 % de la rúbrica.

## Criterio 10 — La medición `TimeSeriesSplit` vs `KFold(shuffle=True)`

Notebook: [`notebooks/02-validacion-temporal-y-leakage.ipynb`](../notebooks/02-validacion-temporal-y-leakage.ipynb) sección 2.

Medido en el caso guía, sobre 144 días de serie diaria de demanda, mismo modelo y
mismas features:

| Esquema | RMSE medio |
|---|---|
| `TimeSeriesSplit(n_splits=5)` | **184,6** |
| `KFold(n_splits=5, shuffle=True)` | 166,0 |

El `KFold` aleatorio reporta un RMSE un **10,1 %** mejor.

**Lo que se evalúa no es la magnitud, es la interpretación.** Una respuesta buena dice
las dos cosas: que la dirección del sesgo es predecible (cada `fold` de `test` queda
rodeado de vecinos que están en `train`, y con lags autocorrelacionados eso es casi
tener la respuesta) y que la magnitud depende del `dataset`. Una respuesta mala dice
*"KFold da mejores resultados"*.

Y el matiz que sube la nota si aparece: `TimeSeriesSplit` tampoco es automáticamente
correcto si tus features usan ventanas largas — hace falta `gap`.

## Criterio 11 — `docs/dataset-card.md`

Referencia completa: [`dataset-card.md`](../dataset-card.md) de esta sesión, que está
rellena de verdad.

Rúbrica, por orden de lo que más suele faltar:

| Señal | Qué significa |
|---|---|
| Las cinco secciones existen y no tienen `TODO` | mínimo |
| Las **unidades** están declaradas por columna | entendió el incidente de la sesión |
| Los nulos distinguen **estructural** de **fallo de captura** | pensó en el dato, no solo en el `dtype` |
| Hay **≥ 3 sesgos** con **evidencia medida** | el fallo más común es escribir sesgos genéricos sin número |
| Dice qué **no** se puede hacer con el `dataset` | entendió validez externa |

*"No conozco sesgos conocidos"* no es aceptable para ningún `dataset` real. Si el
estudiante no encuentra ninguno, no ha buscado.

## Criterio 12 — La tabla de disponibilidad temporal por feature

Referencia: [`dataset-card.md`](../dataset-card.md) sección 7.

La fila que hay que buscar es la que tiene un **matiz**, no la que dice "sí" a todo. En
el caso guía es `trip_distance`: es la distancia **registrada** por el taxímetro, que
solo se conoce al final del viaje. Para una ETA honesta habría que usar la distancia
**estimada** de la ruta. El curso usa la registrada por simplicidad didáctica **y lo
declara**.

Un estudiante que encuentre un matiz así en su `dataset` ha entendido el `leakage` mejor
que uno que ponga "sí" en las doce filas.

## Criterio 13 — El CI corre los tests de datos

Archivo: [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml), `job` `tests`.

```bash
grep -rn -E "continue-on-error|\|\| *true|\|\| *echo" .github/workflows/
# cualquier resultado es motivo de devolucion
```

Y la comprobación de que los tests de datos **no necesitan red**: es lo que permite que
el CI los corra en cada PR sin depender de que la TLC esté disponible.

---

## El bloque que hay que discutir aunque no sea un criterio

**El límite honesto del contrato** ([README](../README.md) sección 4). Es el contenido más
valioso de la sesión y no se puede evaluar con un `grep`, así que conviene sacarlo en la
revisión oral:

| | parquet real, millas | parquet real, "km" |
|---|---|---|
| fracción > 100 | 0,000542 (37 viajes) | 0,000557 (38 viajes) |
| mediana | 1,85 | 2,98 |
| mediana de velocidad implícita | 10,63 mph | 17,10 mph |
| **veredicto del contrato** | **PASA** | **PASA** |

El contrato **no atrapa** el cambio de unidades sobre el lote real, porque el green taxi
es abrumadoramente urbano y no tiene cola larga suficiente. El `fixture` sintético sí lo
atrapa porque tiene una cola diseñada de 70-95 millas.

Lo que sí lo detecta: `KS` contra una referencia, con `D = 0,2513` frente a un ruido de
`D = 0,0069`. Es decir, `drift`, y es la S07.

**El estudiante que llegue a esta conclusión por su cuenta en el extra 1 del taller ha
entendido la sesión completa.** Los que copien un contrato de un tutorial creerán que
un contrato lo detecta todo, y ese es el error que esta sesión existe para prevenir.

---

## Tiempos del taller, para el instructor

55 minutos y **no** alcanza para los siete puntos. Lo que se espera al final de la
clase, en orden de prioridad:

| Prioridad | Puntos | Por qué |
|---|---|---|
| Imprescindible | 1, 3, 5 (contrato con los tres niveles, `fixtures` rotos, control negativo) | es el núcleo conceptual y lo que se evalúa de verdad |
| En clase si da tiempo | 2, 4, 7 (pasa sobre el dato real, hash, CI) | son mecánicos con las referencias delante |
| Tarea, y va al hito 1 | 5 (`split`), 6 (`dataset card`) | requieren medir y escribir; la ficha es la mitad del hito |

Recomendación: pedir el PR abierto **al final de la clase** aunque esté incompleto, con
la descripción diciendo qué falta. Y recordar en voz alta que **el hito 1 se entrega 5
días después**, así que lo que quede a medias tiene fecha.

### Los cuatro errores que más PR devuelven, por frecuencia

1. **Seis reglas, todas de nivel 1.** No detectan nada sistemático.
2. **Falta el control negativo.** El criterio 3 pasa y no demuestra nada.
3. **Umbrales copiados del curso.** `0.003` sobre un `dataset` que no es el de la TLC.
4. **`Fixtures` rotos que lanzan excepciones.** Demuestran lo contrario de lo que se
   pedía.
