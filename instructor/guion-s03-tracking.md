# Guion de clase — Sesión 3: Experiment tracking y model registry

Guion minutado para las **4 horas** del formato de sesión del curso. Cada bloque
indica qué archivo abrir, qué comando correr y qué salida esperar.

**Duración total:** 240 min (4 h), con pausa de 15 min.
**Terminales:** 2 (una para el servidor de MLflow, una para los comandos) + el
navegador con la UI.
**Directorio base:** la **raíz del repositorio**. Todos los comandos se corren desde ahí.
**Material del estudiante:** [`sesiones/s03-tracking/`](../sesiones/s03-tracking/).

| Tramo | Min | Bloques |
|---|---|---|
| Arranque | 0-15 | 1 |
| El dolor | 15-40 | 2 |
| Bloque A — tracking | 40-95 | 3, 4, 5 |
| Pausa | 95-110 | — |
| Bloque B — registry, HPO y model card | 110-165 | 6, 7, 8 |
| Taller | 165-220 | 9 |
| Cierre | 220-240 | 10 |

> **Sobre los tiempos de ejecución:** este guion **no da cifras de duración de los
> comandos**. Dependen de los núcleos de la máquina y de la cardinalidad de las
> features, y una cifra inventada en un guion se convierte en una expectativa falsa
> en el aula. Donde importa, el guion dice **"mide y compara"**: cronometra en la
> máquina del instructor durante el ensayo previo y anota **tus** números en la
> checklist del anexo B.

---

## Mapa de archivos

```
src/taxi/                                   # LA implementacion, una sola vez
├── models/train.py                         # Bloques 4, 5, 6: tracking, HPO, signature
├── models/registry.py                      # Bloque 7: aliases y tags
├── models/evaluate.py                      # Bloque 8: metricas y subgrupos
└── config.py                               # Bloque 3: puerto, experimentos, alias

scripts/
├── model_card.py                           # Bloque 8
└── promote.py                              # Bloque 10 (se menciona, es de S06)

sesiones/s03-tracking/
├── README.md                               # Bloques 2, 3 y 10
├── taller.md                               # Bloque 9
├── notebooks/
│   ├── 01-sin-tracking.ipynb               # Bloque 2
│   ├── 02-tracking-con-mlflow.ipynb        # Bloques 4 y 5
│   └── 03-hpo-y-registry.ipynb             # Bloques 6, 7 y 8
├── scripts/
│   ├── train-sin-mlflow.py                 # Bloque 2
│   ├── train-mlflow-basico.py              # Bloque 4
│   └── train-mlflow-completo.py            # Bloque 6
├── scenarios/                              # Bloque 3
├── exercises/                              # Bloque 9 (quien acabe antes)
└── _soluciones/                            # no publicar antes del taller
```

---

## BLOQUE 1 — Arranque (0-15 min)

**Archivos:** ninguno. **Terminales:** 0.

1. **Arranque directo** (5 min): dudas sueltas de S02 si las hay, y en una frase propia lo que quedó — contrato de
   datos, particiones fijas, tests que fallan en CI. La pregunta que conecta con
   hoy: *"ya sabemos que los datos son válidos; ¿cómo sabemos qué modelo salió de
   ellos?"*
2. **Revisión del CI de los talleres entregados** (7 min): abrir dos PR de
   estudiantes y mirar el workflow. Es la rutina de todas las sesiones.
3. **Encuadre de hoy** (3 min): "Hoy no vamos a mejorar ningún modelo. Vamos a hacer
   que se pueda saber **cuál** modelo es, con qué datos salió y cuál está sirviendo."

---

## BLOQUE 2 — El dolor (15-40 min)

**Archivos:** [`sesiones/s03-tracking/scripts/train-sin-mlflow.py`](../sesiones/s03-tracking/scripts/train-sin-mlflow.py),
[`notebooks/01-sin-tracking.ipynb`](../sesiones/s03-tracking/notebooks/01-sin-tracking.ipynb).
**Terminales:** 1. **No se abre MLflow en todo el bloque.**

### Acto 1 — Cinco corridas, cinco `print` (12 min)

