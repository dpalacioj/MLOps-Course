# Guion de clase — Sesión 6: Cloud y CI/CD

Guion minutado para **3 horas**, no las 4 del formato del curso. La sesión tiene un
concepto central (el gate) y su plomería (los workflows, la nube); estirarla a cuatro
horas la llenaría de detalles de AWS que envejecen en meses. Si el grupo tiene la cuarta
hora, va entera al taller, con el instructor circulando.

**Duración total:** 180 min, con pausa de 10 min.
**Terminales:** 2 (una con `make mlflow` corriendo, una para los comandos). Navegador
con GitHub y con la grabación de la demo.
**Directorio base:** la **raíz del repositorio**.
**Material del estudiante:** [`sesiones/s06-cloud-cicd/`](../sesiones/s06-cloud-cicd/).

| Tramo | Min | Bloques |
|---|---|---|
| Arranque | 0-10 | 1 |
| El dolor | 10-30 | 2 |
| Bloque A — el gate de promoción | 30-80 | 3, 4, 5 |
| Pausa | 80-90 | — |
| Bloque B — los workflows y la seguridad | 90-127 | 6, 7 |
| Bloque C — la nube: traducción, demo grabada, costo, teardown | 127-160 | 8, 9 |
| Cierre y arranque del taller | 160-180 | 10 |

---

## Lo primero que hay que decir, en el minuto 0

**Todo lo evaluable es local y nadie necesita una cuenta de AWS.** Decirlo antes de
cualquier otra cosa, porque baja la ansiedad de media clase:

> "El taller de hoy se aprueba con MLflow, Docker y GitHub Actions, que ya tienen. AWS
> es una demo mía, grabada, sobre mi cuenta. Nadie necesita una tarjeta de crédito para
> pasar esta sesión."

---

## Antes de clase (lista de verificación del instructor)

### El gate tiene que poder demostrarse

```bash
make mlflow          # en una terminal aparte; queda corriendo toda la clase

# 1. Debe existir un @champion, y debe ser un modelo decente.
uv run python -c "
from taxi.models import registry
mv = registry.version_por_alias('nyc-taxi-duration', 'champion')
print('champion ->', mv.version if mv else 'NO HAY. Corre: taxi data && taxi train --registrar && taxi promote')
"

# 2. El holdout tiene que estar preparado, o el gate devuelve exit 2.
make data

# 3. Ensayar el rechazo ANTES de la clase. Es la demo central del bloque 4.
uv run taxi promote --mejora-minima 0.99 --dry-run   # debe salir RECHAZADO, exit 1
```

### La demo de AWS

- **Grabar la demo con antelación** siguiendo
  [`04-demo-ecr-fargate/README.md`](../sesiones/s06-cloud-cicd/04-demo-ecr-fargate/README.md)
  de punta a punta: desde el `mlflow artifacts download` hasta la sección 8 del
  `teardown.sh` con las seis listas vacías. **Es plan A, no plan B: se graba siempre.**
  En clase no se depura AWS en vivo.
- **Correr el teardown al terminar de grabar** y verificar al día siguiente en Cost
  Explorer que la curva bajó a cero. Anotar el costo real de la grabación: es el número
  que se lee en el bloque 9.
- Tener a mano la salida real del `curl .../predict` contra la IP pública y la del
  teardown, para proyectarlas si la grabación falla.

### El repositorio en GitHub

- **Crear los environments** `staging` y `production` en *Settings → Environments*, con
  un *required reviewer* en `production`. Si no existen, el bloque 7.1 no tiene qué
  mostrar: `cd.yml` los declara, pero GitHub los crea vacíos al primer uso y sin
  protección.
- Abrir la última corrida de `nightly-smoke.yml` en Actions y comprobar que está en
  verde. Es el único workflow del curso donde el gate corre de verdad (el de `cd.yml`
  está detrás de la variable `GATE_ACTIVO`, que no está puesta a propósito). Si está en
  rojo, leer el paso que falló antes de clase: se proyecta en el bloque 6.4.
