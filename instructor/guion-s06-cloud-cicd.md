# Guion de clase — Sesión 6: Cloud y CI/CD

Guion minutado para las **4 horas** del formato de sesión del curso. Cada bloque indica
qué archivo abrir, qué comando correr y qué salida esperar.

**Duración total:** 240 min (4 h), con pausa de 15 min.
**Terminales:** 2 (una para el gate, una para AWS o Compose). 3 si se abre la UI de MLflow.
**Directorio base:** la **raíz del repositorio**.
**Material del estudiante:** [`sesiones/s06-cloud-cicd/`](../sesiones/s06-cloud-cicd/).

| Tramo | Min | Bloques |
|---|---|---|
| Arranque | 0-15 | 1 |
| El dolor | 15-40 | 2 |
| Bloque A — el gate de promoción | 40-95 | 3, 4, 5 |
| Pausa | 95-110 | — |
| Bloque B — CI/CD y nube | 110-165 | 6, 7, 8, 9 |
| Taller | 165-220 | 10 |
| Cierre | 220-240 | 11 |

---

## Lo primero que hay que decir, en el minuto 0

**Local es el default y nada evaluable depende de la nube.** Decirlo antes de cualquier
otra cosa, porque baja la ansiedad de media clase:

> "El taller de hoy se aprueba con Docker Compose y GitHub Actions. AWS es una demo mía y
> un laboratorio opcional. Nadie necesita una tarjeta de crédito para pasar esta sesión."

---

## Antes de clase (checklist del instructor)

### El gate tiene que poder demostrarse

```bash
# 1. Debe existir un @champion, y debe ser un modelo decente.
uv run python -c "
from taxi.models import registry
mv = registry.version_por_alias('nyc-taxi-duration', 'champion')
print('champion ->', mv.version if mv else 'NO HAY. Corre: taxi data && taxi train --hpo && taxi promote')
"

# 2. El holdout tiene que estar preparado, o el gate devuelve exit 2.
uv run taxi data

# 3. Ensayar el rechazo ANTES de la clase. Es la demo central del bloque 4.
uv run taxi promote --mejora-minima 0.99 --dry-run   # debe salir RECHAZADO, exit 1
```

### La demo de AWS

- **Grabar la demo con antelación** (bloque 8): ECR + App Runner, desde el `docker push`
  hasta el `curl /health`, con el teardown al final. Si la consola falla en vivo, se
  proyecta la grabación y la clase no pierde el hilo. **Es plan A, no plan B: se graba
  siempre.**
- Verificar que el **presupuesto de 10 USD** existe en la cuenta del curso:

```bash
aws budgets describe-budgets --account-id "$(aws sts get-caller-identity --query Account --output text)" \
  --query 'Budgets[].{Nombre:BudgetName,Limite:BudgetLimit.Amount}'
```

- Tener el IAM user de cada equipo creado, con la política de
  [`scripts/politica-iam-minima.json`](../sesiones/s06-cloud-cicd/scripts/politica-iam-minima.json)
  rellenada.
- Tener la sesión de terminal **con `AWS_REGION` y `EQUIPO` ya exportadas**, y el
  `aws sts get-caller-identity` ya corrido. Perder cuatro minutos en la proyección
  configurando credenciales es la forma más rápida de perder a la clase.

### La regla de proyección

**Nunca proyectar la salida de `get-secret-value`, `create-access-key` ni el contenido de
un `.env`.** Tener una segunda terminal, sin historial, para lo que sí se puede mostrar.

---

## Mapa de archivos

```
.github/workflows/
├── ci.yml                    # Bloque 6: ¿el código está bien?
├── cd.yml                    # Bloques 6 y 7: ¿esto debe atender tráfico?
└── nightly-smoke.yml         # Bloque 6: ¿el caso guía sigue funcionando?

scripts/promote.py            # Bloques 3, 4 y 5: el gate (presentación)
src/taxi/models/evaluate.py   # Bloques 3 y 4: el gate (política pura)
src/taxi/models/registry.py   # Bloque 5: aliases, tags y rollback
tests/unit/test_gate.py       # Bloque 4: la política, sin infraestructura

sesiones/s06-cloud-cicd/
├── README.md                 # Bloques 2, 8 y 11
├── cicd.md                   # Bloques 3, 4, 5, 6, 7
├── guia-aws.md               # Bloque 8
├── taller.md                 # Bloque 10
├── scripts/
│   ├── teardown.sh           # Bloque 9 (obligatorio)
│   ├── politica-iam-minima.json          # Bloque 8
│   ├── presupuesto.json                  # Bloque 9
│   └── presupuesto-notificaciones.json   # Bloque 9
├── _soluciones/              # no publicar antes del taller
│   ├── solucion-taller.md
│   └── evidencia.sh
└── _contraejemplo-insegure-aws/          # Bloque 7 (seguridad)

docs/adr/007-gate-de-promocion.md         # Bloque 5
```

