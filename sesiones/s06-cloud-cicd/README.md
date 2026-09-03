# Sesión 6 — Cloud y CI/CD: automatizar el despliegue y decidir qué se despliega

> Pregunta que responde la sesión: **¿cómo dejo de desplegar a mano, y cómo evito que
> el pipeline automatice el despliegue de un modelo peor que el que ya está
> sirviendo?**

## Cómo funciona esta sesión

Léelo antes de nada, porque cambia lo que hay que preparar:

- **Todo lo evaluable es local.** El taller se aprueba con MLflow, Docker y GitHub
  Actions, que ya tienes desde las sesiones anteriores. Nadie necesita una cuenta de
  AWS ni una tarjeta de crédito.
- **La nube es una demo del instructor, grabada con antelación**, sobre su propia
  cuenta. El paso 04 está escrito para que se pueda seguir solo cuando se tenga una
  cuenta; en clase se ve la grabación y se discute.
- **Dura tres horas, no cuatro.** La sesión tiene un concepto central (el gate) y su
  plomería (los workflows, la nube). Estirarla a cuatro horas la llenaría de detalles
  de AWS que envejecen en meses. Si sobra tiempo, va al taller.
- **Se construye sobre lo que ya tienes.** El gate promueve el modelo del caso guía que
  registraste en la sesión 3 y que la sesión 4 reentrena; el CD construye la imagen
  de la sesión 5; la demo despliega exactamente esa imagen. No hay un ejemplo nuevo.

### Con qué llegas, y qué agrega esta sesión

| Ya tienes (sesiones 3 a 5) | Esta sesión agrega |
|---|---|
| un registry con versiones y un alias `@champion` | **la decisión** de cuándo mover ese alias, codificada y con exit code |
| un pipeline de entrenamiento orquestado | un pipeline de **despliegue** que puede decir "no" |
| una imagen con la API, identificada por digest | quién la construye, dónde se publica y qué la despliega |
| Docker Compose con MinIO y Postgres | la traducción de cada pieza a un servicio de nube, y su precio |

## Objetivos

Al terminar la sesión, cada estudiante puede:

1. **Enumerar** los pasos de un despliegue manual y **decir** en cuáles se puede
   equivocar sin que nada avise.
2. **Enunciar los cinco pasos del gate de promoción** y **demostrar** que rechaza un
   candidato peor y acepta uno mejor, con el log como evidencia.
3. **Distinguir** los tres exit codes del gate y **explicar** por qué "no pude medir" no
   es lo mismo que "el modelo es peor".
4. **Leer** los tres workflows del repositorio y **decir qué pregunta responde cada
   job**, incluido por qué el gate está detrás de una variable en el CD del curso.
5. **Ejecutar un rollback** de modelo y **explicar** por qué tarda menos de un segundo,
   y **distinguirlo** del rollback de la imagen.
6. **Traducir** una necesidad de infraestructura (registro, cómputo, red, permisos,
   logs) a un servicio de AWS **y** a su equivalente local, y **leer** en la consola qué
   se sigue cobrando cuando nadie manda un request.
7. **Explicar** por qué un secreto en la imagen no se borra con `RUN rm` y por qué la
   barrera de aprobación vive en el Environment de GitHub y no en el YAML.

## Contenidos

| Ruta | Qué hay |
|---|---|
| [`01-el-gate-de-promocion.md`](01-el-gate-de-promocion.md) | La decisión: tres criterios, dos escrituras, tres exit codes. Se corre en vivo |
| [`02-los-tres-workflows.md`](02-los-tres-workflows.md) | La mecánica: `ci.yml`, `cd.yml`, `nightly-smoke.yml`, ambientes y aprobación |
| [`03-de-compose-a-la-nube.md`](03-de-compose-a-la-nube.md) | La traducción local → AWS, IAM en concreto, y el costo con fecha |
| [`04-demo-ecr-fargate/`](04-demo-ecr-fargate/) | La demo del instructor, paso a paso: la imagen con su modelo, ECR, Fargate, y el `teardown.sh` |
| [`taller.md`](taller.md) | Enunciado del taller, con criterios de aceptación medibles |
| [`_contraejemplo-insegure-aws/`](_contraejemplo-insegure-aws/) | Un despliegue que funciona y que no hay que copiar. Material del bloque de seguridad |
| [`_soluciones/`](_soluciones/) | Soluciones de referencia. Solo en el disco del instructor |