- Tener abiertos dos PR de talleres de la sesión 5 con su CI, para el arranque.

### La regla de proyección

**Nunca proyectar la salida de `aws configure`, ni un archivo `~/.aws/credentials`, ni
el contenido de un `.env`.** Tener una segunda terminal, sin historial, para lo que sí se
puede mostrar.

---

## Mapa de archivos

```
.github/workflows/
├── ci.yml                    # Bloque 6: ¿el código está bien?
├── cd.yml                    # Bloques 6 y 7: ¿esto debe atender tráfico?
└── nightly-smoke.yml         # Bloque 6: ¿el caso guía sigue funcionando?

scripts/promote.py            # Bloques 3, 4 y 5: el gate (presentación y exit codes)
src/taxi/models/evaluate.py   # Bloques 3 y 4: el gate (política pura)
src/taxi/models/registry.py   # Bloque 5: aliases, tags, fallar_rapido y rollback
tests/unit/test_gate.py       # Bloque 3: la política, sin infraestructura

sesiones/s06-cloud-cicd/
├── README.md                     # Bloques 2 y 10
├── 01-el-gate-de-promocion.md    # Bloques 3, 4, 5
├── 02-los-tres-workflows.md      # Bloques 6, 7
├── 03-de-compose-a-la-nube.md    # Bloque 8
├── 04-demo-ecr-fargate/          # Bloques 8 y 9
│   ├── README.md                 #   la demo paso a paso (grabada)
│   ├── Dockerfile                #   la imagen de S05 + el modelo
│   └── teardown.sh               #   obligatorio al final
├── taller.md                     # Bloque 10
├── _contraejemplo-insegure-aws/  # Bloque 7.3 (seguridad)
└── _soluciones/                  # solo en tu disco

docs/adr/007-gate-de-promocion.md # Bloque 5
```

---

## BLOQUE 1 — Arranque (0-10 min)

**Archivos:** ninguno. **Terminales:** 0.

1. **Recuento de la sesión 5** (4 min): en una frase propia lo que quedó: el servicio, la
   imagen, la carga por alias, el digest. La pregunta que conecta con hoy: *"desplegaron
   a mano. ¿Cuántos pasos eran y en cuáles se pueden equivocar?"*
2. **Revisión del CI de los talleres entregados** (4 min): abrir dos PR y mirar el
   workflow. Hoy tiene un valor extra: **el CI es el tema de la sesión**. Señalar qué
   job responde qué pregunta.
3. **Encuadre** (2 min): la frase del minuto 0, más el mapa: "la primera mitad es el
   gate, la decisión; la segunda es la plomería que la ejecuta; la nube es una
   plataforma más para esa plomería."

---

## BLOQUE 2 — El dolor (10-30 min)

**Archivo:** [README sección 1](../sesiones/s06-cloud-cicd/README.md). **Terminales:** 1.
**No se abre ninguna consola de nube.**

### Acto 1 — Los cinco pasos y las cinco oportunidades de error (9 min)

Desplegar una versión a mano, en vivo, **con cronómetro a la vista**:

```bash
docker build -t mlops-curso/api:v2 .
docker tag mlops-curso/api:v2 mlops-curso/api:latest
# push al registro
# actualizar el servicio y reiniciarlo
curl -fsS http://127.0.0.1:8000/health
```

**Mide el tiempo real y escríbelo en el tablero.** No hay una cifra en el material a
propósito. Mientras corre el build, la pregunta: *"¿en cuáles de estos cinco pasos se
pueden equivocar?"* Recoger respuestas y completar con la tabla del README. La que casi
nadie dice: **construir con cambios sin comitear**.

La pregunta que cierra el acto, escrita en el tablero:

> **¿Qué imagen exacta está corriendo ahora en producción, y quién aprobó que estuviera
> ahí?**

### Acto 2 — El pipeline verde que promovió un modelo peor (9 min)

