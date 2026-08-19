# ADR 003 — Umbrales de drift: tamaño de efecto calibrado, no p-valor

- **Estado:** aceptada
- **Fecha:** 2026-08
- **Alcance:** sesión 7, `src/taxi/monitoring/`, `src/taxi/config.py` (`UMBRAL_DRIFT_COLUMNAS`), CI de monitoreo
- **Decisores:** equipo docente del curso de MLOps

## Contexto

El módulo de monitoreo anterior decidía drift con una línea:

```python
stat, p_value = stats.ks_2samp(train[col], prod[col])
drift = p_value < 0.05
```

Ese criterio tiene tres problemas, en orden de gravedad.

**1. No escala con el tamaño de muestra.** El p-valor de un test de dos muestras
responde "¿es plausible que provengan de la misma distribución?", y su poder crece
con `n`. El valor crítico del KS al 5% es aproximadamente `1.36 * sqrt(2/n)`:

| n por muestra | `D` crítico al 5% |
|---|---|
| 1.000 | 0.061 |
| 60.000 | 0.008 |
| 500.000 | 0.003 |

Con las particiones del caso guía (60.000 filas muestreadas por mes; las particiones
completas de la TLC tienen cientos de miles) cualquier diferencia trivial es
"significativa". Verificado empíricamente sobre los datos reales del curso
(2023-01..03 como referencia, 2023-07 como actual, agosto de 2026):

| Criterio | Columnas con drift de 7 |
|---|---|
| `p_valor` (`p < 0.05`) | **7 / 7** |
| `efecto` (significancia **y** magnitud) | 2 / 7 |
| `psi` (`PSI >= 0.25`) | 1 / 7 |

Un detector que marca todas las columnas todos los meses no informa: produce **alert
fatigue**, el equipo aprende a ignorar la alerta y el día del drift real nadie mira.

**2. Confunde "cambió" con "cambió lo suficiente".** La pregunta operativa no es si
hay diferencia, sino si la diferencia importa para el modelo y para el negocio. Eso lo
responde un **tamaño de efecto**, no un p-valor.

**3. No dejaba rastro de por qué.** Un `True` no permite decidir entre reentrenar,
arreglar el pipeline o ajustar el umbral.

## Decisión

### 1. El veredicto por columna exige significancia **y** magnitud

```python
drift = (p_valor < ALFA) and (tamano_efecto >= umbral_de_esa_columna)
```

Y se guarda el motivo en texto. Los dos casos mixtos son informativos y se reportan
como "sin drift" con explicación:

| Significativo | Relevante | Lectura |
|---|---|---|
| sí | no | diferencia detectable por el tamaño de muestra, no por su magnitud |
| no | sí | efecto grande sin evidencia suficiente: recolectar más datos |

Tamaño de efecto por tipo de columna:

- **numéricas:** el estadístico `D` del KS, que ya es un tamaño de efecto (sup-norma
  entre las CDF empíricas, acotado en `[0,1]`, independiente de `n`);
- **categóricas:** la **V de Cramér**, porque el estadístico chi-cuadrado crece
  linealmente con `n` y no es comparable entre corridas.

Además se reportan PSI y distancia de Jensen-Shannon por columna, para vigilancia
temporal. No deciden por defecto: el PSI no está acotado y con categorías nuevas se
dispara (se han medido PSI de 14 en el caso guía), lo que lo hace buena señal y mala
escala.

### 2. Los umbrales son por feature y se **calibran contra el ruido del instrumento**

El paso obligatorio antes de fijar un umbral es medir el tamaño de efecto entre **dos
mitades aleatorias de la propia referencia**, donde por construcción no hay drift
(`estadistico.linea_base_nula`). Ese número es el ruido del estimador con ese `n` y
esa cardinalidad. **Un umbral por debajo de él garantiza falsos positivos.**

Medición sobre las particiones del curso (referencia 2023-01..03, 180.000 filas,
`SEMILLA=42`, agosto de 2026):

| Feature | Ruido bajo el nulo | Umbral fijado | Señal vs 2023-07 | Señal vs 2024-01 |
|---|---|---|---|---|
| `trip_distance` | 0.004 | 0.07 | 0.042 | 0.024 |
| `hora_pickup` | 0.006 | 0.15 | 0.021 | 0.009 |
| `dia_semana_pickup` | 0.003 | 0.15 | 0.057 | 0.054 |
| `duration` (target) | 0.005 | 0.10 | 0.023 | 0.013 |
| `PULocationID` | 0.035 | 0.10 | 0.134 | 0.089 |
| `DOLocationID` | 0.035 | 0.10 | 0.075 | 0.068 |
| `PU_DO` | **0.119** | **0.15** | 0.187 | 0.160 |