Los workflows **no viven aquí**: viven en [`.github/workflows/`](../../.github/workflows/)
y esta sesión los documenta. Un workflow que se copia a una carpeta de sesión deja de ser
el que corre. Lo mismo el gate: es [`scripts/promote.py`](../../scripts/promote.py) y
[`src/taxi/models/evaluate.py`](../../src/taxi/models/evaluate.py), el código del caso
guía.

---

## El recorrido

| # | Se abre | Para qué | ¿Bloquea la terminal? |
|---|---|---|---|
| 1 | sección 1 de este README | desplegar a mano, y automatizar el despliegue de algo peor | no |
| 2 | [`01-el-gate-de-promocion.md`](01-el-gate-de-promocion.md) | las tres preguntas, los cinco pasos, y el gate rechazando y aceptando en vivo | `make mlflow` en una terminal aparte queda corriendo; los comandos del gate terminan en segundos |
| 3 | [`02-los-tres-workflows.md`](02-los-tres-workflows.md) | qué corre en cada workflow, los ambientes, la aprobación y el comentario del PR | no (navegador) |
| 4 | [`_contraejemplo-insegure-aws/`](_contraejemplo-insegure-aws/) | encontrar qué está mal en un despliegue que funciona | no |
| 5 | [`03-de-compose-a-la-nube.md`](03-de-compose-a-la-nube.md) | la traducción local → nube, los dos roles, el secreto que no se borra, el costo | no |
| 6 | [`04-demo-ecr-fargate/README.md`](04-demo-ecr-fargate/README.md) | la demo grabada: ECR, Fargate, la predicción desde una IP pública, y el teardown | los `wait` de AWS bloquean uno a tres minutos, a propósito |
| 7 | [`taller.md`](taller.md) | el entregable, que se aprueba **sin tocar la nube** | — |

**El gate va antes de los workflows.** Un workflow es la mecánica; el gate es la
decisión. Enseñar primero el YAML produce estudiantes que saben automatizar una
promoción que no deberían estar haciendo.

**El teardown cierra la demo, no la clase.** Si se hace el despliegue y no se
destruye, la nube cobra por segundo de existencia hasta que alguien se acuerde.

### Antes de clase

```bash
make data        # las particiones, incluido el holdout del gate
make mlflow      # el registry de la sesión 3, en otra terminal: queda corriendo
uv run python -c "from taxi.models import registry; mv = registry.version_por_alias('nyc-taxi-duration', 'champion'); print('champion ->', mv.version if mv else 'NO HAY: corre taxi train --hpo y taxi promote')"
```

Hace falta un modelo con alias `champion`. Si no lo hay, `uv run taxi train --hpo
--trials 10` seguido de `uv run taxi promote` lo crea (el primer modelo se promueve
solo, porque no hay contra qué compararlo).

---

## 1. El dolor: desplegar a mano, y automatizar el despliegue de algo peor

No se abre ninguna consola de nube en este bloque.

### Acto 1 — Los cinco pasos y las cinco oportunidades de error

El instructor despliega una versión nueva a mano, en vivo, cronómetro a la vista:

```bash
docker build -t mi-api:v2 .                       # 1
docker tag mi-api:v2 registro/mi-api:latest       # 2
docker push registro/mi-api:latest                # 3
# entrar al servidor, actualizar el servicio, reiniciar  # 4
curl -fsS https://.../health                      # 5
```

**Mide el tiempo real en clase.** No hay una cifra en este material a propósito:
depende de la red del salón, del tamaño de la imagen y de si la capa base está en
cache. Lo que importa es que la clase lo vea y lo compare con lo que tarda un `git push`
en el paso 3 del recorrido.