---

## BLOQUE 1 — Arranque (0-15 min)

**Archivos:** ninguno. **Terminales:** 0.

1. **Arranque directo** (5 min): dudas sueltas de S05 si las hay, y en una frase propia lo que quedó — el servicio, la
   imagen, la carga por alias, el digest. La pregunta de cierre que conecta con hoy:
   *"desplegaron a mano. ¿Cuántos pasos eran y en cuáles se pueden equivocar?"*
2. **Revisión del CI de los talleres entregados** (7 min): abrir dos PR y mirar el
   workflow. Hoy tiene un valor extra: **el CI es el tema de la sesión**. Aprovechar para
   señalar qué job responde qué pregunta.
3. **Encuadre y la regla de la nube** (3 min): la frase del minuto 0, más el mapa: "la
   primera mitad es el gate —la decisión— y la segunda es la plomería que la ejecuta."

---

## BLOQUE 2 — El dolor (15-40 min)

**Terminales:** 1. **No se abre la consola de AWS en este bloque.**

### Acto 1 — Los doce minutos y las tres oportunidades de error (11 min)

Desplegar una versión a mano, en vivo, **con cronómetro a la vista**. Contra el registro
local o contra ECR, da igual:

```bash
docker build -t mlops-curso/api:v2 .
docker tag mlops-curso/api:v2 mlops-curso/api:latest
# push al registro
# actualizar el servicio y reiniciarlo
curl -fsS http://127.0.0.1:8000/health
```

**Mide el tiempo real y escríbelo en el tablero.** No hay una cifra en este material a
propósito: depende de la red del salón, del tamaño de la imagen y del cache. Lo que
importa es que la clase vea el número **suyo** y lo compare con lo que tarda un `git push`
en el bloque 6.

Mientras corre el build, la pregunta: *"¿en cuáles de estos cinco pasos se pueden
equivocar?"* Recoger respuestas y completar con la tabla del
[README sección 1](../sesiones/s06-cloud-cicd/README.md). La que casi nadie dice: **construir con
cambios sin comitear** — la imagen contiene código que no está en ningún commit.

Y la pregunta que cierra el acto, escrita en el tablero:

> **¿Qué imagen exacta está corriendo ahora en producción, y quién aprobó que estuviera
> ahí?**

Con este procedimiento no hay respuesta. `latest` no dice qué bytes son, y de la decisión
solo queda el historial de bash de alguien.

### Acto 2 — El pipeline verde que promovió un modelo peor (12 min)

**Es el acto que da sentido a la sesión.** Proyectar el código del repositorio original:

```python
client.transition_model_version_stage(
    name=model_name,
    version=version,
    stage="Production",
    archive_existing_versions=True,
)
```

Leerlo despacio y preguntar: *"¿cuándo se ejecutaba esto?"* Respuesta: **al final de cada
corrida del entrenamiento.** Y el `cron` era `*/2 * * * *`: 720 promociones al día.

La demostración en vivo. Registrar un modelo deliberadamente peor:

```bash
# El baseline de la media: peor por construcción que cualquier @champion.
uv run taxi train --modelo media --registrar
```

**Salida esperada:** el entrenamiento termina en verde y registra la versión con el alias
`@candidate` y `validation_status=pending`.

Ahí está el momento didáctico. Preguntar: *"con el código de arriba, ¿dónde estaría este
modelo ahora?"* Respuesta: **en producción, y el anterior archivado.**

Escribir en el tablero la frase de la sesión:

> **Un pipeline verde significa "el proceso corrió", no "el resultado es bueno".** CI/CD
> automatiza la *ejecución* de una decisión. Si la decisión no está codificada en ninguna
> parte, lo que se automatiza es no decidir.

Y el `archive_existing_versions=True`, que es la parte que más duele: **archivar al
anterior destruye el camino de vuelta.** No solo promueve mal; además impide el rollback.

### Cierre del bloque (2 min)

Lo que falta es un **gate**: un punto donde se comparan candidato y champion sobre un
holdout fijo y donde el resultado **puede ser "no"**. Es la primera mitad de la sesión.

---

## BLOQUE 3 — El gate: las tres preguntas y la política pura (40-58 min)