**Es el acto que da sentido a la sesión.** Proyectar el atajo del README, sección 1,
acto 2 (la llamada a `transition_model_version_stage` con `archive_existing_versions`)
y preguntar: *"¿dónde pondrían esto en su pipeline de la sesión 4?"* Respuesta honesta:
al final del entrenamiento, sin `if`. Y si el pipeline corre cada dos minutos, 720
promociones al día.

La demostración en vivo. Registrar un modelo deliberadamente peor:

```bash
uv run taxi train --modelo media --registrar
```

**Salida esperada** (unos 7 s):

```text
media: valid_rmse=9.6457 (run c12066ab)
Registrado como nyc-taxi-duration v6 con alias @candidate y validation_status=pending. Corre `taxi promote` para el gate.
```

Ahí está el momento didáctico. Preguntar: *"con el atajo de arriba, ¿dónde estaría este
modelo ahora?"* Respuesta: **en producción, y el anterior archivado.** Un RMSE del doble
que el del champion (compararlo con el `rmse_valid` del champion en la UI de MLflow), y
el pipeline en verde.

Escribir en el tablero la frase de la sesión:

> **Un pipeline verde significa "el proceso corrió", no "el resultado es bueno".** CI/CD
> automatiza la *ejecución* de una decisión. Si la decisión no está codificada en ninguna
> parte, lo que se automatiza es no decidir.

### Cierre del bloque (2 min)

Lo que falta es un **gate**: un punto donde se comparan candidato y champion sobre un
holdout fijo y donde el resultado **puede ser "no"**. Es la primera mitad de la sesión.

---

## BLOQUE 3 — El gate: las tres preguntas y la política pura (30-45 min)

**Archivos:** [`01-el-gate-de-promocion.md`](../sesiones/s06-cloud-cicd/01-el-gate-de-promocion.md)
secciones 1 a 4, [`scripts/promote.py`](../scripts/promote.py) (docstring),
[`src/taxi/models/evaluate.py`](../src/taxi/models/evaluate.py). **Terminales:** 1.

### 3.1 Qué es un gate, y las tres preguntas (5 min)

La analogía del examen de conducir (una sola: no agregar otra). Luego leer el docstring
de `promote.py`:

1. Los datos con los que se midió, ¿son válidos?
2. ¿La mejora es real, o cabe dentro del ruido de muestreo?
3. ¿Mejoró en promedio a costa de empeorar en algún segmento?

*"'El modelo nuevo tiene mejor RMSE, subámoslo' no responde ninguna de las tres."*

### 3.2 Los cinco pasos (5 min)

Proyectar la tabla del 01, sección 2. Insistir en la estructura: **tres criterios que
se evalúan y dos escrituras en un orden que importa.**

### 3.3 La política es una función pura (5 min)

Abrir `evaluate.py` y mostrar la firma de `decidir_promocion`. **No toca MLflow, no
escribe tags, no mueve aliases.** `promote.py` es la capa de presentación.

```bash
uv run pytest tests/unit/test_gate.py
```

**Salida esperada:** `21 passed in 1.77s`, sin MLflow. "Si la política y la
infraestructura estuvieran mezcladas, estos tests necesitarían un registry, alguien los
marcaría `skip` y **el criterio de promoción quedaría sin cobertura**. Es lo que pasa en
la mayoría de los repositorios."

Mostrar también la distinción `NO EVALUADO` vs `FALLA`: *"no lo revisé"* y *"lo revisé
y falló"* son diagnósticos distintos a las tres de la mañana.

---

## BLOQUE 4 — El gate en vivo: rechaza, no puede medir, acepta (45-70 min)

**Archivo:** 01, sección 5. **Terminales:** 1. Es el bloque que hay que ensayar antes de
clase.

### 4.1 El rechazo (8 min)

El candidato del bloque 2 (baseline de la media) ya está registrado:

```bash
uv run taxi promote
echo "exit code: $?"
```

**Salida esperada** (unos 10 s; estos números son de una corrida real, los tuyos
dependen de tu `@champion`):

