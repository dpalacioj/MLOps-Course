# Datasets curados

Diez datasets **verificados contra los requisitos duros** de
[`README.md`](README.md) sección 3. Si eliges de aquí, arrancas sin riesgo de descubrir en
la sesión 7 que tu dataset no permite hacer monitoreo.

**Fecha de verificación: 19 de agosto de 2026.** Todas las URLs de la tabla
principal se comprobaron ese día: respondieron HTTP 200 sin autenticación, y en los
casos marcados como "esquema inspeccionado" se descargó el archivo y se contaron
filas, columnas, nulos y rango temporal.

**Verifica de nuevo antes de comprometerte.** Los proveedores mueven archivos. Un
comando basta:

```bash
curl -s -o /dev/null -w '%{http_code} %{size_download}\n' -L <url>
```

Si una URL de esta lista está muerta cuando la pruebes, avísale al instructor: una
lista "curada" con enlaces muertos es peor que no tener lista.

---

## Tabla resumen

| # | Dataset | Tamaño aprox. | Problema | Eje temporal | Verificación |
|---|---|---|---|---|---|
| 1 | Divvy Bikes (Chicago) | 5-30 MB / mes | Regresión (duración) o clasificación (tipo de usuario) | `started_at` por segundo | 200 + esquema inspeccionado |
| 2 | Capital Bikeshare (Washington DC) | 9-24 MB / mes | Igual que Divvy | `started_at` por segundo | 200 + esquema inspeccionado |
| 3 | Citi Bike — Jersey City | ~2 MB / mes | Igual, en volumen pequeño | `started_at` por segundo | 200 |
| 4 | Beijing Multi-Site Air Quality (UCI 501) | 8 MB (todo) | Regresión (PM2.5) | `year/month/day/hour`, 2013-03 a 2017-02 | 200 + esquema inspeccionado |
| 5 | Online Retail II (UCI 502) | 45 MB (todo) | Regresión (importe), clasificación (devolución), demanda | `InvoiceDate`, 2009-12 a 2011-12 | 200 + esquema inspeccionado |
| 6 | Metro Interstate Traffic Volume (UCI 492) | 400 KB (todo) | Regresión (volumen de tráfico) | `date_time` horario, 2012-10 a 2018-09 | 200 + esquema inspeccionado |
| 7 | Chicago Taxi Trips (Socrata) | según consulta | Regresión (duración, tarifa, propina) | `trip_start_timestamp`, 2013 a hoy | 200 vía API |
| 8 | UK Road Safety — STATS19 (DfT) | ~20 MB / año | Clasificación (severidad) | `date` + `time`, un archivo por año | 200 + esquema inspeccionado |
| 9 | NYC TLC Green Taxi | 1-2 MB / mes | Regresión (duración) | `lpep_pickup_datetime` | 200 |
| 10 | Inside Airbnb | 5-8 MB / snapshot | Regresión (precio) | `last_scraped` por snapshot mensual | 200 (URLs rotan, ver aviso) |

---

## 1. Divvy Bikes — Chicago

- **URL:** `https://divvy-tripdata.s3.amazonaws.com/YYYYMM-divvy-tripdata.zip`
  (ejemplo verificado: `202401-divvy-tripdata.zip`, 5.4 MB; `202407`, 29 MB)
- **Índice:** <https://divvybikes.com/system-data>
- **Tamaño:** 5-30 MB por mes comprimido, según estacionalidad. Un año entero cabe
  de sobra en 500 MB.
- **Problema:** regresión de la duración del viaje (`ended_at - started_at`), o
  clasificación `member` vs `casual`.
- **Eje temporal:** `started_at` / `ended_at`, precisión de segundos.
- **Referencia vs producción:** un mes de invierno contra uno de verano. El `drift`
  es enorme y **real**: en Chicago el volumen de julio es cinco veces el de enero y
  el mix `member/casual` cambia por completo. Es exactamente la discusión que la
  sesión 7 busca: ¿es `drift` o es estacionalidad esperada?
- **Features:** 3 categóricas nativas (`rideable_type`, `member_casual`,
  `start_station_name`) + `end_station_name`; numéricas: 4 coordenadas + duración y
  features de calendario derivadas.
