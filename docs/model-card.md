# Model Card — nyc-taxi-duration

<!-- ARCHIVO GENERADO. No lo edites a mano: `taxi model-card` lo sobrescribe.
     Si necesitas cambiar el texto, edita scripts/model_card.py. -->

_Generada automáticamente el 2026-08-25 16:13 UTC por `scripts/model_card.py`._

## 1. Identificación y versión

| campo | valor |
|---|---|
| Nombre registrado | `nyc-taxi-duration` |
| Versión | **1** |
| Alias | `@champion` |
| URI de referencia | `models:/nyc-taxi-duration@champion` |
| Run de MLflow | `aee553ef5b634abfb6b7390bd74a03e4` |
| Registrada el | 2026-08-25 16:13 UTC |
| `validation_status` | passed |

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
  1 min o mayores a 60 min
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

| rol | partición | archivo | SHA-256 (16 primeros) |
|---|---|---|---|
| Entrenamiento | 2023-01 | `green_tripdata_2023-01.parquet` | `9f0e03dd7f8f94ec...` |
| Entrenamiento | 2023-02 | `green_tripdata_2023-02.parquet` | `bcc2821d639197cb...` |
| Entrenamiento | 2023-03 | `green_tripdata_2023-03.parquet` | `69ab2c3b515ad1dd...` |
| Validación (selección de hiperparámetros) | 2023-04 | `green_tripdata_2023-04.parquet` | `d28bf0485ac095e9...` |
| Holdout (juez del gate de promoción) | 2023-05 | `green_tripdata_2023-05.parquet` | `8545a8510b2f33e4...` |
| Producción simulada (monitoreo) | 2023-07 | `green_tripdata_2023-07.parquet` | `a5063fa42a5d40aa...` |
| Producción simulada (monitoreo) | 2024-01 | `green_tripdata_2024-01.parquet` | `1512a953bed564ac...` |

<details><summary>SHA-256 completos</summary>

- `green_tripdata_2023-01.parquet`: `9f0e03dd7f8f94ecc15949cdbfd2a4e1fc9ebb41a11882215158c9fc95012e31`
- `green_tripdata_2023-02.parquet`: `bcc2821d639197cbb09aeb8994121a7004f2a6568a64bf4839015db802f62743`
- `green_tripdata_2023-03.parquet`: `69ab2c3b515ad1dd686a8ac3375370b8a44b003d95d340655d94828db0681d9d`
- `green_tripdata_2023-04.parquet`: `d28bf0485ac095e923c736180cf1b4fb247fdbcee1ae6d77eb78e7a185b7aacf`
- `green_tripdata_2023-05.parquet`: `8545a8510b2f33e4bec7a2e12f9ff1f83752bb6a976dfbbc347b4fb7ae28eb2d`
- `green_tripdata_2023-07.parquet`: `a5063fa42a5d40aaa965d26033568d75cec3771069203bc286536df36e83d26f`
- `green_tripdata_2024-01.parquet`: `1512a953bed564ac68dcb622827424dfb4f68ad93c2a4572e50ef6ab0b09c1ad`

</details>

Muestreo determinista de 60 000 filas por partición con
semilla `42`. La división es **temporal**, no aleatoria: se entrena
con meses anteriores y se evalúa con meses posteriores, porque en producción el
modelo siempre predice sobre el futuro. Un split aleatorio sobre datos temporales
mezcla meses y produce métricas optimistas que no se sostienen.

## 5. Contrato de features

| grupo | columnas |
|---|---|
| crudas_requeridas | `lpep_pickup_datetime`, `lpep_dropoff_datetime`, `PULocationID`, `DOLocationID`, `trip_distance` |
| features_categoricas | `PU_DO`, `PULocationID`, `DOLocationID` |
| features_numericas | `trip_distance`, `hora_pickup`, `dia_semana_pickup` |
| targets | `duration`, `viaje_largo` |

Notas que evitan errores concretos:

- `trip_distance` está en **millas**, no en kilómetros. El contrato de datos
  rechaza el rango de kilómetros; es el fallo silencioso más probable de esta
  integración.
- `PULocationID` y `DOLocationID` son identificadores (1-265), no cantidades: se
  tratan como categorías.
- `PU_DO`, `hora_pickup` y `dia_semana_pickup` son **derivadas** por el pipeline.
  El consumidor envía las columnas crudas; la derivación va dentro del artefacto.

Target: `nyc-taxi-duration` predice `duration` en minutos. El target
binario `viaje_largo` (duración > 30 min) es un
segundo problema derivado del mismo dato, registrado como
`nyc-taxi-long-trip`.

## 6. Métricas

Leídas del run de MLflow que produjo esta versión. El prefijo indica sobre qué
partición se midió cada una:

- `train_*` → particiones de entrenamiento (2023-01, 2023-02, 2023-03)
- `valid_*` → 2023-04, la partición con la que se seleccionaron los hiperparámetros
- `holdout_*` → 2023-05, el holdout fijo. **Aparecen sólo si alguien lo evaluó
  explícitamente** (`taxi train --holdout` o el gate de promoción). Su ausencia no
  es un error: el holdout se mira lo menos posible, y cada consulta se registra.