Dónde puede salir mal, en los cinco pasos:

| Paso | Error plausible | Cómo se manifiesta |
|---|---|---|
| 1 | construir con cambios sin comitear | la imagen contiene código que no está en ningún commit |
| 2 | etiquetar la imagen equivocada | se despliega la build anterior, y los logs dicen lo mismo |
| 3 | olvidar el push, o empujar a otro registro | el servidor arranca la imagen vieja sin avisar |
| 4 | actualizar un servicio y no el otro | mitad del tráfico en cada versión |
| 5 | no verificar | el despliegue "terminó" y el servicio está caído |

Y la pregunta que cierra el acto:

> **¿Qué imagen exacta está corriendo ahora en producción, y quién aprobó que
> estuviera ahí?**

Con este procedimiento no hay respuesta. `latest` es un puntero mutable: no dice qué
bytes son. Y no existe registro de la decisión, solo el historial de bash de alguien.

### Acto 2 — El pipeline terminó en verde y promovió un modelo peor

Segundo acto, y es el que da sentido a la sesión.

El atajo tentador, cuando ya tienes un pipeline de entrenamiento que corre solo, es
cerrarlo así, al final de cada corrida:

```python
# El atajo. Usa ademas una API deprecada de MLflow (stages, ver ADR 002).
client.transition_model_version_stage(
    name=model_name,
    version=version,
    stage="Production",
    archive_existing_versions=True,   # y archiva al que estaba sirviendo
)
```

Así se ve en tu propio código: una llamada al final de la función de entrenamiento,
sin un `if` delante. Léelo despacio. Un modelo llega a producción **por el solo hecho de
que el entrenamiento no lanzó excepciones**. Sin holdout, sin comparar con el modelo que
está sirviendo, sin posibilidad de rechazo, y archivando al anterior, que destruye el
camino de vuelta. Si el pipeline corre cada dos minutos, son 720 promociones al día.

Demostración en vivo: registrar un modelo deliberadamente peor y ver que el
entrenamiento termina en verde:

```bash
uv run taxi train --modelo media --registrar
```

**Qué debes ver:** `media: valid_rmse=9.6457` y `Registrado como nyc-taxi-duration v6
con alias @candidate y validation_status=pending`. Un RMSE del doble que el del
champion, y el pipeline verde. Con el atajo de arriba, ese modelo estaría sirviendo
tráfico ahora mismo.

La conclusión que hay que dejar escrita en el tablero:

> **Un pipeline verde significa "el proceso corrió", no "el resultado es bueno".**
> CI/CD automatiza la *ejecución* de una decisión. Si la decisión no está codificada
> en ninguna parte, lo que se automatiza es no decidir.

Lo que falta es un **gate**: un punto donde se comparan candidato y champion sobre un
holdout fijo y el resultado puede ser "no". Es el corazón de la sesión y es el paso
[01](01-el-gate-de-promocion.md).

---

## 2. Autoverificación

Cinco preguntas. Si alguna no se puede responder sin volver al material, ahí está el
vacío.

1. Tu pipeline terminó en verde y desplegó. **¿Qué garantiza eso sobre el modelo que
   está sirviendo?** (La respuesta correcta es incómoda.) ¿Qué tendría que existir para
   que garantizara algo?
2. El gate devuelve exit code 1 en una corrida y 2 en la siguiente. **¿Cuál de las dos
   situaciones es más grave y por qué?** ¿Deben las dos hacer fallar el job?
3. Producción exige aprobación humana y staging no. **¿Por qué la barrera se
   configura en el Environment de GitHub y no con un `if:` en el YAML?** ¿Quién puede
   cambiar cada una de las dos?
4. Desplegaste `mi-api:latest` en staging, lo probaste y lo promoviste a producción.
   Producción falla. **¿Puedes afirmar que corría los mismos bytes que probaste?** Si
   no, ¿qué referencia tendrías que haber usado?