- **Nulos reales (verificado, 202401):** `start_station_name` 19 165 / 144 873
  (13 %), `end_station_name` 20 749, `end_lat`/`end_lng` 288.
- **Licencia:** [Divvy Data License Agreement](https://divvybikes.com/data-license-agreement)
  (verificada, 200). Permite uso no comercial con atribución.
- **Trampa conocida:** los nulos de estación **no son un fallo de captura**: son
  viajes con bicicletas sin anclaje (`dockless`) que terminaron fuera de una
  estación. Imputarlos con "desconocido" es correcto; borrar esas filas elimina el
  13 % de los datos y sesga el modelo hacia los viajes entre estaciones. Además el
  esquema cambió en abril de 2020: los archivos anteriores tienen columnas distintas
  (`gender`, `birthyear`). No mezcles las dos épocas.

## 2. Capital Bikeshare — Washington DC

- **URL:** `https://s3.amazonaws.com/capitalbikeshare-data/YYYYMM-capitalbikeshare-tripdata.zip`
  (verificado: `202401`, 8.8 MB; `202407`, 24 MB)
- **Índice:** <https://capitalbikeshare.com/system-data>
- **Esquema idéntico al de Divvy** (los dos operan sobre Lyft/Motivate), así que
  todo lo dicho arriba aplica. Nulos verificados en 202401: `start_station_name`
  32 648 de 200 000 filas leídas.
- **Licencia:** [Capital Bikeshare Data License Agreement](https://capitalbikeshare.com/data-license-agreement)
  (verificada, 200).
- **Trampa conocida:** la misma de los nulos de estación. Y ojo con **no** usarlo si
  tu compañero de al lado eligió Divvy: los proyectos van a salir casi idénticos y
  el `peer review` lo va a notar.

## 3. Citi Bike — Jersey City

- **URL:** `https://s3.amazonaws.com/tripdata/JC-YYYYMM-citibike-tripdata.csv.zip`
  (verificado: `JC-202401`, 1.9 MB)
- **Índice:** <https://citibikenyc.com/system-data>
- **Por qué está en la lista:** mismo esquema que los anteriores pero en volumen
  pequeño (~50 k viajes/mes). Si trabajas en una máquina modesta o quieres que cada
  iteración tarde segundos, es la mejor opción de las tres.
- **Licencia:** [Citi Bike Data Use Policy](https://citibikenyc.com/data-sharing-policy).
- **Trampa conocida:** el subconjunto de **Nueva York** (sin el prefijo `JC-`) pesa
  cientos de MB por mes y algunos meses vienen partidos en varios archivos dentro
  del ZIP. Usa el de Jersey City, que es el `JC-`. Y el nombre del archivo ha
  cambiado de convención varias veces a lo largo de los años: verifica el índice.

## 4. Beijing Multi-Site Air Quality — UCI 501

- **URL:** <https://archive.ics.uci.edu/static/public/501/beijing+multi+site+air+quality+data.zip>
  (verificado, 8.2 MB)
- **Ficha:** <https://archive.ics.uci.edu/dataset/501>
- **Contenido verificado:** un ZIP que contiene otro ZIP con **12 archivos CSV**,
  uno por estación de monitoreo, de 35 064 filas × 18 columnas cada uno
  (420 768 filas en total). Horario, de 2013-03-01 a 2017-02-28.
- **Problema:** regresión de PM2.5 a partir de meteorología y contaminantes; o
  clasificación de "día con calidad de aire mala" con un umbral que tú justificas
  contra el estándar de la OMS. La métrica de negocio es fácil de articular: una
  alerta anticipada tiene un costo (falsa alarma) y un beneficio (exposición
  evitada).
- **Referencia vs producción:** dos opciones, y las dos enseñan algo distinto.
  Temporal: 2013-2015 como referencia contra 2016-2017 (Beijing aplicó medidas de
  control de emisiones en ese período, así que el `drift` tiene una causa
  identificable). Espacial: entrenar en unas estaciones y servir en otras.
- **Features:** categóricas `station` (12 valores) y `wd` (dirección del viento, 16
  valores) + derivadas de calendario; numéricas: `PM2.5`, `PM10`, `SO2`, `NO2`,
  `CO`, `O3`, `TEMP`, `PRES`, `DEWP`, `RAIN`, `WSPM`.
- **Nulos reales (verificado, estación Aotizhongxin):** `CO` 1 776, `O3` 1 719,
  `NO2` 1 023, `SO2` 935, `PM2.5` 925, `PM10` 718, `wd` 81, meteorología ~20.
- **Licencia:** CC BY 4.0 (política estándar de UCI; confirma en la ficha del
  dataset).
- **Trampas conocidas:** (a) la ficha de UCI declara `has_missing_values: no`, y
  **es falso** — los CSV traen `NA` en todas las columnas de contaminantes. No
  confíes en ese campo del metadata de UCI en ningún dataset. (b) Solo hay 2
  categóricas nativas; para llegar a las 3 que pide el requisito tendrás que derivar
  al menos una (estación del año, franja horaria, dirección de viento agrupada) y
  **decirlo** en la `dataset card`. (c) El ZIP anidado sorprende a la mitad de la
  gente: hay que descomprimir dos veces.

## 5. Online Retail II — UCI 502

- **URL:** <https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip>
  (verificado, 45.6 MB)
- **Ficha:** <https://archive.ics.uci.edu/dataset/502>
- **Contenido verificado:** un único `online_retail_II.xlsx` con **dos hojas**:
  `Year 2009-2010` (525 461 × 8) y `Year 2010-2011` (541 910 × 8).
  Columnas: `Invoice`, `StockCode`, `Description`, `Quantity`, `InvoiceDate`,
  `Price`, `Customer ID`, `Country`.
- **Problema:** regresión del importe de la línea; clasificación de devolución;
  predicción de demanda por producto y semana. La métrica de negocio es directa:
  dinero.
- **Referencia vs producción:** las dos hojas ya son las dos particiones, y son
  temporalmente contiguas (2009-12→2010-12 y 2010-12→2011-12). Es el dataset de la
  lista donde el `split` referencia/producción es más natural.
- **Features:** categóricas `Country` (40 y 38 valores), `StockCode` (4 632 y 4 070),
  `Description`, `Customer ID`; numéricas `Quantity`, `Price` + derivadas de
  calendario.
- **Nulos reales (verificado):** `Customer ID` 107 927 y 135 080 (≈20-25 % — son
  ventas sin cliente identificado, un nulo **estructural** que hay que tratar como
  categoría, no imputar); `Description` 2 928 y 1 454.
- **Licencia:** CC BY 4.0 (política estándar de UCI).
- **Trampas conocidas:** (a) es **Excel, no CSV**: necesitas `openpyxl` declarado
  como dependencia, y leerlo tarda ~30 s, así que conviene cachearlo a Parquet una
  vez. (b) Hay **12 326 y 10 624 filas con `Quantity` negativa**: son devoluciones,
  no errores. Filtrarlas sin pensar elimina la mitad del problema interesante;
  dejarlas sin distinguir contamina el target. Decide y documenta. (c) `StockCode`
  tiene códigos que no son productos (`POST`, `M`, `BANK CHARGES`, `D`). (d) Las
  dos hojas se **solapan en diciembre de 2010**: si concatenas sin cuidado, duplicas
  transacciones.

## 6. Metro Interstate Traffic Volume — UCI 492

- **URL:** <https://archive.ics.uci.edu/static/public/492/metro+interstate+traffic+volume.zip>
  (verificado, 406 KB)
- **Ficha:** <https://archive.ics.uci.edu/dataset/492>
- **Contenido verificado:** 48 204 × 9, horario, de 2012-10-02 09:00 a
  2018-09-30 23:00. Columnas: `holiday`, `temp`, `rain_1h`, `snow_1h`,
  `clouds_all`, `weather_main`, `weather_description`, `date_time`,
  `traffic_volume`.
- **Problema:** regresión del volumen de tráfico por hora. Métrica de negocio:
  decisiones de señalización y de personal de mantenimiento.
- **Referencia vs producción:** 2012-2015 contra 2016-2018. Seis años de eje
  temporal continuo dan mucho margen para elegir el corte.
- **Features:** 3 categóricas (`holiday` 11 valores, `weather_main` 11,
  `weather_description` 38); 4 numéricas (`temp`, `rain_1h`, `snow_1h`,
  `clouds_all`) + derivadas de calendario.
- **Nulos reales (verificado):** `holiday` tiene 48 143 de 48 204 nulos.
- **Licencia:** CC BY 4.0 (política estándar de UCI).
- **Trampas conocidas, y son buenas para aprender:** (a) el 99.9 % de nulos en
  `holiday` **no es un fallo**: el campo solo está marcado en la primera hora del
  día festivo. Rellenarlo correctamente (propagar el festivo a las 24 horas del día)
  es un ejercicio de `feature engineering` con impacto medible; imputar
  "desconocido" desperdicia la señal. (b) Hay valores centinela: `temp = 0` en Kelvin
  y `rain_1h = 9831.3` mm. Ninguno es físicamente posible y ninguno es nulo, así que
  solo el contrato con rangos de negocio los atrapa. (c) **7 629 timestamps
  duplicados**: si haces un `merge` o un `resample` sin resolverlos, el resultado es
  silenciosamente incorrecto. (d) Es el dataset más pequeño de la lista: cómodo, pero
  no vas a poder presumir de escala.

## 7. Chicago Taxi Trips — portal de datos de Chicago (Socrata)

- **URL de la API:** `https://data.cityofchicago.org/resource/ajtu-isnz.csv?$limit=...`
  (verificado: devuelve CSV con datos hasta agosto de 2026)
- **Portal:** <https://data.cityofchicago.org/Transportation/Taxi-Trips/ajtu-isnz>
- **Problema:** regresión de duración (`trip_seconds`), tarifa (`fare`) o propina
  (`tips`). La propina es especialmente interesante como problema de negocio.
- **Eje temporal:** `trip_start_timestamp`, de 2013 a hoy.
- **Referencia vs producción:** cualquier par de meses. El corte pre/post 2020 es un
  caso de `concept drift` masivo y documentado.
- **Features:** categóricas `payment_type`, `company`, `pickup_community_area`,
  `dropoff_community_area`; numéricas `trip_seconds`, `trip_miles`, `fare`, `tips`,
  `tolls`, `extras`, `trip_total`, coordenadas.
- **Nulos reales (verificado):** `pickup_census_tract` y `dropoff_census_tract`
  vienen vacíos en buena parte de los registros; las áreas comunitarias también
  faltan en algunos.
- **Licencia:** términos de uso del portal de datos abiertos de la ciudad de
  Chicago; uso libre con atribución.
- **Trampas conocidas:** (a) es una **API con paginación**, no un archivo. Sin
  `$limit` y `$offset` bajas 1 000 filas y crees que el dataset es diminuto. Escribe
  la descarga con paginación y **cachéala a Parquet**, o cada ejecución del pipeline
  vuelve a golpear la API. (b) Los timestamps están **redondeados a 15 minutos**, así
  que la duración calculada como diferencia tiene una granularidad grosera: usa
  `trip_seconds`, que sí es fino. (c) Hay viajes con `trip_seconds = 0` y
  `trip_miles = 0` que cobran tarifa: son cancelaciones o errores, y hay que
  filtrarlos con una regla del contrato. (d) Un mes completo son cientos de miles de
  filas: usa `$where` sobre `trip_start_timestamp` para acotar y mantener el
  proyecto bajo 500 MB.

## 8. UK Road Safety — STATS19 (Department for Transport)

- **URL:** `https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-YYYY.csv`
  (verificado: `2023`, 19.8 MB; `2022`, 20.1 MB). Hay archivos hermanos
  `-casualty-YYYY.csv` (10.7 MB, verificado) y `-vehicle-YYYY.csv` para unir.
- **Portal:** <https://www.data.gov.uk/dataset/cb7ae6f0-4be6-4935-9277-47e5ce24a11f/road-safety-data>
  (verificado, 200)
- **Contenido verificado (2023):** 104 258 × 44.
- **Problema:** clasificación de la severidad de la colisión
  (`collision_severity`). Es el dataset de la lista con la métrica de negocio más
  fácil de defender —y con las consideraciones éticas más ricas para
  `docs/riesgos.md`.
- **Eje temporal:** `date` (dd/mm/yyyy) + `time`. Un archivo por año, lo que hace
  trivial la partición referencia vs producción (2022 contra 2023, por ejemplo).
- **Features:** decenas de categóricas (`police_force`, `road_type`,
  `light_conditions`, `weather_conditions`, `road_surface_conditions`,
  `junction_detail`, `urban_or_rural_area`…) y numéricas (`number_of_vehicles`,
  `number_of_casualties`, `speed_limit`, coordenadas).
- **Nulos reales (verificado):** solo 12 nulos "de verdad" (coordenadas) — pero ver
  la trampa.
- **Licencia:** [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
  Uso educativo y comercial permitido con atribución.
- **Trampas conocidas:** (a) **los nulos vienen codificados como `-1`** (y a veces
  `99`), no como celdas vacías. **16 de las 44 columnas contienen `-1`.** Si no los
  conviertes a `NaN`, el modelo aprende que `-1` es una categoría real y las
  numéricas quedan con una media absurda. Este es el ejemplo perfecto de por qué el
  contrato de datos necesita rangos de negocio y no solo tipos. (b) Hay que leer las
  **guías de códigos** del DfT para saber qué significa cada valor entero; sin ellas
  el EDA es adivinanza. (c) `collision_severity` está muy desbalanceado (las
  fatales son ~1 %): trabaja con la matriz de costos, no con `accuracy`. (d) Es un
  dataset sobre lesiones y muertes de personas: la `dataset card` y `riesgos.md`
  tienen que tomarse en serio la parte ética.

## 9. NYC TLC Green Taxi

- **URL:** `https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_YYYY-MM.parquet`
  (verificado: `2023-01` responde 206 a un `range request`; `2024-01`, 1.36 MB
  completo)
- **Portal:** <https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page>
  (el portal devolvió 403 a la verificación automatizada — es protección
  anti-bot, se abre bien en un navegador; el CDN de los archivos sí responde)
- **Problema:** regresión de la duración del viaje.
- **Eje temporal:** `lpep_pickup_datetime`. Un Parquet por mes desde 2009.
- **Referencia vs producción:** 2023-01/02/03 como referencia, 2023-07 y 2024-01
  como producción. Es exactamente la partición que usa el caso guía del curso.
- **Licencia:** datos públicos de la NYC TLC, uso libre con atribución.
- **Trampa principal, y es la razón por la que está en el puesto 9:** **es el caso
  guía del curso.** El repositorio ya lo resuelve de punta a punta, así que copiar es
  trivial y aprender es cero. La rúbrica evalúa tu sistema, no tu capacidad de
  reproducir el nuestro. Úsalo solo si tienes una razón concreta (por ejemplo, atacar
  un problema distinto sobre los mismos datos), y dilo en el README del proyecto.
- **Otras trampas:** el esquema cambió en 2015 y en 2022 (`ehail_fee` quedó todo
  nulo, aparecieron columnas de congestión); las columnas de `yellow` y `green` se
  llaman distinto (`tpep_` vs `lpep_`); hay viajes con `trip_distance = 0` y
  duraciones de 8 horas que son errores de captura, no viajes.

## 10. Inside Airbnb

- **URL:** se obtienen del índice, **no son estables**:
  <https://insideairbnb.com/get-the-data/> (verificado: el índice lista URLs del
  tipo `https://data.insideairbnb.com/<pais>/<region>/<ciudad>/<YYYY-MM-DD>/data/listings.csv.gz`;
  se descargó `.../north-holland/amsterdam/2026-06-15/data/listings.csv.gz`, 5.8 MB)
- **Problema:** regresión del precio por noche. Métrica de negocio evidente para
  un anfitrión o una plataforma.
- **Eje temporal:** cada snapshot tiene una fecha (`last_scraped`). El eje temporal
  es **entre snapshots**, no dentro de uno.
- **Referencia vs producción:** dos snapshots de la misma ciudad separados por
  varios meses, o dos ciudades comparables. El `drift` de precios entre temporada
  alta y baja es real y grande.
- **Features:** decenas de categóricas (`room_type`, `neighbourhood_cleansed`,
  `property_type`, `host_response_time`…) y numéricas (`accommodates`, `bedrooms`,
  `bathrooms`, `minimum_nights`, `number_of_reviews`, `review_scores_*`).
- **Nulos:** abundantes y variados, especialmente en los `review_scores_*` de
  alojamientos nuevos — un nulo estructural muy claro y buen material para la
  discusión de imputación.
- **Licencia:** CC BY 4.0 según las
  [políticas de datos del proyecto](https://insideairbnb.com/data-policies/)
  (verificado, 200).
- **Trampa principal:** **las URLs caducan.** Inside Airbnb conserva solo los
  snapshots recientes (aproximadamente el último año) y borra los anteriores. Si
  eliges este dataset, **descarga los dos snapshots el primer día, guarda su hash en
  `metadata.json` y súbelos a un almacenamiento propio**, o quien te haga `peer
  review` en diez semanas se encontrará con un 403. Es, dicho de otro modo, el mejor
  dataset de la lista para aprender por qué la verificación por hash existe.
- **Otras trampas:** `price` viene como string con símbolo de moneda y separador de
  miles (`"$1,234.00"`); hay ciudades con menos de 1 000 alojamientos, donde el
  modelo no tiene con qué aprender.

---

## Verificados, pero **no** recomendados

Estos descargan bien (200 comprobado el 19 de agosto de 2026) y aparecen mucho en
tutoriales, pero **incumplen un requisito duro**. Se listan con el motivo para que no
pierdas tiempo evaluándolos.

| Dataset | URL verificada | Requisito que incumple |
|---|---|---|
| Seoul Bike Sharing Demand (UCI 560) | 200, 604 KB | Sin nulos reales, y solo 3 categóricas de baja cardinalidad (`Seasons`, `Holiday`, `Functioning Day`). El contrato de datos queda trivial |
| Bike Sharing Dataset (UCI 275) | 200, 280 KB | 17 389 filas, sin nulos, ya agregado por hora. No hay nada que limpiar |
| Individual Household Electric Power Consumption (UCI 235) | 200, 20.6 MB | **Cero** features categóricas. Excelente para series de tiempo, inservible para el contrato de datos que pide el curso |
| ElectricityLoadDiagrams 2011-2014 (UCI 321) | 200, 261 MB | Formato ancho: 370 clientes como **columnas**, no como filas. Sin categóricas. Convertirlo a formato largo es trabajo que no enseña nada del curso |
| Steel Industry Energy Consumption (UCI 851) | 200, 482 KB | Sin nulos; pocas categóricas |

Un patrón que conviene notar: **casi todos los datasets "limpios" de UCI fallan el
requisito de nulos reales.** Están curados para enseñar algoritmos, no para enseñar
ingeniería de datos. Los datos municipales y de operación (bicicletas, taxis,
siniestralidad, alojamiento) son sucios porque provienen de sistemas reales, y ese
es precisamente su valor para este curso.

## Si traes otro dataset

Antes de comprometerte, comprueba las seis cosas. Toma diez minutos y ahorra
semanas:

```bash
# 1. Descarga sin autenticación y tamaño
curl -s -o /dev/null -w 'HTTP %{http_code} · %{size_download} bytes\n' -L <url>
```

```python
# 2-6. Esquema, eje temporal, nulos y particiones
import pandas as pd

df = pd.read_csv("<archivo>")  # o read_parquet
print(df.shape)
print(df.dtypes)  # ¿≥3 categóricas y ≥3 numéricas?
print(df.isna().sum()[lambda s: s > 0])  # ¿nulos reales?
print(df["<col_fecha>"].min(), df["<col_fecha>"].max())  # ¿eje temporal?
```

Y las dos que no se comprueban con código:

- ¿puedes escribir en una frase quién tomaría una decisión distinta por tener esta
  predicción? Si no, no hay métrica de negocio.
- ¿la licencia está publicada, con nombre y URL? "Estaba en internet" no es una
  licencia.

Documenta las respuestas en `docs/dataset-card.md` de tu proyecto. La plantilla de
[`starter-template/docs/dataset-card.md`](starter-template/docs/dataset-card.md) ya
trae la tabla de requisitos para llenar.