```bash
uv run python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 5
uv run python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 10
uv run python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 20
uv run python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 20 --n-estimators 300
uv run python sesiones/s03-tracking/scripts/train-sin-mlflow.py --max-depth 30
```

**Salida esperada por corrida:** una línea
`max_depth=… n_estimators=… -> RMSE=…` y la frase "Y esto es todo lo que queda de la
corrida cuando cierres la terminal".

**Mide y compara:** cronometra la primera y la última. La diferencia entre 25 y 300
árboles es el argumento de por qué el presupuesto de cómputo es una decisión de
ingeniería y no un detalle.

### Acto 2 — Las cinco preguntas, en la pizarra (8 min)

Se hacen en voz alta, mirando solo la terminal:

1. ¿Cuál fue la mejor, y por cuánto?
2. ¿Con qué datos se entrenó la tercera?
3. ¿Con qué versión del código? ¿Había cambios sin commitear?
4. ¿Dónde está ese modelo?
5. ¿Se puede repetir la corrida 2 exactamente dentro de tres meses?

**Guion:** dejar que respondan la 1 (se puede, leyendo hacia arriba) y que se
atasquen en la 2. La 4 es la que duele: el modelo **no existe**, nunca se guardó.

### Acto 3 — Cerrar la terminal (5 min)

Literalmente. Cerrar la ventana y preguntar dónde está el resultado del experimento.

**Cierre del bloque:** la tabla de sección 1 del README de la sesión —qué falta registrar
para responder cada pregunta— y la advertencia: **"el tracking no mejora su modelo"**.
Un experimento bien registrado con un modelo malo sigue siendo un modelo malo; la
diferencia es que se puede descartar con evidencia.

---

## BLOQUE 3 — Anatomía y topologías (40-55 min)

**Archivos:** [`README.md`](../sesiones/s03-tracking/README.md) sección 2,
[`scenarios/`](../sesiones/s03-tracking/scenarios/), `src/taxi/config.py`.
**Terminales:** 2 (aquí se levanta el servidor).

### 3.1 Las cuatro piezas (5 min)

El diagrama de sección 2 del README: tracking server, backend store, artifact store,
registry. **La frase que hay que dejar clavada:** *el Model Registry necesita un
backend de base de datos; con un file store no existe.*

### 3.2 Levantar el servidor (3 min)

```bash
make mlflow
```

**Salida esperada:** el log de `mlflow server` escuchando en `127.0.0.1:5001`, y la
UI vacía en el navegador.

Aquí, y **solo aquí**, se explica el puerto: en macOS AirPlay Receiver ocupa el
puerto por defecto de `mlflow server` y responde un HTTP 403 que no dice nada. El
valor vive en `taxi.config.MLFLOW_PORT`; nadie lo escribe a mano en el resto del
curso.

### 3.3 Los tres escenarios (7 min)

Ejecutar el [escenario 1](../sesiones/s03-tracking/scenarios/scenario-1-file-store.ipynb)
hasta la última celda, la del `try/except`.

**Salida esperada:** `Model Registry no disponible en este escenario (sin tracking
server).`

**Guion:** "Ese error no es un problema de configuración: es la definición del
escenario." Enseñar la tabla de los tres escenarios y decir que el 3 se lee, no se
ejecuta. Abrir el escenario 2 solo para mostrar que **el código de entrenamiento es
el mismo** y lo único que cambia es el `set_tracking_uri`.

---

## BLOQUE 4 — Tracking manual (55-75 min)

**Archivos:** [`scripts/train-mlflow-basico.py`](../sesiones/s03-tracking/scripts/train-mlflow-basico.py),
[`notebooks/02-tracking-con-mlflow.ipynb`](../sesiones/s03-tracking/notebooks/02-tracking-con-mlflow.ipynb)
(hasta la sección 4). **Terminales:** 2.

### 4.1 El script, y qué cambió respecto al bloque 2 (7 min)

```bash
uv run python sesiones/s03-tracking/scripts/train-mlflow-basico.py --max-depth 5
uv run python sesiones/s03-tracking/scripts/train-mlflow-basico.py --max-depth 10
uv run python sesiones/s03-tracking/scripts/train-mlflow-basico.py --max-depth 20
```