5. Terminaste la demo de nube y corriste el teardown. **¿Con qué comandos demuestras
   que ya no se factura nada?** Nombra los recursos que hay que verificar y cuál de
   ellos cobra por existir aunque nadie le mande un request.

---

## 3. Qué NO usar

Evaluado el **3 de septiembre de 2026**.

| No usar | Usar | Motivo |
|---|---|---|
| `imagen:latest` como referencia de despliegue | `imagen@sha256:…` | un tag es mutable: lo que probaste puede no ser lo que corre |
| Auto-promoción al final del entrenamiento | el gate, con exit code, antes del deploy | "el pipeline terminó" no es "el modelo es mejor" |
| `transition_model_version_stage(..., archive_existing_versions=True)` | `set_registered_model_alias` | API deprecada desde MLflow 2.9.0, y archivar destruye el camino de rollback |
| `AWS_ACCESS_KEY_ID` en la imagen, en el repo o en un `--build-arg` | un rol de IAM que la plataforma asume | una llave de larga vida no expira y acaba en git |
| `RUN rm .env` para "quitar" un secreto de la imagen | que no entre: `.dockerignore`, o `RUN --mount=type=secret` | la capa anterior sigue en la imagen |
| Security group con el puerto abierto a `0.0.0.0/0` en una API sin autenticación | solo la IP que necesita entrar; TLS y autenticación delante | ver el [contraejemplo](_contraejemplo-insegure-aws/) |
| AWS App Runner para un despliegue nuevo | ECS con Fargate (la demo), o ECS Express Mode | **cerrado a clientes nuevos** según su propia documentación. Quien ya lo usa puede seguir; quien empieza no puede crear un servicio |
| `iterative/setup-cml` para comentar métricas en el PR | `actions/github-script` | última release de CML: 0.20.6, octubre de 2024. Una acción sin mantener en el camino crítico del despliegue es deuda con fecha de vencimiento |
| Actions en versiones mayores sobre Node 20 (`actions/checkout@v4` y similares) | las versiones sobre Node 24 (tabla en el paso 02) | GitHub retira Node 20 de los runners el 23 de septiembre de 2026 |
| Interpolar `${{ ... }}` dentro del cuerpo de un script | pasar los valores por `env:` | *script injection*: basta una comilla en el título de un PR para ejecutar código con el token del workflow |
| `cancel-in-progress: true` en el workflow de despliegue | encolar (`false`) | cancelar un deploy a medias deja un rollout parcial |
| Un paso de CI que termina en `\|\| true` o `\|\| echo "..."` | dejar que falle | un pipeline que no puede fallar produce confianza injustificada |
| Dejar la demo de nube "para mañana" | `teardown.sh` y pegar la verificación | una tarea de Fargate y su IP cobran por segundo de existencia |

---

## 4. Referencias

Verificadas el **3 de septiembre de 2026**. Los comandos, los precios y las versiones
cambian; revisa antes de cada cohorte. Las referencias específicas de AWS están al
final del paso [04](04-demo-ecr-fargate/README.md#14-referencias).

- GitHub Actions: [environments y reglas de protección](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) · [seguridad: *script injection*](https://docs.github.com/en/actions/reference/security/secure-use) · [retiro de Node 20 en los runners](https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/) · [`actions/github-script`](https://github.com/actions/github-script)
- Docker: [multi-stage](https://docs.docker.com/build/building/multi-stage/) · [secretos en el build](https://docs.docker.com/build/building/secrets/)
- MLflow: [Model Registry: aliases y tags](https://mlflow.org/docs/latest/ml/model-registry/)
- Decisiones de diseño: [ADR 007 — el gate de promoción](../../docs/adr/007-gate-de-promocion.md) · [ADR 002 — aliases en vez de stages](../../docs/adr/002-aliases-en-vez-de-stages.md)
- *Designing Machine Learning Systems*, Chip Huyen: capítulo de infraestructura y el
  ciclo de despliegue continuo de ML.