```text
Candidato: nyc-taxi-duration version 6
Holdout: particion fija 2023-05 con 60000 filas. No se uso para seleccionar hiperparametros.
Champion actual: version 1
...
│ 1 │ contrato_de_datos          │ PASA   │ 60000 filas del holdout cumplen ViajesProcesados
│ 2 │ mejora_global              │ FALLA  │ rmse candidato=9.9962 vs champion=4.9104 (+103.57%); objetivo <= 4.8613 (mejora minima 1.0%)
│ 3 │ sin_regresion_por_subgrupo │ FALLA  │ 8 de 8 subgrupos se degradan mas de 5.0%: ...

RECHAZADO — criterios no superados: mejora_global, sin_regresion_por_subgrupo
@champion sigue en version 1. El modelo que ya estaba sirviendo no se toco.
exit code: 1
```

Señalar la **estructura**, no los números: qué criterio falló, con qué número, y qué NO
pasó. Y la comprobación que cierra el criterio, que es la mitad que se olvida:

```bash
uv run python -c "
from taxi.models import registry
mv = registry.version_por_alias('nyc-taxi-duration', 'champion')
print('champion sigue en la version', mv.version if mv else 'ninguna')
"
```

Y en la UI de MLflow (*Models → nyc-taxi-duration → versión 6*): el tag
`validation_status = failed`. **El paso 4 se ejecutó aunque el 5 no**: hay registro.

### 4.2 Los tres criterios, uno por uno (8 min)

**Criterio 1, el dato primero.** *"¿Por qué validar el holdout antes de mirar
métricas?"* Un RMSE sobre datos inválidos no significa nada, y **promover en base a él
es peor que no promover, porque el gate habría dado una garantía falsa.**

**Criterio 2, el margen.** *"¿Por qué no basta `rmse_cand < rmse_champ`?"* Dejar que lo
piensen. Respuesta: el **churn de modelos**. Y decir la verdad sobre el número: **el 1%
es un umbral elegido, no derivado.** Está en `config.py` para poder discutirlo.

Aquí también el detalle que hace que muchos gates reales no sirvan: **el champion se
reevalúa** sobre el holdout actual. Mostrar la línea en `promote.py`.

**Criterio 3, la regresión silenciosa.** El promedio dice "mejor"; el usuario del
segmento afectado dice "peor". Y el argumento que hay que decir en voz alta: **es la
misma técnica que detecta inequidad.**

### 4.3 "No pude medir" no es "el modelo es peor" (5 min)

Apagar MLflow con `Ctrl-C` en su terminal, y:

```bash
uv run taxi promote
echo "exit code: $?"
```

**Salida esperada** (menos de 2 s):

```text
No se pudo hablar con MLflow en http://127.0.0.1:5001 (MlflowException).
No es un problema del modelo: es infraestructura. Levanta el tracking server (make mlflow, o make up) y vuelve a correr el gate.
exit code: 2
```

**No hay tabla de criterios.** No se midió nada, y el mensaje lo dice. La frase:

> **"El modelo no es lo bastante bueno" es un resultado exitoso del gate; "no pude
> medir" es una falla del gate.** Confundirlos hace que un MLflow caído se lea como un
> modelo malo, y que alguien reentrene para arreglar un problema de red.

Los dos hacen fallar el pipeline. Mostrar `registry.fallar_rapido()`: **un fallback que
tarda cuatro minutos en activarse no es un fallback.** Volver a levantar MLflow
(`make mlflow`) antes de seguir.

### 4.4 La aceptación (4 min)

```bash
uv run taxi train --hpo --trials 10     # minutos: lanzarlo y seguir hablando
uv run taxi promote
echo "exit code: $?"
```

**Salida esperada:** los tres criterios en `PASA`, `PROMOVIDO`, el alias movido, y la
última línea con el comando exacto de rollback. **El propio gate te dice cómo volver
atrás.** Decir la verdad si rechaza: si el champion ya está bien afinado, diez trials
pueden no superarlo en un 1%, y eso es el gate haciendo su trabajo, no una demo fallida.