La fila de `PU_DO` es la que justifica esta sección del ADR. El par origen-destino
tiene miles de niveles, y la V de Cramér tiene **sesgo positivo** cuando hay muchas
celdas con conteos bajos: marca ~0.12 sobre datos donde no pasa nada. El default
razonable para una categórica (0.10) queda **por debajo** de ese ruido, así que con él
el detector alertaría comparando dos mitades del mismo mes. Se subió a 0.15: por
encima del ruido y por debajo de la señal observada.

El resto de umbrales incorpora además una decisión de negocio: `trip_distance` entra
directo en la predicción, así que se vigila fino (0.07); `hora_pickup` y
`dia_semana_pickup` tienen variación estacional esperada **y ya son features del
modelo**, así que se toleran cambios mayores (0.15).

### 3. La alerta de dataset es una fracción de columnas, no "alguna columna"

`UMBRAL_DRIFT_COLUMNAS = 0.30` en `config.py`. Se alerta cuando más del 30% de las
columnas evaluadas tiene drift. Una columna moviéndose es ruido normal de cualquier
sistema; un tercio de las columnas moviéndose a la vez casi siempre indica un cambio
upstream (esquema, unidad, proveedor de datos), que es un problema distinto y más
grave que el drift.

### 4. El resultado se materializa como exit code

`0` sin alerta · `1` umbral superado · `2` no evaluable. El `2` existe porque "no pude
medir" no es "todo bien". Sin exit code, el monitoreo es un informe; con exit code, es
un paso de pipeline que abre una alerta.

## Consecuencias

**Positivas**

- La tasa de falsas alarmas es medible y está medida: 0 columnas sobre el nulo, con
  cualquiera de los tres criterios.
- Cada umbral tiene procedencia: un número medido y una razón de negocio escrita.
- El criterio malo sigue disponible (`--criterio p_valor`) y se usa **para demostrar
  que está mal** con el mismo dataset. La comparación 7/7 vs 2/7 es la clase.
- El registro del motivo por columna convierte la salida en algo que se puede revisar
  en un PR.

**Negativas y riesgos aceptados**

- **Los umbrales son específicos de este dataset y de este `n`.** No son
  transferibles. El proyecto de cada estudiante tiene que recalibrar con
  `linea_base_nula` sobre sus propios datos; el taller lo exige.
- **Un umbral alto reduce la sensibilidad.** Con `PU_DO` en 0.15 se pierde capacidad de
  detectar cambios de mezcla de rutas moderados. El precio es explícito y se compensa
  con la señal de categorías nuevas, que se reporta aparte del test.
- **El submuestreo a `MAX_FILAS = 200.000`** hace que el p-valor dependa de una
  decisión de implementación. Es coherente con el argumento del ADR (si hay que
  submuestrear para que el p-valor sea interpretable, el p-valor no era el criterio),
  pero hay que decirlo en clase en lugar de esconderlo.
- **Calibrar contra el nulo tiene un supuesto:** que las dos mitades aleatorias de la
  referencia sean intercambiables. Con datos con fuerte autocorrelación temporal, un
  split aleatorio subestima el ruido y habría que usar un split por bloques temporales.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Solo p-valor con alfa más estricto (1e-6) | mueve el problema sin resolverlo: el alfa necesario depende de `n`, así que el umbral cambia cada vez que cambia el volumen del lote |
| Solo PSI con los cortes clásicos (0.1 / 0.25) | el PSI no está acotado y con categorías nuevas se dispara; sigue disponible como `--criterio psi` y como métrica reportada |
| Bonferroni / control de FDR sobre las 7 columnas | corrige la multiplicidad, no el problema de fondo: con `n` grande los p-valores corregidos siguen siendo minúsculos |
| Delegar el umbral a `DataDriftPreset(drift_share=...)` de Evidently | acopla la política del curso a los defaults de una librería y deja el plan B sin criterio propio |
| Umbral único global para todas las features | ignora que el ruido del estimador varía en dos órdenes de magnitud entre `trip_distance` (0.004) y `PU_DO` (0.119) |
| Estimar performance sin etiquetas (NannyML CBPE/DLE) | es la respuesta correcta al problema real, pero añade una dependencia y un marco conceptual que no cabe en una sesión de 4 h; se menciona en el README como complemento |

## Verificación

```bash
uv run python -m taxi.monitoring.check_drift --sin-evidently --verbose
uv run python -m taxi.monitoring.check_drift --sin-evidently --criterio p_valor
uv run pytest tests/unit/test_monitoring.py -q
```

Los tests que fijan esta decisión:

- `test_p_valor_solo_es_criterio_malo_con_n_grande` — con n = 60.000 y una diferencia
  de 0,05 sigma, el criterio por p-valor declara drift y el criterio por efecto no. Si
  alguien "simplifica" el código volviendo a `p < 0.05`, este test falla y explica por
  qué.
- `test_control_negativo_sin_drift_en_ninguna_columna` — cero falsos positivos sobre
  dos muestras de la misma distribución.
- `test_fraccion_de_columnas_con_drift` — el umbral de dataset, incluido el borde.