**Archivos:** [`scripts/promote.py`](../scripts/promote.py) (docstring),
[`src/taxi/models/evaluate.py`](../src/taxi/models/evaluate.py). **Terminales:** 1.

### 3.1 Las tres preguntas (5 min)

Antes del código, el razonamiento. Leer el docstring de `promote.py`:

1. Los datos con los que se midió, ¿son válidos?
2. ¿La mejora es real, o cabe dentro del ruido de muestreo?
3. ¿Mejoró en promedio a costa de empeorar en algún segmento?

*"'El modelo nuevo tiene mejor RMSE, subámoslo' no responde ninguna de las tres."*

### 3.2 Los cinco pasos (6 min)

Proyectar la tabla de [`cicd.md`](../sesiones/s06-cloud-cicd/cicd.md#el-gate-de-promoción).
Insistir en la estructura: **tres criterios que se evalúan y dos escrituras en un orden que
importa.**

### 3.3 La política es una función pura (7 min)

Abrir `evaluate.py` y mostrar la firma:

```python
def decidir_promocion(holdout, metricas_candidato, subgrupos_candidato,
                      metricas_champion=None, subgrupos_champion=None, *,
                      mejora_minima=..., umbral_subgrupo=...) -> DecisionGate:
```

**No toca MLflow, no escribe tags, no mueve aliases.** `promote.py` es la capa de
presentación.

Por qué importa, y es un argumento de ingeniería de software, no de ML:

```bash
uv run pytest tests/unit/test_gate.py -q
```

"Estos tests corren sin MLflow. Si la política y la infraestructura estuvieran mezcladas,
necesitarían un registry, alguien los marcaría `skip` y **el criterio de promoción quedaría
sin cobertura**. Es lo que pasa en la mayoría de los repositorios."

Mostrar también `DecisionGate.motivo` y la distinción `NO EVALUADO` vs `FALLA`: *"no lo
revisé"* y *"lo revisé y falló"* son diagnósticos distintos a las tres de la mañana.

---

## BLOQUE 4 — El gate en vivo: rechaza y acepta (58-80 min)

**Terminales:** 1. Es el bloque que hay que ensayar antes de clase.

### 4.1 El rechazo (8 min)

El candidato del bloque 2 (baseline de la media) ya está registrado:

```bash
uv run taxi promote --dry-run
echo "exit code: $?"
```

**Salida esperada:** dos tablas y un veredicto rojo.

```text
Candidato: nyc-taxi-duration version 9
Holdout: particion fija 2023-05 con NNNNN filas. No se uso para seleccionar hiperparametros.
Champion actual: version 8

        Candidato vs @champion en el holdout fijo
metrica  candidato  champion  delta rel.
rmse     <mayor>    <menor>   +XX.XX%    empeora
...

              Criterios del gate
1  contrato_de_datos           PASA   NNNNN filas del holdout cumplen ViajesProcesados
2  mejora_global               FALLA  rmse candidato=... vs champion=...; objetivo <= ...
3  sin_regresion_por_subgrupo  FALLA  N de M subgrupos se degradan mas de 5.0%: ...

RECHAZADO — criterios no superados: mejora_global, sin_regresion_por_subgrupo
@champion sigue en version 8. El modelo que ya estaba sirviendo no se toco.
exit code: 1
```

**No cites números concretos en clase**: dependen del `@champion` de tu máquina. Lo que se
señala es la **estructura** de la salida: qué criterio falló, con qué número, y qué NO
pasó.

Y la comprobación que cierra el criterio, que es la mitad que se olvida:

```bash
uv run python -c "
from taxi.models import registry
mv = registry.version_por_alias('nyc-taxi-duration', 'champion')
print('champion sigue en la version', mv.version if mv else 'ninguna')
"
```

### 4.2 Los tres criterios, uno por uno (9 min)

**Criterio 1 — el dato primero.** Preguntar: *"¿por qué validar el holdout antes de mirar
métricas?"* Respuesta: un RMSE sobre datos inválidos no significa nada, y **promover en
base a él es peor que no promover, porque el gate habría dado una garantía falsa.**

**Criterio 2 — el margen.** Preguntar: *"¿por qué no basta `rmse_cand < rmse_champ`?"*
Dejar que lo piensen. Respuesta: el **churn de modelos** — con ruido de muestreo, dos
modelos equivalentes se alternan indefinidamente, y cada rotación cuesta un despliegue y
rompe la comparabilidad de las métricas de negocio.

Y decir la verdad sobre el número: **el 1% es un umbral elegido, no derivado.** Lo riguroso
sería un test estadístico con el tamaño del holdout. Está en `config.py` para poder
discutirlo.

Aquí también el detalle que hace que muchos gates reales no sirvan: **el champion se
reevalúa** sobre el holdout actual, no se leen sus métricas guardadas. Mostrar la línea en
`promote.py`. "Si su holdout cambió, los números viejos no son comparables — y un gate que
compara números incomparables es peor que no tener gate."

**Criterio 3 — la regresión silenciosa.** El caso: el RMSE global baja porque el modelo
mejora en viajes cortos en hora valle y se degrada en viajes largos de madrugada. El
promedio dice "mejor".

Y el argumento que hay que decir en voz alta: **es la misma técnica que detecta
inequidad.** Cuando el segmento que se degrada corresponde a un grupo de personas en lugar
de a un rango de millas, el mecanismo es idéntico; cambia la consecuencia.

Tres decisiones honestas del criterio: umbral por subgrupo (5%) **más laxo** que el global
(1%) porque hay menos datos y más varianza; `MIN_FILAS_SUBGRUPO = 50` porque por debajo
manda el ruido; y **si no hay subgrupos comparables, FALLA** — *el gate no aprueba lo que
no puede verificar.*

### 4.3 La aceptación (5 min)

```bash
uv run taxi train --hpo --trials 10
uv run taxi promote
echo "exit code: $?"     # 0
```

**Salida esperada:** los tres criterios en `PASA`, `PROMOVIDO`, el alias movido, y la línea
que imprime el comando exacto de rollback con la versión anterior.

Señalar esa última línea: **el propio gate te dice cómo volver atrás.** Es una decisión de
diseño: el momento de escribir el procedimiento de rollback es cuando despliegas, no
durante el incidente.

---

## BLOQUE 5 — Exit codes, tag antes que alias, y rollback (80-95 min)

**Archivos:** [`registry.py`](../src/taxi/models/registry.py),
[ADR 007](../docs/adr/007-gate-de-promocion.md). **Terminales:** 1.

### 5.1 Tres exit codes, no dos (6 min)

```bash
docker compose stop mlflow
uv run taxi promote
echo "exit code: $?"      # 2
docker compose start mlflow
```

**Salida esperada:** un mensaje de infraestructura, **no** una tabla de criterios.

La distinción, que es la parte fina de la sesión:

> **"El modelo no es lo bastante bueno" es un resultado exitoso del gate; "no pude medir"
> es una falla del gate.** Confundirlos hace que un MLflow caído se lea como un modelo
> malo, y que alguien reentrene para arreglar un problema de red.

Los dos hacen fallar el pipeline, eso sí. No se despliega un modelo cuyo gate no corrió.

Mostrar `registry.fallar_rapido()` y decir la frase: **un fallback que tarda cuatro minutos
en activarse no es un fallback.** Con los defaults de mlflow (7 reintentos con backoff,
120 s) el job se colgaría antes de devolver el 2.

### 5.2 El orden de las dos escrituras (4 min)

Leer el docstring de `marcar_validacion`. La pregunta: *"¿qué pasa si el proceso muere
entre escribir el tag y mover el alias?"*

- Orden actual: *"validada pero no promovida"*. **Seguro.**
- Orden inverso: un modelo sirviendo tráfico **sin registro de haber sido validado**. Es el
  incidente que se quiere evitar.

Regla transferible, y sirve fuera de MLOps: **cuando dos escrituras no son atómicas, se
ordenan para que el estado intermedio sea el seguro.**

### 5.3 El rollback, en vivo (5 min)

```bash
# Ver dónde está el champion
uv run python -c "from taxi.models import registry; print(registry.version_por_alias('nyc-taxi-duration','champion').version)"

# Volver a la versión anterior
time uv run python -c "from taxi.models import registry; registry.asignar_alias('nyc-taxi-duration', 'champion', '7')"
```

**Mide el tiempo.** Es una escritura de metadatos.

Y la pregunta: *"¿por qué funciona?"* Respuesta: **las versiones del registry son
inmutables.** La versión anterior sigue intacta y el artefacto es bit a bit el que estaba
sirviendo. Es la razón por la que el modelo se referencia por alias y no se copia — y por
la que **no** se archiva al champion anterior.

Cerrar con los **dos rollbacks independientes**: el del modelo (mover el alias) y el de la
imagen (desplegar el digest previo). Dos artefactos, dos rollbacks.

---

## PAUSA (95-110 min)

Nada que dejar corriendo. Si vas a hacer la demo de AWS en vivo, este es el momento de
verificar que la consola responde y que las credenciales están cargadas.

---

## BLOQUE 6 — Los tres workflows (110-128 min)

**Archivos:** [`ci.yml`](../.github/workflows/ci.yml),
[`cd.yml`](../.github/workflows/cd.yml),
[`nightly-smoke.yml`](../.github/workflows/nightly-smoke.yml). **Terminales:** 0 (navegador).

### 6.1 Tres archivos, tres preguntas (4 min)

Proyectar la tabla de [`cicd.md`](../sesiones/s06-cloud-cicd/cicd.md). "Meterlas en un solo
workflow hace que un fallo de lint bloquee un despliegue urgente."

Y aquí se cierra el acto 1 del dolor: **abrir una corrida real del CI en GitHub y comparar
su duración con el número del tablero.** Es el remate del cronómetro.

### 6.2 `ci.yml`: el job `imagen` (5 min)

Leer los dos pasos de verificación. La frase: *"un criterio que verifica una persona se
deja de verificar en la tercera semana."*

Y las tres decisiones de diseño: `TAXI_MODELO_URI=ninguno` (verifica sin registry),
`docker logs` antes del `exit 1` (un job que falla sin log obliga a reproducir en local), y
el bucle con `sleep 1` en lugar de un `sleep 30` fijo.

Contar la nota histórica, porque es el mejor argumento de la sesión: el CI anterior
terminaba en `uv run pytest -q || echo "No tests configured yet"`. **Un pipeline que no
puede fallar es peor que no tener pipeline.** Y estaba rojo —50 errores de ruff, 67
archivos sin formatear— sin que nadie lo notara.

### 6.3 `cd.yml`: el digest y el orden de los jobs (6 min)

Mostrar el diagrama de cinco jobs y detenerse en dos cosas:

**1. `latest` no aparece en los tags.** La referencia que viaja a los deploys es
`${REGISTRY}/${IMAGEN}@${digest}`. "Producción despliega el mismo digest que se verificó en
staging **por construcción**, no por disciplina."

**2. El gate está entre la imagen y el deploy, y su exit code manda.** Sin eso, el CD
despliega cualquier cosa que compile.

Señalar `provenance: true` y `sbom: true`: es lo que permite responder "¿esta imagen tiene
la versión vulnerable de X?" sin reconstruirla.

Y decir lo que **no** es real: los pasos de deploy son `echo`s. La estructura es real, la
ejecución no. El bloque 8 la hace a mano.

### 6.4 `nightly-smoke.yml` (3 min)

Por qué existe: el diagnóstico del repositorio encontró material que funcionó una vez en la
máquina de quien lo escribió y se degradó en silencio. **Nada de eso lo detecta un CI de
lint y tests unitarios.**

Las dos piezas que lo hacen útil: **abre un issue si falla** (y no lo duplica), y tiene
`timeout-minutes: 30`. *"Un nightly que nadie mira es peor que no tenerlo: crea la
sensación de estar cubierto."*

---

## BLOQUE 7 — Ambientes, aprobación y el comentario del PR (128-142 min)

**Archivos:** `cd.yml` (jobs 3, 4 y 5), Settings del repositorio. **Terminales:** 0.

### 7.1 La barrera vive en el Environment (6 min)

Mostrar en el navegador **Settings → Environments → production → Required reviewers**.

La pregunta: *"¿por qué aquí y no con un `if:` en el YAML?"*

> Un `if:` lo puede cambiar **cualquiera con permiso de push**, en el mismo PR que
> introduce el cambio que debía revisarse. **La barrera no debe estar en el archivo que la
> barrera protege.**

Las tres razones por las que producción se aprueba y staging no: alguien asume la decisión,
se introduce una ventana, y obliga a que staging signifique algo.

Y lo que **no** justifica una aprobación manual: usarla como sustituto de tests. "Si el
único filtro real es que alguien haga clic, el pipeline no tiene calidad, tiene ceremonia."

### 7.2 El comentario del PR, y por qué no CML (5 min)

Abrir el job `comentario`. Dos detalles, los dos transferibles:

**El marcador HTML** para actualizar en lugar de acumular. "Un PR con quince pushes
acumula quince comentarios y nadie sabe cuál es el vigente."

**Los valores entran por `env:`**, nunca interpolados en el script. Explicar el ataque:
basta una comilla o un backtick en un valor para romper el JavaScript, y si el valor viene
del título de un PR —que cualquiera puede escribir— para **ejecutar código con el token del
workflow**.

Y por qué no CML: **su última release es la 0.20.6, de octubre de 2024.** Una acción sin
mantenimiento activo en el camino crítico del despliegue es deuda con fecha de vencimiento.
Se reemplaza por veinte líneas de la API de GitHub.

### 7.3 El bloque de seguridad: el contraejemplo (5 min, en parejas)

Abrir [`_contraejemplo-insegure-aws/`](../sesiones/s06-cloud-cicd/_contraejemplo-insegure-aws/)
y **no** explicar nada todavía. En parejas, 3 minutos:

> "Abran `predict.py`, `Dockerfile` y `GUIA_AWS_EC2.md`. Escriban todo lo que este
> despliegue expondría a internet, ordenado por gravedad."

Después, la puesta en común. El que hay que subrayar:

```python
app.run(debug=True, host="0.0.0.0", port=9696)
```

más lo que dice la guía: *"Rango de puertos: 9696. Origen: Anywhere (0.0.0.0/0)"*.

> **El debugger de Werkzeug expuesto a internet es una shell remota potencial.** En una
> guía que un estudiante iba a seguir paso a paso.

Y la pregunta de cierre, que es la lección real:

> **¿Cuál de estos defectos habría detectado el CI de este repositorio?**

`gitleaks` no ve ninguno. `ruff` tampoco. El del usuario root **sí** lo detecta el job
`imagen`. Los otros cinco requieren revisión humana. **Ese es el argumento para tener una
lista de verificación de despliegue.**

---

## BLOQUE 8 — La nube: la traducción y la demo (142-158 min)

**Archivos:** [README sección 2](../sesiones/s06-cloud-cicd/README.md),
[`guia-aws.md`](../sesiones/s06-cloud-cicd/guia-aws.md). **Terminales:** 2.

### 8.1 La tabla que hace la sesión transferible (5 min)

Proyectar la tabla necesidad / AWS / local. **Las columnas de la izquierda son
necesidades; las de la derecha, implementaciones.**

La fila que hay que subrayar: **MinIO habla el protocolo S3.** El código no cambia entre
local y AWS; cambia un endpoint. "Es por eso que su taller es local y esta demo es
opcional sin que se pierda nada conceptual."

Y por qué App Runner y no ECS: **criterio declarado — cuánta ceremonia hay entre "tengo una
imagen" y "hay una URL que responde".** Con ECS hay que crear cluster, task definition,
service, target group, ALB, listener y security groups. En cuatro horas, esa ceremonia se
paga con el tiempo de los conceptos. Decir también sus límites: menos control de red, no
está en todas las regiones, y cobra por memoria provisionada aunque no haya tráfico.

Mostrar la tabla de GCP/Azure en diez segundos: **Cloud Run y Container Apps son el
equivalente directo.** Cambian los comandos, no cambia una idea.

### 8.2 La demo (9 min) — o la grabación

Seguir [`guia-aws.md`](../sesiones/s06-cloud-cicd/guia-aws.md) sección 3 y sección 4, con las variables
ya exportadas. Los comandos, en orden:

```bash
aws sts get-caller-identity                    # con qué identidad opero

aws ecr create-repository --repository-name "$REPO_ECR" --region "$AWS_REGION" \
  --image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true

aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRO"
docker build -t "${REGISTRO}/${REPO_ECR}:v1" .
docker push "${REGISTRO}/${REPO_ECR}:v1"

DIGEST="$(aws ecr describe-images --repository-name "$REPO_ECR" \
  --image-ids imageTag=v1 --query 'imageDetails[0].imageDigest' --output text)"
echo "${REGISTRO}/${REPO_ECR}@${DIGEST}"       # LA unidad de despliegue

aws apprunner create-service --service-name "$SERVICIO" --region "$AWS_REGION" \
  --source-configuration "file:///tmp/source-config.json" \
  --instance-configuration Cpu="1 vCPU",Memory="2 GB" \
  --health-check-configuration Protocol=HTTP,Path=/health,Interval=10,Timeout=5,HealthyThreshold=1,UnhealthyThreshold=5
```

**Mide y comenta el tiempo de creación del servicio.** No hay una cifra aquí a propósito:
varía. Aprovecha la espera para las tres explicaciones que caben:

1. **`--image-tag-mutability IMMUTABLE`**: un `push` a un tag ya usado **falla** en lugar
   de reescribir la historia. Es la lección del bloque 5 de la sesión 5, reforzada por el
   registro.
2. **`Path=/health`**: el default de App Runner es `Protocol=TCP` y `Path=/`. Con TCP basta
   que el puerto acepte conexiones — un proceso que devuelve 500 en todo pasaría el check.
   **La diferencia entre "el puerto está abierto" y "el servicio funciona".**
3. **`AutoDeploymentsEnabled: false`**: con un digest no tendría sentido, porque el digest
   no cambia. Con un tag, App Runner redespliega solo cuando el tag se repunta — cómodo, y
   exactamente lo que la sesión 5 argumenta que **no** se quiere en producción.

Y la verificación:

```bash
URL="https://$(aws apprunner describe-service --service-arn "$SERVICIO_ARN" \
  --query 'Service.ServiceUrl' --output text)"
curl -fsS "$URL/health" | jq
```

**Salida esperada:** `"status": "degradado"`, `"model_loaded": false` — porque se despliega
con `TAXI_MODELO_URI=ninguno` a propósito, para verificar la plataforma antes de meter el
registry en la ecuación. **Decirlo antes de que alguien crea que falló.**

Señalar el `https://`: App Runner sirve TLS con certificado gestionado sin haber
configurado nada. Montarlo a mano en una EC2 —lo que el contraejemplo directamente no
hacía— es media hora de trabajo.

**Plan B, sin dramatizar:** si algo falla, decir "proyecto la grabación" y seguir. Nunca
depurar AWS en vivo más de dos minutos: es tiempo del que la clase no aprende nada.

### 8.3 IAM en dos minutos (2 min)

Abrir [`politica-iam-minima.json`](../sesiones/s06-cloud-cicd/scripts/politica-iam-minima.json)
y mostrar **un solo statement**: `PasarSoloElRolDeAccesoAEcr`.

```json
"Action": "iam:PassRole",
"Resource": "arn:aws:iam::<ACCOUNT_ID>:role/AppRunnerECRAccess-<EQUIPO>",
"Condition": { "StringEquals": { "iam:PassedToService": "build.apprunner.amazonaws.com" } }
```

> **`PassRole` sin restringir permite escalar privilegios.** Quien pueda pasar un rol de
> administrador a un servicio que ejecuta código, es administrador.

Y el secreto en la imagen, en una frase con el `Dockerfile` proyectado:

```dockerfile
COPY .env .     # capa N
RUN rm .env     # capa N+1 — el secreto SIGUE AHÍ
```

"Una imagen es una pila de capas inmutables. `docker history` lo muestra."

---

## BLOQUE 9 — Costo y teardown (158-165 min)

**Archivos:** [`teardown.sh`](../sesiones/s06-cloud-cicd/scripts/teardown.sh).
**Terminales:** 1 (+ navegador en la consola de facturación).

### 9.1 El costo se lee en la consola (4 min)

Abrir **Billing → Cost Explorer**, agrupar por servicio, **y leer los números reales en
voz alta.** No es un anexo: *"un ingeniero de ML que no sabe qué cuesta lo que despliega
toma malas decisiones de arquitectura con total confianza."*

La pregunta clave: *"¿qué se sigue cobrando si nadie manda un request?"*

Las dos dimensiones de App Runner: **memoria provisionada** (se cobra mientras el servicio
exista) y **CPU/memoria activas** (mientras atiende). Los números se leen en la página de
precios y en la consola, no de memoria.

Y la sorpresa que hay que nombrar: **RDS cobra por hora de existencia**, más
almacenamiento y backups. Una instancia olvidada de un laboratorio es la causa número uno
de facturas inesperadas en cursos de nube.

Mostrar el presupuesto de 10 USD y decir la limitación: **un presupuesto avisa, no
frena.** No existe un "corta el gasto" en AWS. Por eso el teardown es obligatorio.

### 9.2 El teardown (3 min)

```bash
EQUIPO=demo bash sesiones/s06-cloud-cicd/scripts/teardown.sh --dry-run
EQUIPO=demo bash sesiones/s06-cloud-cicd/scripts/teardown.sh
```

Tres cosas que señalar en el script, y las tres son transferibles a cualquier teardown:

1. **El orden es inverso al de creación.** App Runner antes que ECR, porque un servicio en
   marcha mantiene una referencia a la imagen.
2. **Es idempotente.** Correrlo dos veces no falla. "Un teardown que aborta a la mitad deja
   lo peor: la mitad caro."
3. **Termina verificando.** La sección 7 lista lo que quedó. *"'Corrí el teardown' no es
   evidencia; la salida de los `list` sí."*

Y el detalle que hay que explicar: **se borra el servicio, no se pausa.** `pause-service`
reduce el cómputo a cero pero el servicio sigue existiendo. El objetivo es dejar la cuenta
como estaba.

Cerrar con el argumento pedagógico: *"en un proyecto real el teardown es lo que hace
posible experimentar. Un equipo que no sabe destruir su infraestructura no crea entornos de
prueba, y sin entornos de prueba prueba en producción."*

---

## BLOQUE 10 — Taller (165-220 min)

**Archivo:** [`sesiones/s06-cloud-cicd/taller.md`](../sesiones/s06-cloud-cicd/taller.md).

**Arranque (5 min).** Repetir la regla: **los criterios 1 a 7 no necesitan AWS.** El 8 es
opcional, y **descuenta** si se hizo el despliegue y no el teardown.

Subrayar el criterio 3, que es el núcleo: *"los dos casos —rechazo y aceptación— en el log
del workflow. Un gate que solo se ha visto aprobar es indistinguible de un `echo 'todo
bien'`."*

Mencionar que `_soluciones/evidencia.sh` genera la evidencia del PR, sin abrir las
soluciones.

**Circulación (45 min).** Los cuatro problemas que vas a encontrar, en orden de frecuencia:

| Lo que verás | Qué preguntar |
|---|---|
| El gate siempre aprueba | "¿de dónde salen las métricas del champion?" (leídas del run en lugar de reevaluadas) |
| Exit 1 cuando MLflow está caído | "¿cómo distinguen 'modelo malo' de 'no pude medir'?" |
| Solo el enlace verde en el PR | "muéstrenme el rechazo. Sin él, no sé si el gate existe" |
| Tests del gate que necesitan MLflow | "la política, ¿es una función pura?" |

**Cierre (5 min).** Pedir a dos estudiantes que proyecten el log de **su** rechazo. Ver la
tabla de criterios con un `FALLA` y el número que lo justifica, en el repositorio de otro,
es lo que fija la sesión.

---

## BLOQUE 11 — Cierre (220-240 min)

### 11.1 Autoverificación (7 min)

Las cinco preguntas del [README sección 7](../sesiones/s06-cloud-cicd/README.md), con 30 segundos
de silencio cada una. **No las respondas.**

Si nadie sabe la 1 —*"su pipeline terminó en verde y desplegó: ¿qué garantiza eso sobre el
modelo?"*— vuelve al bloque 2. Es la sesión entera.

### 11.2 Trade-offs, dicho honestamente (5 min)

| Ganamos | Nos costó |
|---|---|
| un modelo peor no llega a producción por inercia | el gate es el job más largo del CD |
| el criterio está escrito, versionado y en un solo lugar | tres umbrales elegidos, no derivados |
| rollback en una escritura de metadatos | hay que resistir la tentación de archivar la versión anterior |
| despliegue por digest, auditable | más ceremonia que un `docker push latest` |
| aprobación humana en producción | una ventana de espera en cada release |

Y los huecos declarados, que es lo que hace honesto el cierre: **no hay despliegue
progresivo, ni smoke test real contra staging, ni rollback automático por métricas.** El
orden en que se agregarían: primero el smoke test (evita desplegar algo roto), después el
canary, y el rollback automático al final — porque mal calibrado revierte despliegues
buenos.

### 11.3 Qué NO usar (5 min)

Recorrer la tabla del README sección 8. Detenerse en tres:

- **auto-promoción al final del entrenamiento** → el acto 2 del dolor;
- **`latest` como referencia de despliegue** → el acto 1;
- **dejar el laboratorio "pausado"** → un servicio pausado y una RDS parada **siguen
  cobrando** por existir.

### 11.4 Tarea y puente a la sesión 7 (3 min)

**Tarea:** cerrar el PR del taller con los dos enlaces de Actions. Y si hubo laboratorio,
**la salida del teardown**.

**El puente**, con la pregunta que abre la sesión de monitoreo:

> "Su gate aprobó el modelo con el holdout de mayo de 2023 y su pipeline lo desplegó. Pasan
> tres meses. **¿Cómo saben que ese modelo sigue siendo válido?** El gate midió una vez, en
> un dato del pasado, y desde entonces nadie ha vuelto a mirar."

Dejarla sin responder. Es el dolor de la sesión 7.

### Verificación final del instructor

```bash
# Dejar el registry como estaba antes de la clase, si se movió el alias
uv run python -c "
from taxi.models import registry
mv = registry.version_por_alias('nyc-taxi-duration', 'champion')
print('champion ->', mv.version if mv else 'ninguna')
"
docker compose down

# Y si se hizo la demo de AWS, esto NO es opcional:
EQUIPO=demo bash sesiones/s06-cloud-cicd/scripts/teardown.sh
```
