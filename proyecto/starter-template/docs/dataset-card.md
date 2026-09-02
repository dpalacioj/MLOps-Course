# Dataset card

> Documenta el dato con el mismo rigor con el que se documenta el modelo. No es
> burocracia: es lo que permite que otra persona (tu revisor, tú en tres meses,
> un auditor) sepa qué se midió, con qué población y con qué sesgos.
>
> El AI Act exige documentación técnica del dato para sistemas de alto riesgo, y
> aun cuando tu proyecto no lo sea, esta ficha es honestidad intelectual básica.

## Identificación

| Campo | Valor |
|---|---|
| Nombre | TODO(estudiante) 29 |
| Fuente y URL | TODO |
| Licencia (nombre exacto + URL) | TODO |
| Fecha de descarga | TODO |
| Tamaño (filas × columnas, MB) | TODO |
| Hash de las particiones | ver `data/raw/metadata.json` |

## Cumplimiento de los requisitos duros del curso

Contrasta tu dataset contra la tabla de `proyecto/README.md`. Si algún requisito
no se cumple, dilo aquí y explica cómo lo compensas; un requisito incumplido y
declarado es manejable, uno escondido rompe la fase de monitoreo.

| Requisito | ¿Cumple? | Evidencia o justificación |
|---|---|---|
| Eje temporal explícito | TODO | TODO |
| ≥2 particiones separables (referencia vs producción) | TODO | TODO |
| ≤500 MB, descargable sin autenticación | TODO | TODO |
| ≥3 categóricas y ≥3 numéricas con nulos reales | TODO | TODO |
| Métrica de negocio articulable | TODO | TODO |
| Licencia que permite uso educativo | TODO | TODO |

## Esquema y significado de las columnas

| Columna | Tipo | Unidades | Nulos | Significado |
|---|---|---|---|---|
| TODO | TODO | TODO | TODO | TODO |

Las **unidades** no son un detalle. Un cambio silencioso de unidades no lanza
excepciones: solo degrada la métrica.

## Nulos: por qué los hay y qué se hace con ellos

TODO(estudiante) 29: por columna. Distingue el nulo **estructural** (el campo no
aplica a ese registro) del nulo por **fallo de captura**. No se tratan igual, y
`fillna(0)` no es una estrategia por defecto: es una decisión que sesga la media e
inventa ceros que el modelo aprende como reales.

## Particiones

| Partición | Rango temporal | Filas | Uso |
|---|---|---|---|
| TODO | TODO | TODO | entrenamiento |
| TODO | TODO | TODO | validación (selección de hiperparámetros) |
| TODO | TODO | TODO | holdout fijo (juez del gate) |
| TODO | TODO | TODO | producción simulada (monitoreo) |

## Población representada y sesgos conocidos

TODO(estudiante) 29: a quién describe este dato y a quién **no**. Ejemplos de lo
que hay que nombrar: cobertura geográfica parcial, un canal de captura que
subrepresenta a un grupo, un período atípico (pandemia, cambio regulatorio).

## Limitaciones y usos no previstos

TODO(estudiante) 29: para qué **no** sirve este dato, aunque técnicamente se pueda
entrenar un modelo con él.