**Salida esperada:** `RMSE=… | run_id=…` y la línea `Modelo logueado: NO. Ese es el
punto del paso 3.`

Mostrar el `diff` mental: tres líneas (`set_tracking_uri`, `set_experiment`,
`start_run`) y las preguntas 1, 2 y 3 del bloque 2 ya tienen respuesta en la UI.

**Y señalar lo que falta a propósito:** este script **no loguea el modelo**. Es el
estado real en el que estaba este módulo del curso: tracking de métricas sin
trazabilidad de artefactos. Preguntar: *"si dentro de un mes alguien pide el modelo
del mejor run, ¿qué le damos?"*

### 4.2 Los cuatro tipos de cosas que se registran (8 min)

Notebook 02, celda del run manual. Insistir en la distinción:

- una **métrica** responde "¿qué tan bueno?";
- un **tag** responde "¿de qué corrida estamos hablando?".

Confundirlos produce experimentos con 40 runs y ninguna forma de agrupar. El tag
`particiones_train=2023-01,2023-02,2023-03` es lo que hace comparables dos runs.

**Detalle que conviene mostrar:** el notebook usa `mlflow.log_figure` y
`mlflow.log_table` en lugar de `savefig` + `log_artifact`. La versión anterior
escribía `residuals.png` en el directorio del repositorio, así que el artefacto
dependía de dónde se hubiera abierto el notebook.

### 4.3 Comparar por código (5 min)

```python
mlflow.search_runs(experiment_names=["s03-baseline"], order_by=["metrics.valid_rmse ASC"])
```

**Guion:** "La UI sirve para mirar; `search_runs` sirve para decidir, porque
devuelve un DataFrame." Aquí se dice explícitamente el punto débil de MLflow frente
a W&B (la UX de comparación) y por qué la respuesta del curso es programática.

---

## BLOQUE 5 — Autolog, signature y el fallo en vivo (75-95 min)

**Archivos:** notebook 02, secciones 4 a 7. **Terminales:** 2.

### 5.1 `autolog()` y sus límites (6 min)

Ejecutar la celda de autolog.

**Salida esperada:** ~30 params capturados y cinco métricas `training_*`, sin haber
escrito un `log_param`.

**Pregunta antes de explicar:** *"¿qué es lo que sigue faltando?"* La respuesta:
todo lo que no está en la llamada a `fit` — qué datos, la métrica de negocio, los
subgrupos. Y el aviso operativo: **desactivarlo al terminar**, porque si queda
activo cada `fit` posterior crea un run.

### 5.2 `signature` e `input_example` (6 min)

Mostrar `train._ejemplo_de_entrada` y **leer su docstring en voz alta**: es el mejor
ejemplo de la sesión de un bug que solo aparece al servir.

La regla: *una firma es un contrato con consumidores que no controlas; declara el
tipo más permisivo que el modelo acepta, no el más compacto con el que se entrenó.*

### 5.3 El fallo, en vivo (8 min)

Ejecutar la celda de las tres peticiones.

**Salida esperada, literal:**

```
1) tipos correctos -> [14.147 13.371  9.936]
2) float donde se espera entero -> MlflowException | Error: Incompatible input types
   for column hora_pickup. Can not safely convert float64 to int64.
3) falta una feature -> MlflowException | Error: Model is missing inputs ['trip_distance'].
```

**Guion:** "El caso 3 es el importante. Sin firma **no habría fallado**:
`DictVectorizer` ignora las claves que no conoce, así que la petición habría
producido una predicción silenciosamente peor. Un error visible cuesta un ticket; un
error silencioso cuesta un trimestre de decisiones tomadas con predicciones malas."

Cerrar con la tabla de skops vs cloudpickle (sección 4 del README). Si hay tiempo, provocar
el fallo: quitar `skops_trusted_types` y mostrar
*"The saved sklearn model references untrusted types"*.

---

## Pausa (95-110 min)

**Antes de irse a la pausa, lanzar el HPO en la terminal 2:**

```bash
make hpo        # taxi train --hpo --trials 20
```

Es la operación más lenta de la sesión y así los resultados están listos al volver.
**Mide y compara:** anota cuánto tardó en tu máquina durante el ensayo previo; si en
el aula la red o el equipo son peores, baja `--trials`.