- `mejor_iteracion` → ronda de boosting en la que actuó el early stopping; es la
  evidencia de que el early stopping opera de verdad.

#### Globales
| métrica | valor |
|---|---|
| `mejor_iteracion` | 498.0000 |
| `train_mae` | 2.5543 |
| `train_r2` | 0.8143 |
| `train_rmse` | 4.0115 |
| `valid_mae` | 2.8795 |
| `valid_r2` | 0.7669 |
| `valid_rmse` | 4.6516 |

#### Por subgrupo

Un RMSE global mejor puede esconder una degradación en un segmento minoritario. El gate de promoción compara estos valores entre candidato y champion y rechaza el candidato si alguno se degrada más de 5%. Los subgrupos con menos de 50 observaciones no se usan para decidir porque su error está dominado por el ruido de muestreo.

| subgrupo | RMSE |
|---|---|
| `rmse_dist_corta` | 5.5567 |
| `rmse_dist_larga` | 5.8912 |
| `rmse_dist_media` | 2.9775 |
| `rmse_dist_muy_larga` | 8.1741 |
| `rmse_hora_madrugada` | 4.6452 |
| `rmse_hora_manana` | 4.8451 |
| `rmse_hora_noche` | 4.0294 |
| `rmse_hora_tarde` | 4.9063 |

Definición de los subgrupos:

- Franjas horarias: `madrugada` (0-5 h), `manana` (6-11 h), `tarde` (12-17 h), `noche` (18-23 h)
- Rangos de distancia: `corta` ([0.0, 1.0) millas), `media` ([1.0, 3.0) millas), `larga` ([3.0, 10.0) millas), `muy_larga` ([10.0, inf) millas)

### Criterio de promoción

Un candidato reemplaza al `@champion` sólo si supera los tres
criterios del gate (`scripts/promote.py`):

1. El holdout cumple el contrato de datos de Pandera.
2. `RMSE_candidato <= RMSE_champion * (1 - 0.01)`.
   Se exige un margen y no un simple "menor que" para evitar que dos modelos
   equivalentes roten indefinidamente en producción por ruido de muestreo.
3. Ningún subgrupo se degrada más de
   5%.

## 7. Limitaciones conocidas

- **Rutas no vistas.** `PU_DO` tiene miles de valores posibles y en producción
  aparecen pares que no estaban en entrenamiento. `DictVectorizer` los ignora
  silenciosamente: la predicción se apoya sólo en distancia y hora, y su error
  es mayor. No hay señal de esto en la respuesta del modelo.
- **Distancia declarada, no recorrida.** `trip_distance` viene del taxímetro al
  cierre del viaje. Si el consumidor la estima al inicio (por ejemplo, con
  distancia en línea recta), la entrada no es la misma que el modelo vio.
- **Truncamiento del target.** Se entrenó sólo con viajes de
  1 a 60 minutos. El
  modelo no puede predecir fuera de ese rango y subestima sistemáticamente los
  viajes largos reales.
- **Sin información de tráfico ni clima.** El error crece en condiciones
  atípicas, que es precisamente cuando un ETA importa más.
- **Deriva temporal.** Entrenado con datos de 2023. Cambios de tarifa, de
  patrones de movilidad o de la definición de zonas degradan el desempeño con el
  tiempo. Es el problema que se monitorea en la sesión de drift.
- **Métricas por subgrupo con poca muestra.** Los subgrupos de menos de
  50 observaciones se reportan pero no se usan para
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
Por que aliases + tags y no stages:

1. Los stages (None/Staging/Production/Archived) estan deprecados desde
   MLflow 2.9.0. El metodo del cliente que los cambiaba todavia existe, pero
   la documentacion oficial anuncia su eliminacion en una version mayor.
2. Los stages eran un vocabulario cerrado de cuatro palabras. Un equipo real
   necesita mas: champion, challenger, shadow, canary, champion-eu. Los
   aliases son nombres libres, uno por rol de servicio.
3. Un stage mezclaba dos cosas distintas: 'que version sirve' (routing) y
   'en que estado de validacion esta' (metadato). Aliases y tags las separan:
   el alias @champion enruta, el tag validation_status=passed documenta.
4. Solo una version puede tener un alias dado, y eso es una garantia util:
   con stages, dos versiones podian quedar en Production a la vez y nadie
   sabia cual respondia.
5. El rollback se vuelve trivial: mover @champion a la version anterior es
   una escritura de metadatos, no un redeploy. La version anterior sigue en
   el registry porque las versiones son inmutables.

En codigo:
    client.set_registered_model_alias('nyc-taxi-duration', 'champion', '7')
    client.set_model_version_tag('nyc-taxi-duration', '7', 'validation_status', 'passed')
    modelo = mlflow.pyfunc.load_model('models:/nyc-taxi-duration@champion')
```

Detalle completo en `docs/adr/002-aliases-en-vez-de-stages.md`.
