# ADR 005 — Contratos de datos ejecutables con Pandera, en tres niveles

- **Estado:** aceptada
- **Fecha:** 2026-08
- **Alcance:** validación de datos de todo el curso (sesiones 2 a 8) y del
  `starter-template` del proyecto
- **Decisores:** equipo docente del curso de MLOps

## Contexto

El repositorio anterior **no validaba datos en ningún punto**. Ni un esquema, ni un
rango, ni un `assert`. Las consecuencias no eran hipotéticas:

1. **El generador de datos sintéticos documentaba kilómetros y alimentaba un modelo
   entrenado en millas.** El `pipeline` entrenaba sin quejarse, registraba un RMSE
   plausible y servía predicciones. Nadie lo detectó porque nada podía detectarlo.
2. **El `target` del módulo de `deployment` era `random.choices([0, 1])`.** Ruido puro
   presentado como problema de ML, con métricas de azar que el estudiante interpretaba
   como resultado de un modelo.
3. **`loaders.py` casteaba `['PU_DO', 'trip_distance']` a `str` sobre el parquet
   crudo**, donde `PU_DO` todavía no existe. Producía
   `KeyError: "['PU_DO'] not in index"` y el `pipeline` estrella del curso no
   arrancaba. Y si se "arreglaba" mal, `trip_distance` quedaba como `str` y el
   `DictVectorizer` la `one-hot-encodeaba` en lugar de tratarla como numérica.

El problema de fondo es una asimetría que el curso tiene que enseñar explícitamente:
**los errores de datos casi nunca lanzan excepciones, degradan métricas.** Un fallo
ruidoso cuesta una tarde de `debugging`; un fallo silencioso cuesta meses de decisiones
tomadas con predicciones malas, más el tiempo de descubrir que el problema estaba en el
dato y no en el modelo.

Y hay una restricción específica del aula que condiciona la decisión: **la validación
tiene que funcionar sobre datos reales de la NYC TLC**, que traen basura individual
medible. En `green_tripdata_2023-01.parquet` hay **37 viajes de más de 100 millas** (uno
de 120.098,84) en **68.211** filas. Un mecanismo de validación que rechace esa partición
bloquea el curso entero.

## Decisión

**Contratos de datos ejecutables con Pandera, versionados junto al código en
`src/taxi/data/contract.py`, validados en la frontera del `pipeline`, y organizados en
tres niveles de check con responsabilidades distintas.**

### 1. Pandera, y `pandera.pandas` como espacio de nombres

```python
import pandera.pandas as pa
from pandera.typing import Series
```

`import pandera as pa` para clases de `pandas` emite `FutureWarning` y será eliminado
(verificado con `pandera 0.32.1`, agosto de 2026). `SchemaModel` ya se eliminó; el
nombre vigente es `DataFrameModel`.

### 2. Dos contratos, no uno

| | `ViajesCrudos` | `ViajesProcesados` |
|---|---|---|
| Valida | el parquet tal como llega del proveedor | el `dataframe` listo para entrenar |
| Rangos | **anchos** | **duros** |
| Si falla, el bug es | del proveedor o de la descarga | **nuestro** |

Los dos con `strict = False`, a propósito: el parquet trae ~20 columnas y solo importan
cinco. Un contrato que exija ausencia de columnas extra se rompe cada vez que la TLC
agrega un campo, **y eso entrena al equipo a ignorarlo**.

### 3. Tres niveles de check, con la cota por fila **ancha a propósito**

| Nivel | Cómo | Qué atrapa | Ejemplo |
|---|---|---|---|
| **1. Por fila** | `pa.Field(ge=, le=, nullable=)` | registros corruptos individuales | `PULocationID` en `1-265` |
| **2. Por distribución** | `@pa.dataframe_check` sobre una **fracción** o un agregado | problemas **sistemáticos** | `outliers_de_distancia_son_marginales`, `volumen_minimo` |
| **3. Entre columnas** | `@pa.dataframe_check` con dos o más columnas | incoherencias invisibles columna a columna | `velocidad_implicita_plausible` |

La parte contraintuitiva, y es el centro de la decisión: **`trip_distance` se acota por
fila en `[0, 1e6)`, no en `[0, 100]`.** La señal de "esto es sistemático" se mueve al
nivel 2, con un umbral **calibrado sobre datos medidos**:

| Cantidad | Valor | Fuente |
|---|---|---|
| Fracción real de viajes > 100 millas | **0,054 %** (37 de 68.211) | medido en `green_tripdata_2023-01.parquet` |
| `MAX_FRACCION_OUTLIERS` | **0,3 %** | decisión, con ~5,5x de margen |

Y el umbral queda **atrapado entre dos aserciones** en
`tests/data/test_niveles_de_check.py`: no puede bajar hasta el ruido real de la TLC ni
subir por encima de `0,01`, donde dejaría de detectar un cambio de unidades.