---

## BLOQUE 5 — El orden de las escrituras y el rollback (70-80 min)

**Archivos:** [`registry.py`](../src/taxi/models/registry.py),
[ADR 007](../docs/adr/007-gate-de-promocion.md). **Terminales:** 1.

### 5.1 Tag antes que alias (4 min)

Leer el docstring de `marcar_validacion`. La pregunta: *"¿qué pasa si el proceso muere
entre escribir el tag y mover el alias?"*

- Orden actual: *"validada pero no promovida"*. **Seguro.**
- Orden inverso: un modelo sirviendo tráfico **sin registro de haber sido validado**.

Regla transferible: **cuando dos escrituras no son atómicas, se ordenan para que el
estado intermedio sea el seguro.**

### 5.2 El rollback, en vivo (6 min)

```bash
uv run python -c "from taxi.models import registry; print(registry.version_por_alias('nyc-taxi-duration','champion').version)"
time uv run python -c "from taxi.models import registry; registry.asignar_alias('nyc-taxi-duration', 'champion', '1')"
```

**Mide el tiempo.** Es una escritura de metadatos. *"¿Por qué funciona?"* **Las
versiones del registry son inmutables.** Por eso no se archiva al champion anterior.

Cerrar con los **dos rollbacks independientes**: el del modelo (mover el alias) y el de
la imagen (desplegar el digest previo). Dos artefactos, dos rollbacks. Y dejar el alias
donde estaba antes de la clase.

---

## PAUSA (80-90 min)

Nada que dejar corriendo salvo `make mlflow`. Comprobar que la grabación de la demo
abre y que GitHub carga.

---

## BLOQUE 6 — Los tres workflows (90-115 min)

**Archivos:** [`02-los-tres-workflows.md`](../sesiones/s06-cloud-cicd/02-los-tres-workflows.md),
[`ci.yml`](../.github/workflows/ci.yml), [`cd.yml`](../.github/workflows/cd.yml),
[`nightly-smoke.yml`](../.github/workflows/nightly-smoke.yml). **Terminales:** 0
(navegador).

### 6.1 Tres archivos, tres preguntas (4 min)

Proyectar la tabla del 02. "Meterlas en un solo workflow hace que un fallo de lint
bloquee un despliegue urgente."

Y aquí se cierra el acto 1 del dolor: **abrir una corrida real del CI en GitHub y
comparar su duración con el número del tablero.** Es el remate del cronómetro.

### 6.2 `ci.yml`: el job `imagen` y el paso que no puede fallar (6 min)

Leer los dos pasos de verificación de la imagen. La frase: *"un criterio que verifica
una persona se deja de verificar en la tercera semana."*

Las tres decisiones de diseño: `TAXI_MODELO_URI=ninguno`, `docker logs` antes del
`exit 1`, y el bucle con `sleep 1`.

Proyectar el atajo del 02, sección 1: `uv run pytest -q || echo "No tests configured
yet"`. Preguntar qué pasa con ese job cuando los tests fallan. **Un pipeline que no
puede fallar es peor que no tener pipeline.**

### 6.3 `cd.yml`: el digest, el orden de los jobs, y la verdad sobre el gate (8 min)

Mostrar el diagrama de cinco jobs y detenerse en tres cosas:

**1. `latest` no aparece en los tags.** La referencia que viaja es
`${REGISTRY}/${IMAGEN}@${digest}`. "Producción despliega el mismo digest que se
verificó en staging **por construcción**, no por disciplina."

**2. El gate está entre la imagen y el deploy, y su exit code manda.**

**3. La verdad de este repositorio.** Abrir una corrida de `cd.yml` en Actions: el job
del gate aparece `skipped`, y los deploys también. Explicar la condición
`vars.GATE_ACTIVO == 'true'`: los runners de GitHub no llegan al MLflow de mi máquina,
y un gate que falla por infraestructura no distingue "peor" de "no pude medir". Por eso
el gate de verdad corre en el nightly, con MLflow dentro del runner. **Decirlo así, sin
adornos: un material que finge que el gate corre en cada push enseña a fingir.**