---

## BLOQUE 6 — HPO con runs anidados (110-130 min)

**Archivos:** [`notebooks/03-hpo-y-registry.ipynb`](../sesiones/s03-tracking/notebooks/03-hpo-y-registry.ipynb)
sección 1 y sección 2, `src/taxi/models/train.py` (`optimizar_hiperparametros`),
[`scripts/train-mlflow-completo.py`](../sesiones/s03-tracking/scripts/train-mlflow-completo.py).

### 6.1 Por qué 20 informados le ganan a 200 al azar (5 min)

TPE modela la relación entre hiperparámetros y métrica; el pruner abandona los
trials que ya se ven peores que la mediana. El presupuesto de cómputo es parte de la
decisión de ingeniería.

### 6.2 La estructura de runs (7 min)

En la UI, con el resultado que quedó corriendo en la pausa: un parent run y sus
child runs.

**Qué mirar, en este orden:**

| Dónde | Qué | Qué significa si sale mal |
|---|---|---|
| parent | `trials`, `espacio`, `semilla` | sin semilla, el resultado no es reproducible |
| parent | `trials_podados` | si es 0 con muchos trials, el pruner no actúa |
| child | `mejor_iteracion` | si es siempre `n_estimators - 1`, el early stopping no actúa |

El segundo y el tercero son bugs reales del repositorio anterior: declaraba
`EARLY_STOPPING_ROUNDS = 50` y entrenaba `num_boost_round=30`, así que el early
stopping no podía dispararse nunca.

### 6.3 El script, para quien prefiera leer 60 líneas (8 min)

`train-mlflow-completo.py` hace lo mismo en una pantalla y **sí loguea el modelo**.
Mostrar tres cosas del código:

1. `name="modelo"`, no `artifact_path=`;
2. `skops_trusted_types` con los tres tipos, y por qué son tres;
3. la constante `RONDAS_EN_CLASE` y su comentario: acotar el presupuesto es legítimo,
   esconderlo no. **Mide y compara** con `make hpo`.

---

## BLOQUE 7 — Registry: aliases y tags (130-150 min)

**Archivos:** notebook 03 sección 3 a sección 6, `src/taxi/models/registry.py`,
[`docs/adr/002-aliases-en-vez-de-stages.md`](../docs/adr/002-aliases-en-vez-de-stages.md).

### 7.1 Un run no es una versión (5 min)

El diagrama de sección 3 del notebook. Ejecutar:

```python
print(registry.explicar_por_que_no_stages())
```

**Salida esperada:** las cinco razones. Vive en el código a propósito, para que el
notebook y la model card impriman **la misma** explicación: cuando esto estaba
duplicado, un módulo enseñaba aliases y otro usaba stages.

### 7.2 Promover: tag primero, alias después (6 min)

**Preguntar antes de explicar:** *"¿por qué el tag antes del alias?"*

La respuesta: si el proceso muere entre las dos operaciones, "validada pero no
promovida" es seguro; al revés queda un modelo sirviendo tráfico sin registro de
haber sido validado.

### 7.3 Cargar por alias y reproducir la métrica (9 min)

Ejecutar la celda de reproducción.

**Salida esperada:** los dos RMSE **idénticos** y `diferencia absoluta: 0.00e+00`.

**Guion:** "Esto es el criterio de aceptación 1 del taller. Y no sale exacto por
suerte: sale exacto porque el preprocesamiento va dentro del artefacto, porque la
evaluación usa el mismo código y porque los datos son la misma partición completa.
Si a alguien no le sale exacto, una de esas tres cosas no se cumple."

Cerrar con la tabla de diferencias (0, ~1e-6, decimales visibles, enorme) y con el
**rollback**: mover el alias es una escritura de metadatos. Hacerlo en vivo y
cronometrarlo.

### 7.4 El contraejemplo (4 min)

La celda desactivada del notebook, con la tabla de traducción término a término.
Decir por qué está desactivada y por qué el `pre-commit` bloquea esas llamadas en el
resto del repositorio: no es purismo, es que el curso se contradecía a sí mismo.

---

