# Dataset card — NYC Green Taxi Trip Records (caso guía del curso)

> **Doble propósito.** Esta ficha documenta el `dataset` del caso guía **y** sirve de
> plantilla para la tuya. La versión con `TODO(estudiante)` para rellenar está en
> [`proyecto/starter-template/docs/dataset-card.md`](../../proyecto/starter-template/docs/dataset-card.md);
> lo que tienes aquí es el mismo esquema **relleno de verdad**, para que se vea el
> nivel de detalle que se espera.
>
> **Fecha de esta ficha:** 19 de agosto de 2026.
> **Todas las cifras están medidas**, no estimadas. Cada sección lleva el comando que
> las reproduce.

Se documenta el dato con el mismo rigor con el que se documenta el modelo. No es
burocracia: es lo que permite que otra persona —tu revisor, tú en tres meses, un
auditor— sepa qué se midió, con qué población y con qué sesgos. Y hay un motivo
inmediato: **la ficha es el único sitio donde existen las unidades de las columnas.**
El incidente central de esta sesión —`trip_distance` de millas a kilómetros— es
indetectable sin ella, porque un `float64` no lleva sus unidades encima.

---

## 1. Identificación

| Campo | Valor |
|---|---|
| Nombre | NYC TLC Trip Record Data — **Green Taxi** |
| Proveedor | New York City Taxi and Limousine Commission (TLC) |
| Página oficial | [nyc.gov/site/tlc/about/tlc-trip-record-data.page](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) |
| Diccionario de datos oficial | [Green Taxi Trips data dictionary (PDF)](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_green.pdf) |
| URL base de descarga | `https://d37ci6vzurychx.cloudfront.net/trip-data` |
| Formato | Apache Parquet, un archivo por mes |
| Licencia | **Datos públicos** de la NYC TLC, uso libre con atribución. Ver las [Terms of Use del portal de datos de la ciudad](https://www.nyc.gov/home/terms-of-use.page) |
| Fecha de descarga de esta cohorte | 19 de agosto de 2026 |
| Hashes de las particiones | `data/raw/metadata.json` (SHA-256 por archivo, registrado en cada descarga) |
| Tamaño por partición | ~1,4 MB comprimido (2023-01: **1.427.002 bytes**) |
| Dimensiones por partición | **68.211 filas × 20 columnas** en 2023-01 |
| Declarado en código | [`src/taxi/config.py`](../../src/taxi/config.py) |

**Atribución que hay que incluir** si publicas resultados: *"Datos de viajes de la New
York City Taxi and Limousine Commission (TLC)."* La TLC además advierte que los datos
son recogidos por proveedores autorizados (los `technology service providers` que
operan los taxímetros) y que **la TLC no revisó la exactitud de cada registro** — lo
cual es, por sí solo, la mejor justificación posible para tener un contrato de datos.

```bash
# Reproducir descarga y procedencia
uv run taxi data
cat data/raw/metadata.json
```

---

## 2. Cumplimiento de los requisitos duros del curso

Contrastado contra la tabla de
[`proyecto/README.md`](../../proyecto/README.md).

| Requisito | ¿Cumple? | Evidencia |
|---|---|---|
| Eje temporal explícito | **Sí** | `lpep_pickup_datetime`, `lpep_dropoff_datetime` |
| ≥ 2 particiones separables (referencia vs producción) | **Sí** | `train` 2023-01..03, `valid` 2023-04, `holdout` 2023-05, producción 2023-07 y 2024-01 |
| ≤ 500 MB, descargable sin autenticación | **Sí** | ~1,4 MB por mes, HTTPS público sin cuenta |
| ≥ 3 categóricas y ≥ 3 numéricas, con **nulos reales** | **Sí** | categóricas: `PULocationID`, `DOLocationID`, `payment_type`, `trip_type`, `RatecodeID`. Numéricas: `trip_distance`, `fare_amount`, `total_amount`, `tip_amount`. Nulos reales: sección 4 |
| Métrica de negocio articulable | **Sí** | error en minutos de la ETA que se le muestra al pasajero; y el coste asimétrico de prometer 10 min y tardar 25 |
| Licencia que permite uso educativo | **Sí** | datos públicos con atribución |

> **Nota para el estudiante:** el caso guía **puede** usarse en el proyecto, pero
> [`proyecto/README.md`](../../proyecto/README.md) recomienda no hacerlo: el
> repositorio del curso ya lo resuelve, así que copiar es trivial y aprender es cero.

---

## 3. Esquema y significado de las columnas

Las **unidades no son un detalle**. Es la sección que evita el incidente de la sección 1 del
[README](README.md).

### Columnas que el `pipeline` del curso usa

| Columna | Tipo | Unidades | Nulos | Significado |
|---|---|---|---|---|
| `lpep_pickup_datetime` | `datetime64[us]` | — (hora local de NY, sin `timezone` declarada) | 0 % | instante de inicio del viaje |
| `lpep_dropoff_datetime` | `datetime64[us]` | ídem | 0 % | instante de fin. **Es la fuente del `target`** |
| `PULocationID` | `int` | ID de zona TLC, **1-265** | 0 % | zona de recogida. Es un **ID categórico**: la zona 42 no es "mayor" que la 41 |
| `DOLocationID` | `int` | ID de zona TLC, **1-265** | 0 % | zona de destino |
| `trip_distance` | `float64` | **MILLAS** | 0 % | distancia registrada por el taxímetro. **La unidad es lo único que impide el incidente del cambio de escala** |

### Columnas presentes que el `pipeline` **no** usa, y por qué

| Columna | Unidades | Nulos | Por qué no se usa |
|---|---|---|---|
| `VendorID` | código (1, 2) | 0 % | identifica al proveedor tecnológico del taxímetro. Útil para diagnosticar, no como feature |
| `passenger_count` | personas | **6,34 %** | lo declara el conductor, no el taxímetro: es poco fiable, y sus nulos son sistemáticos (sección 4) |
| `RatecodeID` | código | 6,34 % | ídem |
| `store_and_fwd_flag` | `Y`/`N` | 6,34 % | metadato de transmisión |
| `payment_type` | código | 6,34 % | **se conoce al final del viaje**: usarlo para predecir la duración sería `leakage` |
| `trip_type` | código (1 = `street-hail`, 2 = `dispatch`) | 6,35 % | mismo problema de disponibilidad temporal |
| `fare_amount`, `total_amount`, `tip_amount`, `extra`, `mta_tax`, `tolls_amount`, `improvement_surcharge`, `congestion_surcharge` | USD | 0-6,34 % | **`LEAKAGE`**: la tarifa se calcula **con** el tiempo del viaje. Ver [README](README.md) sección 7 |
| `ehail_fee` | USD | **100 %** | la columna existe y está **completamente vacía** en todas las particiones. Es un buen recordatorio de que "la columna existe" no significa "la columna tiene datos" |

### Columnas **derivadas** por el `pipeline`

Definidas en un solo sitio,
[`src/taxi/features/contract.py`](../../src/taxi/features/contract.py):

| Columna | Cómo se calcula | Unidades | Por qué |
|---|---|---|---|
| `duration` | `dropoff - pickup` | **minutos** | el `target` de regresión |
| `viaje_largo` | `duration > 30` | 0/1 | `target` de clasificación derivado, para poder enseñar umbrales y matriz de costes **sin traer un segundo dataset** |
| `PU_DO` | `PULocationID + "_" + DOLocationID` | categoría | la ruta como unidad: (Harlem → JFK) tiene comportamiento propio que las dos zonas por separado no expresan |
| `hora_pickup` | `pickup.dt.hour` | 0-23 | el tráfico de NY a las 8 de un martes no se parece al de las 3 de un domingo |
| `dia_semana_pickup` | `pickup.dt.dayofweek` | 0-6 (0 = lunes) | ídem |

**El orden importa y está separado a propósito:** las zonas se castean a `str` **solo
al construir features**, nunca sobre el parquet crudo. Castear el crudo completo era la
causa del `KeyError: "['PU_DO'] not in index"` que impedía arrancar el `pipeline`
estrella del curso anterior.

```bash
# Reproducir el esquema y los nulos
uv run python -c "
import pandas as pd
df = pd.read_parquet('data/raw/green_tripdata_2023-01.parquet')
print(df.shape); print(df.dtypes)
print((df.isna().mean() * 100).round(2).to_string())
"
```

---

## 4. Nulos: por qué los hay y qué se hace con ellos

Aquí está la razón por la que este `dataset` sirve para enseñar: **sus nulos no son
aleatorios.**

Medido en 2023-01: seis columnas —`store_and_fwd_flag`, `RatecodeID`,
`passenger_count`, `payment_type`, `trip_type`, `congestion_surcharge`— tienen
**exactamente el mismo 6,34 %** de nulos. Y no es coincidencia:

| Hecho medido | Valor |
|---|---|
| Filas con **alguna** de esas seis columnas nula | 4.334 |
| Filas con **las seis a la vez** nulas | **4.324** |
| `VendorID` de esas filas | los dos (2: 4.196 · 1: 128) |

Es decir: hay ~4.300 registros a los que les falta **el bloque completo** de campos que
declara el conductor y el sistema de tarifas. Eso no es "ruido": es un **camino de
ingesta distinto** —registros que entraron sin pasar por el flujo normal del taxímetro—
y produce un patrón de nulos **estructurado**.

### La distinción que hay que hacer siempre

| Tipo de nulo | Qué significa | Qué se hace |
|---|---|---|
| **Estructural** | el campo **no aplica** a ese registro. `ehail_fee` en un viaje que no fue un `e-hail`; `congestion_surcharge` en un viaje anterior a que existiera el recargo | no se imputa: se modela la ausencia (una categoría "no aplica", o un indicador booleano) |
| **Fallo de captura** | el valor existía y **se perdió**. El bloque de seis columnas de arriba | se decide por columna, y se **registra** cuántos había |
| **No visto todavía** | el valor **aún no existe** en el instante de la predicción | **no es un nulo que imputar: es `leakage` si lo usas.** Ver [README](README.md) sección 7 |

### Y por qué `fillna(0)` no es una estrategia

> **`df.fillna(0)` no es un valor por defecto: es una decisión oculta.** Un `0` en
> `trip_distance` significa "viaje de distancia nula", que es una afirmación **distinta**
> de "no sé cuánto midió". El modelo aprende esos ceros como reales, la media se sesga
> hacia abajo, y en producción la única señal de que algo va mal es una métrica que
> empeora un poco.

Lo correcto: decidir **por columna**, imputar **dentro de un `Pipeline`** (para que el
`fit` del `imputer` no vea `test` — [README](README.md) sección 7) y dejar la decisión escrita
en esta ficha.

**Qué hace el caso guía:** las cinco columnas que el `pipeline` usa **no tienen
nulos** (0 % medido), así que no hay imputación. Es una situación afortunada y hay que
decirlo: no es que el problema esté resuelto, es que no aparece con estas cinco
columnas. Lo que sí hay es un `check` de contrato que exige `nullable=False` en las
cinco, de modo que **si un día aparecen, el `pipeline` falla ruidosamente** en lugar de
imputar por su cuenta.

---

## 5. Población representada, y sesgos conocidos

**Esta es la sección que casi nadie escribe, y la que más ahorra.**

### Qué población es, exactamente

`Green taxi` **no es "los viajes de Nueva York"**. Los *boro taxis* verdes se crearon
en 2013 con una restricción geográfica explícita: pueden recoger pasajeros a mano
alzada **solo** fuera del núcleo de Manhattan (por encima de la calle 96 al este y de
la 110 al oeste) y en los `boroughs` exteriores, aunque pueden **dejar** pasajeros en
cualquier sitio.

Consecuencias directas, y son limitaciones del **modelo**, no del `dataset`:

1. **Un modelo entrenado con esto no generaliza a Manhattan sur.** La distribución de
   `PULocationID` está estructuralmente sesgada por regulación.
2. **No representa el mercado de viajes en coche de la ciudad.** Los `for-hire
   vehicles` (Uber, Lyft) son hoy un volumen mucho mayor, y tienen su propio `dataset`
   en el portal de la TLC. Extrapolar de green taxi a "movilidad en NYC" es un error de
   validez externa.
3. **Es una flota en declive.** El volumen de viajes de green taxi ha caído
   sostenidamente, lo que significa que las particiones más recientes tienen menos
   filas y, posiblemente, una composición distinta de conductores y zonas. Medido en
   este repositorio: **68.211** filas en 2023-01 frente a **56.551** en 2024-01.

### Otros sesgos y artefactos, medidos

| Sesgo o artefacto | Evidencia medida | Consecuencia |
|---|---|---|
| **Datos declarados por el proveedor, sin auditar** | la propia TLC advierte que no verificó la exactitud de los registros | el contrato de datos no es opcional |
| **`Timestamps` de otros periodos** dentro del archivo del mes | 2023-01 contiene **4 filas** con `pickup` fuera de enero de 2023; los años presentes son **2009, 2022 y 2023** | cualquier agregación temporal debe recortar al rango **declarado**, no confiar en el nombre del archivo. Es lo que hace el [notebook 02](notebooks/02-validacion-temporal-y-leakage.ipynb) |
| **Outliers de distancia** | **37 viajes de más de 100 millas** en 68.211 (**0,054 %**), uno de **120.098,84** | motiva la cota ancha por fila + el `check` de fracción ([README](README.md) sección 3) |
| **Duraciones imposibles** | viajes de 0 minutos y de varias horas | filtro de negocio `[1, 60]` minutos, **contabilizado** en el log |
| **Estacionalidad fuerte** | verano frente a invierno; ver [S07](../s07-monitoreo/README.md) | `drift` de datos que **no** es degradación: reentrenar sería perseguir la propia cola |
| **`target` desbalanceado** | `viaje_largo` positivo en el **6,0 %** (2023-01) a **8,5 %** (2023-05) de los viajes válidos; **7,18 %** agregando las siete particiones | `accuracy` es una métrica inútil aquí: predecir siempre "no" da ~93 %. Hay que usar `precision`/`recall` y un umbral decidido con la matriz de costes |
| **Sin `timezone` declarada** | los `timestamps` no llevan `tz` | los cambios de horario de verano introducen una hora duplicada y una ausente cada año. Irrelevante para el error de un modelo de duración; **letal** si agregas por hora sobre el cambio |
| **Sin información del pasajero** | por diseño de la TLC | no hay datos personales, lo que reduce el riesgo de privacidad; y **no se puede** auditar sesgo por grupo demográfico, solo por **zona** (que en NYC correlaciona con renta y con composición racial) |

### Nota de verificación sobre la tasa de positivos

El [ADR 001](../../docs/adr/001-caso-guia-y-particiones.md) menciona una distribución de
`viaje_largo` de "~27 % de positivos". **Medido en este repositorio con
`UMBRAL_VIAJE_LARGO_MIN = 30` minutos y el filtro de negocio vigente, la tasa está
entre el 6,0 % y el 8,5 % por partición (7,18 % agregado).** Se deja constancia aquí en
lugar de repetir la cifra del ADR: la ficha del `dataset` es el sitio donde las cifras
se miden, y una cifra heredada sin verificar es exactamente el problema que este curso
enseña a evitar.

Comando para re-verificarlo antes de cada cohorte:

```bash
uv run python -c "
import pandas as pd
from taxi.config import (
    DURACION_MAX_MIN, DURACION_MIN_MIN, PARTICIONES_TRAIN, PARTICION_VALID,
    PARTICION_TEST, PARTICIONES_PRODUCCION, RAW_DIR, UMBRAL_VIAJE_LARGO_MIN,
)
for p in [*PARTICIONES_TRAIN, PARTICION_VALID, PARTICION_TEST, *PARTICIONES_PRODUCCION]:
    df = pd.read_parquet(RAW_DIR / p.nombre_archivo)
    d = (df.lpep_dropoff_datetime - df.lpep_pickup_datetime).dt.total_seconds() / 60
    v = d.between(DURACION_MIN_MIN, DURACION_MAX_MIN) & df.trip_distance.le(100)
    print(p.etiqueta, f'{100 * (d[v] > UMBRAL_VIAJE_LARGO_MIN).mean():.2f}%')
"
```

**Si el umbral de negocio fuera otro** —digamos 20 minutos— la tasa cambiaría por
completo. Eso también hay que decirlo: `viaje_largo` no es una propiedad del `dataset`,
es una **decisión** con un número dentro, y el número está en
[`src/taxi/config.py`](../../src/taxi/config.py).

---

## 6. Particiones

Fijas y declaradas en [`src/taxi/config.py`](../../src/taxi/config.py). **Nunca
`datetime.now()`** ([ADR 001](../../docs/adr/001-caso-guia-y-particiones.md)).

| Partición | Periodo | Filas crudas | Filas válidas tras el filtro | Uso |
|---|---|---|---|---|
| `PARTICIONES_TRAIN` | 2023-01 | 68.211 | 65.909 | entrenamiento |
| | 2023-02 | 64.809 | 62.536 | entrenamiento |
| | 2023-03 | 72.044 | 69.338 | entrenamiento |
| `PARTICION_VALID` | 2023-04 | 65.392 | 62.942 | selección de hiperparámetros |
| `PARTICION_TEST` | 2023-05 | 69.174 | 66.269 | **`holdout` fijo: el juez del `gate` de promoción (S06)** |
| `PARTICIONES_PRODUCCION` | 2023-07 | 61.343 | 58.671 | "producción simulada" — estacionalidad de verano |
| | 2024-01 | 56.551 | 54.331 | "producción simulada" — un año de distancia |

Filas medidas el 19 de agosto de 2026. "Filtro" = duración en `[1, 60]` minutos y
`trip_distance ≤ 100` millas. Además, el `pipeline` **muestrea** a
`FILAS_POR_PARTICION = 60.000` de forma determinista con `SEMILLA = 42`, para que
entrenar tome segundos en clase.

Tres propiedades de este diseño que hay que entender:

1. **El `split` es temporal, no aleatorio.** Se entrena con meses anteriores y se
   evalúa con posteriores, porque en producción el modelo siempre predice sobre el
   futuro ([README](README.md) sección 7).
2. **El `holdout` tiene un rol exclusivo.** 2023-05 no participa en la selección de
   modelo ni de hiperparámetros. Si se usa para tunear, el `gate` de la S06 deja de
   medir generalización y pasa a medir cuánto se sobreajustó la búsqueda al juez.
3. **El `drift` de la S07 es real, no sintético.** 2023-07 aporta estacionalidad de
   verano y 2024-01 está a un año, con cambios de tarifa y de patrones de movilidad. No
   hace falta inyectar ruido con `numpy`.

---

## 7. Disponibilidad temporal de cada feature

La tabla que responde *"¿este valor estaba disponible en el momento de la
predicción?"* sin discutirlo en un PR. Es el instrumento que detecta `leakage` sin
entrenar nada ([README](README.md) sección 7), y **se pide en el taller**.

Escenario de referencia: se predice la **duración del viaje en el instante de la
recogida**, para mostrar una ETA al pasajero.

| Feature | Disponible en `t = pickup` | Comentario |
|---|---|---|
| `hora_pickup`, `dia_semana_pickup` | **Sí** | derivadas del propio instante |
| `PULocationID` | **Sí** | es dónde estás |
| `DOLocationID`, `PU_DO` | **Sí** | el destino se declara al subir |
| `trip_distance` | **Sí, con matiz importante** | es la distancia **registrada** por el taxímetro, que solo se conoce al final. Para una ETA honesta hay que usar la distancia **estimada** de la ruta. El caso guía usa la registrada por simplicidad didáctica, y **eso es una limitación declarada**, no un descuido |
| `payment_type`, `trip_type` | **No** | se conocen al liquidar el viaje |
| `fare_amount`, `total_amount`, `tip_amount` | **No** | se calculan **con** la duración: `leakage` directo |
| `lpep_dropoff_datetime` | **No** | es el `target` |
| `velocidad_media` (si se calculara) | **No** | divide por el `target` |

El matiz de `trip_distance` es el más instructivo de la tabla, porque es el tipo de
cosa que se descubre en producción: el modelo validaba perfectamente y en el mundo real
no tenía esa columna con ese valor. **Un `leakage` declarado es manejable; uno
escondido rompe el sistema.**

---

## 8. Limitaciones y usos no apropiados

**Limitaciones**

- No generaliza a Manhattan sur, ni a `for-hire vehicles`, ni a otras ciudades (sección 5).
- `trip_distance` es *post hoc* (sección 7): el caso guía asume una simplificación.
- El bloque de ~6,3 % de registros sin campos declarados por el conductor limita
  cualquier análisis que los use (sección 4).
- Sin `timezone` en los `timestamps` (sección 5).
- No hay atributos de la persona, así que **no se puede auditar sesgo demográfico
  directamente**; solo por zona, que es un `proxy` imperfecto y correlacionado con
  renta.
- Datos de 2023-2024, no del mes corriente. Es deliberado: la reproducibilidad entre
  cohortes vale más que la sensación de actualidad
  ([ADR 001](../../docs/adr/001-caso-guia-y-particiones.md)).

**Usos que serían inapropiados**

- **Fijar tarifas o penalizar conductores.** El dato no fue auditado por la TLC y los
  outliers son sistemáticos.
- **Cualquier inferencia sobre personas o grupos.** La zona no es una persona, y usarla
  como `proxy` demográfico es precisamente el tipo de uso que el
  [AI Act](../s07-monitoreo/gobernanza.md) mira con lupa.
- **Planificación urbana** sin combinarlo con el `dataset` de FHV, por el sesgo de
  cobertura de sección 5.

**Clasificación regulatoria del caso guía:** predecir la duración de un viaje para
mostrar una ETA **no** es un sistema de alto riesgo bajo el AI Act. Y eso es
didácticamente útil: lo que mueve la clasificación no es la técnica —el mismo XGBoost—
sino **sobre quién decide y con qué consecuencia**. El recorrido completo de variantes
está en [`sesiones/s07-monitoreo/gobernanza.md`](../s07-monitoreo/gobernanza.md).

---

## 9. Mantenimiento de esta ficha

| Cuándo | Qué se revisa |
|---|---|
| Al inicio de cada cohorte | los hashes de `data/raw/metadata.json`; las URL; que las cifras de sección 3, sección 5 y sección 6 sigan siendo las medidas |
| Si el proveedor republica un archivo | el `loader` avisa con `HASH DISTINTO`. Hay que anotarlo aquí y **revisar la comparabilidad** de las métricas históricas |
| Si cambia `UMBRAL_VIAJE_LARGO_MIN` o el filtro de duración | las tasas de sección 5 y las filas válidas de sección 6 |
| Si se añade una columna al `pipeline` | sección 3 y sección 7, **antes** de entrenar con ella |

**Responsable:** el equipo docente del curso. En tu proyecto, una persona con nombre.

---

## 10. Cómo usar esta ficha como plantilla

Copia las diez secciones y rellénalas para tu `dataset`. Lo que se evalúa en el
[hito 1](../../proyecto/README.md) no es la extensión, es que estas cinco cosas estén y
sean **verificables**:

1. **Procedencia y licencia** con nombre exacto y URL, más el hash de tus particiones.
2. **Unidades de cada columna.** Es la sección que evita el incidente de esta sesión.
3. **Nulos por columna**, distinguiendo estructural de fallo de captura, con la
   decisión escrita. Nada de `fillna(0)` sin justificar.
4. **Población representada y sesgos conocidos.** Al menos tres, con evidencia medida.
   "No conozco sesgos" no es una respuesta aceptable para ningún `dataset` real.
5. **Disponibilidad temporal por feature** (sección 7). Es lo que demuestra que entendiste el
   `leakage`.

Y un consejo práctico: **escribe la ficha antes de entrenar.** Si la escribes después,
se convierte en una justificación de lo que ya hiciste en lugar de en la herramienta
que te habría avisado.

---

Volver: [README de la sesión](README.md) · [`taller.md`](taller.md) ·
[`versionado-de-datos.md`](versionado-de-datos.md) ·
[`proyecto/starter-template/docs/dataset-card.md`](../../proyecto/starter-template/docs/dataset-card.md)