Y decir lo que **no** es real: los pasos de deploy son `echo`s. La estructura es real,
la ejecución no. El bloque 8 la hace a mano.

### 6.4 `nightly-smoke.yml` (4 min)

Abrir la última corrida. Por qué existe: el material funciona una vez en la máquina de
quien lo escribió y se degrada en silencio; **nada de eso lo detecta un CI de lint y
tests unitarios.** Las dos piezas que lo hacen útil: abre un issue si falla (y no lo
duplica), y `timeout-minutes: 30`.

Señalar en el log el paso `Gate de promocion`: ahí está el gate en un log de Actions, y
es lo que el taller pide replicar.

### 6.5 Las actions envejecen (3 min)

La tabla de versiones del 02, sección 5. Node 20 sale de los runners el 23 de septiembre
de 2026; desde entonces toda action en una versión mayor vieja deja de arrancar. "Es el lockfile de la
sesión 1 en la otra dirección: fijar protege, pero obliga a actualizar a propósito."

---

## BLOQUE 7 — Ambientes, aprobación y seguridad (115-127 min)

**Archivos:** `cd.yml` (jobs 3, 4 y 5), Settings del repositorio,
[`_contraejemplo-insegure-aws/`](../sesiones/s06-cloud-cicd/_contraejemplo-insegure-aws/).

### 7.1 La barrera vive en el Environment (4 min)

Mostrar en el navegador **Settings → Environments → production → Required reviewers**
(creado antes de clase). La pregunta: *"¿por qué aquí y no con un `if:` en el YAML?"*

> Un `if:` lo puede cambiar **cualquiera con permiso de push**, en el mismo PR que
> introduce el cambio que debía revisarse. **La barrera no debe estar en el archivo que la
> barrera protege.**

Y el detalle práctico: con el plan gratuito, esto solo existe en repositorios públicos.
Está en el taller.

### 7.2 El comentario del PR, y por qué no CML (3 min)

Abrir el job `comentario`. El marcador HTML para actualizar en lugar de acumular, y los
valores por `env:`, nunca interpolados (*script injection*). Por qué no CML: última
release octubre de 2024; una acción sin mantener en el camino crítico es deuda con fecha
de vencimiento.

### 7.3 El bloque de seguridad: el contraejemplo (5 min, en parejas)

Abrir la carpeta y **no** explicar nada todavía. En parejas, 3 minutos:

> "Abran `predict.py`, `Dockerfile` y `guia-despliegue-ec2.md`. Escriban todo lo que
> este despliegue expondría a internet, ordenado por gravedad."

Puesta en común. El que hay que subrayar: `app.run(debug=True, host="0.0.0.0")` más
*"Origen: Anywhere (0.0.0.0/0)"* en la guía. **El debugger de Werkzeug expuesto a
internet es una shell remota potencial.**

La pregunta de cierre: **¿cuál de estos defectos habría detectado el CI de este
repositorio?** `gitleaks` no ve ninguno; `ruff` tampoco; el del usuario root **sí** lo
detecta el job `imagen`. Los otros cinco requieren revisión humana.

---

## BLOQUE 8 — La nube: la traducción y la demo grabada (127-150 min)

**Archivos:** [`03-de-compose-a-la-nube.md`](../sesiones/s06-cloud-cicd/03-de-compose-a-la-nube.md),
[`04-demo-ecr-fargate/README.md`](../sesiones/s06-cloud-cicd/04-demo-ecr-fargate/README.md),
la grabación. **Terminales:** 0.

### 8.1 La tabla que hace la sesión transferible (5 min)

Proyectar la tabla del 03, sección 1. **Las columnas de la izquierda son necesidades;
las de la derecha, implementaciones.** La fila que hay que subrayar: **MinIO habla S3.**