## BLOQUE 8 — `evaluate` y model card (150-165 min)

**Archivos:** notebook 02 sección 6, notebook 03 sección 7, `scripts/model_card.py`.

### 8.1 `mlflow.models.evaluate` (5 min)

El nombre canónico es `mlflow.models.evaluate`; `mlflow.evaluate` es un alias
histórico. Y **`mlflow.genai.evaluate` es otra API** (LLM, S08): **no son
interoperables**. Elegir la equivocada da un error de tipos, no un resultado malo.

### 8.2 Model card generada (10 min)

```bash
make model-card
```

**Salida esperada:** `Generada docs/model-card.md para nyc-taxi-duration v… (@champion).`
y un archivo que empieza con el aviso `ARCHIVO GENERADO`.

**Guion:** "Una model card escrita a mano queda desactualizada en el primer
reentrenamiento. Una generada desde el registry se puede **verificar**: si el modelo
cambió y la card no, es porque nadie corrió el generador, y eso se ve en el diff."

Mostrar la sección de métricas **por subgrupo**: es lo que el promedio esconde y lo
que la documentación técnica del AI Act pide (S07 lo retoma).

Y mostrar el **modo degradado**: parar el servidor de MLflow y volver a correr el
comando. Sale la card sin versión y sin métricas, con un aviso en amarillo. Es
intencional, y la card degradada **no** sirve como evidencia.

---

## BLOQUE 9 — Taller (165-220 min)

**Archivo:** [`sesiones/s03-tracking/taller.md`](../sesiones/s03-tracking/taller.md)

Los estudiantes trabajan **en su propio repositorio de proyecto**. El instructor
circula. Se entrega en clase.

Los siete criterios de aceptación están en el enunciado. Los tres que hay que
recordar en voz alta al empezar:

- el criterio 1 se **mide**: dos números y la diferencia, con la **tolerancia
  declarada**;
- el criterio 4 es un conteo: `len(mlflow.search_runs(...)) >= 20`, **anidados**;
- el criterio 3 es un comando: `make model-card` tiene que existir en su `Makefile`.

Quien acabe antes: los dos ejercicios de
[`exercises/`](../sesiones/s03-tracking/exercises/), que tienen TODO numerados y su
propia tabla de criterios de completitud.

**No publicar `_soluciones/` antes del taller.**

### Errores que van a aparecer, con su causa

| Síntoma | Causa habitual |
|---|---|
| `HTTP 403` al conectar | están apuntando al puerto por defecto de MLflow, ocupado por AirPlay en macOS |
| `RestException` al registrar | el servidor no tiene backend de base de datos: sin eso no hay registry |
| "no veo mi run" | `set_experiment` con otro nombre, o el cliente en otro puerto |
| "registré 2 artefactos y aparecen 0" | `log_artifact` llamado **fuera** del `with` |
| `The saved sklearn model references untrusted types` | default `skops` + una clase propia sin declarar |
| `Can not safely convert int64 to int32` | `input_example` con tipos demasiado estrechos |
| La métrica no se reproduce | otra partición, otro subconjunto, u otra definición de la métrica |
| `database is locked` | dos procesos escribiendo en el mismo SQLite |
| El run queda en verde pero no hay modelo | `log_model` envuelto en `try/except` |

---

## BLOQUE 10 — Cierre (220-240 min)

### 10.1 Panorama de herramientas (7 min)

La tabla de sección 5 del README, **declarando los criterios antes de mostrarla**:
licencia y self-hosting, registry y ciclo de vida, UX de comparación, encaje con el
stack. Fecha de evaluación: agosto de 2026.

Los tres mensajes:

- **MLflow gana** en ser open source, self-hostable de verdad y estándar de facto,
  y en cubrir tracking y registry con la misma API.
- **MLflow pierde** en UX de comparación frente a **W&B**. Decirlo tal cual: comparar
  cincuenta runs es cómodo en W&B e incómodo en MLflow. Por eso la sesión enseña
  `search_runs()`.
- **DVC experiments** juega otro partido: Git-native, sin servidor, fuerte en datos
  versionados, sin gobierno del ciclo de vida del modelo.