### 4. El contrato describe; el test verifica

- **Contrato** → afirmación sobre el mundo (*"`PULocationID` está entre 1 y 265"*). Vive
  en `src/`, corre **en producción**, en la frontera.
- **Test** → afirmación sobre nuestro código (*"si llega la zona 999, la validación
  falla"*). Vive en `tests/`, corre en el CI, **nunca** en producción.

Con tres `fixtures` rotos que reproducen fallos reales, la propiedad de que **ninguno
lanza excepción por sí mismo**, y un **control negativo** obligatorio: el contrato debe
aceptar varios lotes independientes de datos buenos.

### 5. El filtro de negocio es una responsabilidad separada, y se contabiliza

El contrato dice **qué es un dato bien formado**; el filtro de
`loaders.preparar_particion` dice **qué es un viaje**. El filtro cuenta cuántas filas
descarta, lo registra, y **avisa si descarta más del 35 %**. Un filtro silencioso es tan
peligroso como no tener filtro.

### 6. Se declara el límite del mecanismo

Un contrato estático sobre un solo lote **no detecta** un cambio de escala moderado. Se
verifica con el propio caso guía: convertir `trip_distance` de millas a km en el parquet
real **pasa el contrato** (fracción > 100: 0,000542 → 0,000557; mediana 1,85 → 2,98;
velocidad implícita 10,63 → 17,10 mph, dentro del rango aceptado). Lo que sí lo detecta
es comparar contra una referencia: `KS` da `D = 0,2513` frente a un ruido de `0,0069`.

**Esta limitación se enseña explícitamente**, y es el puente estructural S02 → S07.

## Alternativas consideradas

**A. Great Expectations Core 1.x.**
Más potente para `data warehouse` y `reporting`: Data Docs, catálogo de `expectations`,
`Checkpoints` con `Actions`. **Descartada como opción por defecto del curso** por peso
de adopción: introduce `Data Context`, `Data Source`, `Data Asset`, `Batch Definition`,
`Expectation Suite`, `Validation Definition` y `Checkpoint` —siete conceptos— para
validar cinco columnas. Y un problema didáctico específico: su API cambió por completo
respecto a 0.18, así que **la mayoría de los tutoriales que el estudiante va a encontrar
no ejecutan**, y depurar eso consume el tiempo de clase que debería ir a los tres
niveles de check. **Sigue siendo la respuesta correcta** cuando el consumidor del
contrato es un analista o un auditor y no un `pipeline`, y el taller la acepta.

**B. Pydantic.**
Descartada **para `DataFrames`**: está diseñada para un registro a la vez, validar
60.000 filas creando 60.000 objetos es lento, y no expresa checks de distribución, que
son justo los que atrapan el incidente de esta sesión. **Sí se usa** para el I/O de la
API en la S05, que es su sitio correcto.

**C. `assert` a mano en el `loader`.**
Ventaja: cero dependencias. Descartada porque el esquema deja de ser **declarativo**:
no se puede documentar, ni reutilizar, ni serializar a la `model card`
(`resumen_contrato()` se llama desde `scripts/model_card.py`), ni integrar con `pytest`
sin duplicarlo.

**D. Un solo nivel de check, con cotas estrictas por fila.**
Es la opción intuitiva, y es la que estaba implementada y **rompía el curso**:
`trip_distance <= 100` por fila fallaba con `SchemaErrors` en la primera partición por 37
filas de 68.211. Descartada por una razón que va más allá de lo técnico: un contrato que
rechaza el lote completo por 0,054 % de basura es un contrato que **el equipo aprende a
desactivar**, y un contrato desactivado protege exactamente cero.

**E. Un solo nivel, con cotas anchas y sin checks de distribución.**
El error opuesto: el contrato pasa siempre y no detecta nada sistemático. Descartada
porque deja fuera el único check que atrapa un cambio de unidades.

**F. Validar solo en los tests, no en el `pipeline`.**
Descartada porque los tests corren sobre `fixtures`, no sobre el dato de producción. Un
contrato que no se ejecuta en la frontera no protege del dato que llegó ayer.

**G. Delegar la validación al monitoreo de `drift` (S07).**
Descartada por la asimetría inversa a la del punto 6: el `drift` necesita **acumular un
lote y tener una referencia**. Mientras espera, el `pipeline` entrena con nulos y con
zonas inexistentes. Contrato y `drift` responden preguntas distintas y se apilan.

**H. Datos sintéticos en lugar de reales, para evitar la basura del proveedor.**
Descartada en el [ADR 001](001-caso-guia-y-particiones.md): los problemas interesantes
—outliers reales, categorías nuevas, re-publicación de archivos— **no existen** en datos
sintéticos, o existen solo porque alguien los inyectó. Los sintéticos se conservan
únicamente en los `fixtures` de test, donde la reproducibilidad sí es el objetivo.

## Consecuencias

**Positivas**

- El fallo silencioso se convierte en fallo ruidoso en la frontera, que es órdenes de
  magnitud más barato de arreglar.
- El contrato pasa sobre las siete particiones reales del caso guía, así que nadie tiene
  motivo para desactivarlo.
- La distinción de tres niveles es transferible: es lo que se le pide al estudiante en su
  propio `dataset`, y el criterio nº 1 del taller de la S02.
- `resumen_contrato()` alimenta la `model card`: el modelo declara contra qué esquema se
  entrenó.
- El `smoke test` del entorno valida el contrato **y comprueba que rechaza un dato
  roto**, así que un contrato degradado se detecta en la S01.
- La limitación declarada (punto 6) construye el puente S02 → S07 con una medición, no
  con una afirmación.

**Negativas, y qué se hace con ellas**

- **Una dependencia más** (`pandera`), en un curso que ya instala 17 paquetes.
  *Mitigación:* es ligera, `in-process` y no requiere servicios. Y el `smoke test` la
  verifica.
- **La cota ancha por fila es contraintuitiva y hay que explicarla cada cohorte.**
  Alguien va a proponer, razonablemente, endurecerla. *Mitigación:* el razonamiento está
  escrito en el `docstring` de la clase **y** en el encabezado de
  `tests/data/test_niveles_de_check.py`, y hay un test que se rompe si se cambia.
- **El umbral de fracción es específico de este `dataset`.** `0,003` no significa nada
  fuera del green taxi. *Mitigación:* el taller **penaliza copiarlo** y exige la tabla de
  calibración con datos propios. Es un riesgo pedagógico real: es lo primero que un
  estudiante copia.
- **Validar cuesta tiempo de `pipeline`.** Sobre 60.000 filas es despreciable; sobre
  millones no. *Mitigación:* `preparar_particion` acepta `validar=False`, documentado como
  *"desactivarlo solo tiene sentido para demostrar en clase qué pasa sin contrato"*. Es un
  interruptor que se puede abusar, y se asume a cambio de poder hacer la demostración.
- **`strict = False` deja pasar columnas que nadie mira.** Si la TLC añade una columna con
  un nombre que colisiona semánticamente, el contrato no dice nada. *Se asume:* el coste
  de `strict = True` —romperse en cada cambio del proveedor— es mayor.
- **El contrato no detecta cambios de escala moderados** (punto 6). *No se mitiga: se
  enseña.* Intentar taparlo con umbrales más agresivos produciría falsos positivos y
  `alert fatigue`, que es el error que el [ADR 003](003-umbrales-de-drift.md) documenta
  para el `drift`.

## Cuándo revisar esta decisión

- Si la TLC republica una partición y las fracciones medidas cambian: re-calibrar
  `MAX_FRACCION_OUTLIERS` y actualizar la cifra en el material y en la
  `dataset card`.
- Si Pandera introduce un cambio incompatible: la superficie usada es pequeña
  (`DataFrameModel`, `Field`, `dataframe_check`, `validate`), pero el `import` de
  `pandera.pandas` es reciente y conviene verificarlo cada cohorte.
- Si el volumen del caso guía creciera en órdenes de magnitud: revisar el coste de
  validar y la política de muestreo.
- Al inicio de cada cohorte: re-verificar las versiones y fechas de la tabla comparativa
  de `sesiones/s02-datos/README.md` §5. La fila de Great Expectations es la que envejece
  más rápido.

## Referencias

- [`src/taxi/data/contract.py`](../../src/taxi/data/contract.py) — los dos contratos y
  los tres niveles
- [`src/taxi/data/loaders.py`](../../src/taxi/data/loaders.py) — hash, orden de
  validación, filtro contabilizado
- [`src/taxi/features/contract.py`](../../src/taxi/features/contract.py) — la definición
  única de features
- [`tests/conftest.py`](../../tests/conftest.py) — los `fixtures`, incluidos los tres
  rotos
- [`tests/data/test_niveles_de_check.py`](../../tests/data/test_niveles_de_check.py) —
  los tres niveles y la calibración del umbral
- [`sesiones/s02-datos/README.md`](../../sesiones/s02-datos/README.md) — el material de
  clase, con las mediciones
- [ADR 001 — caso guía y particiones](001-caso-guia-y-particiones.md)
- [ADR 003 — umbrales de drift](003-umbrales-de-drift.md) — el otro lado del puente
- [pandera.readthedocs.io](https://pandera.readthedocs.io/) ·
  [docs.greatexpectations.io](https://docs.greatexpectations.io/) ·
  [docs.pydantic.dev](https://docs.pydantic.dev/)