Y la fila de cómputo, con la noticia: **App Runner está cerrado a clientes nuevos**
(leerlo de su documentación, con fecha). Por eso la demo usa ECS con Fargate, y por eso
hay que mirar la documentación antes de cada cohorte: la nube cambia debajo del
material.

### 8.2 Dos formas de llevar el modelo al servicio (4 min)

La tabla del 03, sección 3. La pregunta: *"¿por qué la demo mete el modelo en la imagen,
si la sesión 5 dijo que no?"* Respuesta: la sesión 5 dijo que no se copia **a mano un
run sin saber cuál es**; aquí se exporta del registry por alias y la versión queda en la
etiqueta de la imagen. El costo (rebuild para cambiar de modelo, `version=desconocida`
en `/modelo`) está dicho y se ve en la grabación.

### 8.3 La grabación (12 min)

Proyectar la grabación de [`04-demo-ecr-fargate/README.md`](../sesiones/s06-cloud-cicd/04-demo-ecr-fargate/README.md),
pausando en cinco momentos:

1. **La imagen local responde `14.2` minutos** (sección 1.3). Anotarlo en el tablero.
2. **El push y su tiempo** (sección 2.2). "Cada versión de modelo es un push de la capa
   nueva; la base ya está arriba."
3. **El digest** (sección 2.3): *"esto, con `@sha256`, es lo que se despliega. El tag es
   para nosotros."*
4. **La task definition** (sección 7): señalar `image` por digest, `runtimePlatform`, y
   que **ECS ignora el `HEALTHCHECK` del Dockerfile**: solo vigila el que está declarado
   ahí.
5. **La predicción desde la IP pública responde `14.2`** (sección 8.3). Mismo digest,
   mismos bytes, misma respuesta. Es la sesión 5 comprobada en la nube.

Y el `wait tasks-running` con su tiempo (48 s en la grabación de referencia, frente a
4 s del `docker run` local): esa diferencia es el precio de que la imagen viaje con el
modelo.

**Si la grabación falla:** proyectar las salidas reales guardadas y seguir. Nunca
depurar AWS en vivo más de dos minutos.

### 8.4 IAM en dos minutos (2 min)

Los dos roles de la tarea (03, sección 4): el de **ejecución** (la plataforma baja la
imagen y escribe logs) y el de **tarea** (tu código), que la demo **no crea** porque la
API no llama a ninguna API de AWS. Privilegio mínimo es también no dar un rol.

Y el secreto en la imagen, en una frase con el `Dockerfile` proyectado: `COPY .env` +
`RUN rm .env` **no borra nada**. Una imagen es una pila de capas inmutables.

---

## BLOQUE 9 — Costo y teardown (150-160 min)

**Archivos:** 03 sección 5, 04 secciones 9 y 11, [`teardown.sh`](../sesiones/s06-cloud-cicd/04-demo-ecr-fargate/teardown.sh).

### 9.1 El costo se lee en la consola (5 min)

Proyectar Cost Explorer del día de la grabación, agrupado por servicio, **y leer los
números reales en voz alta.** Después la tabla del 03, sección 5, con fecha.

La pregunta clave: *"¿qué se sigue cobrando si nadie manda un request?"* La tarea de
Fargate y su IP, por segundo. El repositorio, por GB. Y las cifras que se llevan: **la
demo corriendo cuesta unos 0,045 USD por hora; olvidada un mes, unos 33 USD.** El costo
no está en usar la nube, está en no apagarla.

Y la limitación del presupuesto: **avisa, no frena.** Por eso el teardown es
obligatorio.

### 9.2 El teardown (5 min)

Proyectar el final de la grabación: la sección 8 del `teardown.sh` con las seis listas
vacías. Tres cosas que señalar en el script, transferibles a cualquier teardown:

1. **El orden es inverso al de creación.** Tareas antes que cluster; cluster antes que
   security group, porque la interfaz de red de la tarea vive en ese grupo.
2. **Es idempotente.** Correrlo dos veces no falla. "Un teardown que aborta a la mitad
   deja lo peor: la mitad cara."