Y verificar el estado de la tabla antes de cada cohorte: el panorama comercial
envejece más rápido que los conceptos.

### 10.2 Autoverificación (7 min)

Las cinco preguntas de sección 6 del README, en voz alta y por sorteo:

1. Te pasan un `run_id` con buen RMSE: **¿qué tiene que tener para que el número sea
   comparable con el tuyo?**
2. `autolog()` registró 30 params: **¿qué falta y por qué no puede saberlo?**
3. `Can not safely convert int64 to int32`: **¿el error está en el cliente, en el
   modelo o en la firma?**
4. Alguien propone `transition_model_version_stage`: **dos argumentos que no sean
   "está deprecado"**.
5. El RMSE de `@champion` no coincide con el de su run: **cuatro causas, en orden de
   revisión**.

### 10.3 Qué NO usar (4 min)

Leer la tabla de sección 7 del README: `transition_model_version_stage`,
`get_latest_versions`, `models:/<nombre>/Production`, `artifact_path=`,
`mlflow.evaluate` como nombre canónico, `mean_squared_error(squared=False)`,
`try/except` alrededor de `log_model`, `run_id` hardcodeado, dos artefactos en lugar
de uno.

Y la advertencia práctica: **verificar el `serialization_format` por defecto** en la
versión instalada. En mlflow 3 es `skops`, y eso puede romper código que funcionaba
— con razón.

### 10.4 Tarea y puente a S04 (2 min)

El taller se puede entregar hoy mismo. Y se enuncia lo que de aquí aplica directo al **proyecto**
(que se entrega después de S05, e incluye también lo de S04 y S05): tracking
completo, modelo registrado con `@champion`, model card generada y CI verde.

Puente: "Ya saben entrenar, registrar y documentar. Todo eso lo han hecho **ustedes,
a mano, delante del teclado**. La sesión que viene: que ocurra sin ustedes, y que
cuando falle se pueda saber qué pasó."

---

## Anexo A — Clase y producción: qué cambia y qué no

| Aspecto | En clase | En producción |
|---|---|---|
| Código de entrenamiento | `src/taxi/models/train.py` | **exactamente el mismo** |
| Tracking server | `mlflow server` en localhost | contenedor detrás de un proxy con auth |
| Backend store | SQLite (`mlflow.db`) | Postgres gestionado (RDS) |
| Artifact store | carpeta local (`./mlartifacts`) | S3 o MinIO |
| Quién promueve | el instructor, a mano | el gate de CI (`scripts/promote.py`, S06) |
| Quién entrena | tu portátil | un worker orquestado (S04) |
| Model card | `make model-card` a mano | un paso del pipeline de CD |

**Mensaje final del anexo:** lo que cambia es *dónde* vive la metadata y *quién*
aprieta el botón. La API es la misma.

---

## Anexo B — Checklist antes de clase

- [ ] `make setup` y `make smoke` en verde en la máquina del instructor.
- [ ] `make data` ejecutado: las siete particiones en `data/processed/` y
      `metadata.json` con sus SHA-256. **Sin esto, el bloque 2 depende de la red del
      aula.**
- [ ] Puerto 5001 libre. En macOS, AirPlay Receiver desactivado o el puerto por
      defecto de MLflow ignorado (usamos 5001 precisamente por eso).
- [ ] `make mlflow` arranca y la UI carga en el navegador.
- [ ] **Un `mlflow.db` limpio**, o al menos con los experimentos de la sesión
      vacíos: una UI con 300 runs de ensayos previos hace ilegible el bloque 4.
- [ ] Ensayo previo del bloque 6 (`make hpo`) **cronometrado**, y el número anotado
      aquí: `make hpo con 20 trials = ____ min`. Si es demasiado, decidir el
      `--trials` de la clase.
- [ ] Un modelo en `@champion` **antes** de clase si se quiere mostrar el rollback
      con dos versiones.
- [ ] `make model-card` probado, y probado también **con el servidor apagado** (modo
      degradado).
- [ ] Verificado el estado de la tabla de herramientas del README sección 5: las columnas
      de licencia y de estado envejecen entre cohortes.
- [ ] Decidido si se publica `_soluciones/` (recomendación: no antes del taller).