3. **Termina verificando.** *"'Corrí el teardown' no es evidencia; la salida de los
   `list` sí."*

Cerrar con el argumento pedagógico: *"en un proyecto real el teardown es lo que hace
posible experimentar. Un equipo que no sabe destruir su infraestructura no crea entornos
de prueba, y sin entornos de prueba prueba en producción."*

---

## BLOQUE 10 — Cierre y arranque del taller (160-180 min)

### 10.1 Autoverificación (6 min)

Las cinco preguntas del [README sección 2](../sesiones/s06-cloud-cicd/README.md), con 30
segundos de silencio cada una. **No las respondas.** Si nadie sabe la 1 (*"su pipeline
terminó en verde y desplegó: ¿qué garantiza eso sobre el modelo?"*), vuelve al bloque 2.
Es la sesión entera.

### 10.2 Trade-offs, dicho honestamente (4 min)

| Ganamos | Nos costó |
|---|---|
| un modelo peor no llega a producción por inercia | el gate es el job más largo del CD |
| el criterio está escrito, versionado y en un solo lugar | tres umbrales elegidos, no derivados |
| rollback en una escritura de metadatos | hay que resistir la tentación de archivar la versión anterior |
| despliegue por digest, auditable | más ceremonia que un `docker push latest` |
| aprobación humana en producción | una ventana de espera en cada release |

Y los huecos declarados: **no hay despliegue progresivo, ni smoke test real contra
staging, ni rollback automático por métricas, ni el gate corre en el CD del propio
repositorio.** El orden en que se agregarían está en el 02, sección 6.

### 10.3 Arranque del taller (7 min)

**Archivo:** [`taller.md`](../sesiones/s06-cloud-cicd/taller.md).

Repetir la regla: **los criterios 1 a 7 no necesitan AWS.** El 8 es opcional y
**descuenta** si se hizo el despliegue y no el teardown.

Subrayar el criterio 3 y su receta: MLflow dentro del runner, dos candidatos en el mismo
job, y el rechazo **afirmado** con `test "$codigo" -eq 1`, no tragado con `|| true`.
*"Un gate que solo se ha visto aprobar es indistinguible de un `echo 'todo bien'`."*

Los cuatro problemas que vas a encontrar al revisar, en orden de frecuencia:

| Lo que verás | Qué preguntar |
|---|---|
| El gate siempre aprueba | "¿de dónde salen las métricas del champion?" (leídas del run en lugar de reevaluadas) |
| Exit 1 cuando MLflow está caído | "¿cómo distinguen 'modelo malo' de 'no pude medir'?" |
| Solo el enlace verde en el PR | "muéstrenme el rechazo. Sin él, no sé si el gate existe" |
| Tests del gate que necesitan MLflow | "la política, ¿es una función pura?" |

Si el grupo tiene la cuarta hora, el taller sigue en clase con el instructor circulando.
Si no, es tarea, y el cierre de la próxima sesión empieza por dos estudiantes proyectando
el log de **su** rechazo.

### 10.4 Puente a la sesión 7 (3 min)

> "Su gate aprobó el modelo con el holdout de mayo de 2023 y su pipeline lo desplegó.
> Pasan tres meses. **¿Cómo saben que ese modelo sigue siendo válido?** El gate midió una
> vez, en un dato del pasado, y desde entonces nadie ha vuelto a mirar."

Dejarla sin responder. Es el dolor de la sesión 7.

### Verificación final del instructor

```bash
# Dejar el registry como estaba antes de la clase, si se movió el alias
uv run python -c "
from taxi.models import registry
mv = registry.version_por_alias('nyc-taxi-duration', 'champion')
print('champion ->', mv.version if mv else 'ninguna')
"
# Ctrl-C en la terminal de `make mlflow`

# Si se volvió a correr la demo de AWS en vivo, esto NO es opcional:
DEMO=taxi-demo bash sesiones/s06-cloud-cicd/04-demo-ecr-fargate/teardown.sh
```
