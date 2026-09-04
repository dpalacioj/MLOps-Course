# 03 — De Compose a la nube: la misma imagen, otra plataforma

> Paso 3 de 4 del recorrido. Aquí no se ejecuta nada: se lee. Es la traducción que
> hace que el paso 04 (la demo en AWS) no sea un tutorial de AWS sino la misma idea de
> la sesión 5 con otra plataforma debajo.

**La idea en una frase.** En la sesión 5 el contenedor pasó a ser el contrato: una
imagen con código y dependencias, identificada por su digest, que arranca igual en
cualquier máquina que sepa ejecutar contenedores. La nube es una de esas máquinas. Lo
que cambia al ir a la nube no es el código ni la imagen: es **quién ejecuta el
contenedor, dónde se guarda la imagen, y quién paga la cuenta**.

---

## 1. Lo que la nube resuelve, y su equivalente local

Las columnas de la izquierda son **necesidades**; las de la derecha, implementaciones.
Esta tabla es la que hace la sesión transferible a cualquier proveedor.

| Necesidad | En tu máquina (Compose, sesión 5) | En AWS (esta sesión) | Por qué el código no cambia |
|---|---|---|---|
| Guardar la imagen | la imagen construida en el host | **ECR** (Elastic Container Registry) | `docker push` habla el mismo protocolo con los dos |
| Ejecutar el contenedor | `docker compose up` | **ECS con Fargate** | el contenedor es el contrato; la plataforma solo lo ejecuta |
| Darle una dirección | `-p 8000:8000` en localhost | una IP pública en la interfaz de red de la tarea | la app escucha en `0.0.0.0:8000` en los dos casos |
| Decidir qué entra | nada: solo tú llegas a localhost | un **security group** (reglas de puerto y origen) | la app no sabe ni le importa |
| Artifact store de MLflow | **MinIO** | **S3** | MinIO habla el protocolo S3: cambia una variable de entorno, no el código |
| Backend store de MLflow | Postgres en Compose | **RDS Postgres** | misma cadena `postgresql://`, distinto host |
| Secretos | `.env` fuera de git | **Secrets Manager**, inyectado como variable de entorno | el código lee variables de entorno en los dos casos |
| Logs | `docker logs` | **CloudWatch Logs** | la app escribe a stdout; quien lo recoge es la plataforma |
| Métricas | Prometheus + Grafana (sesión 7) | CloudWatch, o Prometheus gestionado | el endpoint `/metrics` es el mismo |

La demo del paso 04 hace las **primeras cuatro filas y la de logs**. Las de MLflow
(S3, RDS, secretos) se explican aquí y no se ejecutan, por una razón de costo que la
sección 5 pone en números: montar un MLflow gestionado en la nube cuesta más que toda
la demo junta y no enseña nada que MinIO y Postgres en Compose no enseñen ya.

### MinIO habla S3: el puente entre las dos columnas

Es la pieza que hace que el taller sea local sin perder nada conceptual. Compara el
servicio `mlflow` de [`docker-compose.yml`](../../docker-compose.yml) con lo que sería
en AWS:

```bash
# --- Contra MinIO, en local (lo que hace docker-compose.yml) ---
mlflow server --artifacts-destination "s3://mlflow/" ...
# y en el entorno del servidor:
#   MLFLOW_S3_ENDPOINT_URL=http://minio:9000
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY   (las de MinIO)

# --- Contra AWS ---
mlflow server --artifacts-destination "s3://mi-bucket/mlflow" ...
# y en el entorno del servidor se BORRA MLFLOW_S3_ENDPOINT_URL (el default es el
# de AWS) y las credenciales las da el rol de la tarea, no dos variables.
```

**El código de MLflow no cambia. Ni una línea.** Lo único que se mueve es el destino y
el endpoint. Ese es el motivo de ser de las interfaces estándar: el proveedor pasa a ser
configuración de despliegue en lugar de una decisión de arquitectura.

---

## 2. Por qué ECS con Fargate, y no otra cosa

**Qué es cada palabra.** *ECS* (Elastic Container Service) es el orquestador de
contenedores de AWS: recibe una descripción de "cómo correr esta imagen" (la *task
definition*) y la ejecuta. *Fargate* es el modo en que ECS ejecuta sin que tú
administres servidores: pides "1 vCPU y 2 GB" y AWS pone la máquina, la parchea y la
retira cuando la tarea termina. La alternativa es que ECS use instancias EC2 tuyas, y
eso agrega todo lo que Fargate te quita.

**Criterio de la elección: cuánta ceremonia hay entre "tengo una imagen" y "hay una URL
que responde", y si el servicio acepta cuentas nuevas.** Evaluado el **3 de septiembre
de 2026** contra la documentación oficial de cada servicio.

| Opción | Qué hay que crear antes de tener una URL | Por qué no es la de la demo |
|---|---|---|
| **ECS con Fargate, una tarea** (la demo) | repositorio, rol de ejecución, log group, security group, cluster, task definition, tarea | es la que se usa: cada pieza es una fila de la tabla de la sección 1 y se ve entera |
| AWS App Runner | el servicio y un rol | **cerrado a clientes nuevos.** Su documentación dice hoy: *"AWS App Runner is no longer open to new customers"*. Quien ya lo usaba puede seguir; quien abre una cuenta hoy no puede crear un servicio. Era la opción más simple y por eso hay que decir por qué ya no está |
| ECS Express Mode | dos roles y una llamada; AWS crea el servicio, el balanceador, el autoescalado y la red | es el reemplazo que AWS recomienda para App Runner. No se usa aquí por dos razones: crea un **balanceador** que cobra por hora exista o no tráfico, y esconde exactamente las piezas que esta sesión quiere que veas |
| ECS con Fargate, un *service* con balanceador | todo lo de la demo más target group, balanceador, listener y certificado | es el paso siguiente real: da HTTPS, dominio propio y despliegue sin corte. Se nombra, no se hace |
| Lambda con imagen de contenedor | rol, función, URL de función | cobra por invocación (casi gratis para una demo), pero hay que meter un adaptador en la imagen y el arranque en frío de un proceso que importa MLflow y XGBoost es de varios segundos en cada primera petición. Para modelos de ML es el caso que **no** se recomienda |
| EKS (Kubernetes) | todo lo anterior más el clúster de Kubernetes | solo si la organización ya vive en Kubernetes |

La demo elige la primera fila **por pedagogía, no por superioridad técnica**: en
producción, la respuesta es la cuarta fila o Express Mode. La traducción es directa,
porque **la unidad sigue siendo la imagen referenciada por digest**.

### GCP y Azure, para quien trabaje ahí

| Necesidad | AWS | GCP | Azure |
|---|---|---|---|
| Registro de imágenes | ECR | Artifact Registry | Azure Container Registry |
| Cómputo del contenedor | ECS con Fargate | Cloud Run | Container Apps |
| Artifact store | S3 | Cloud Storage | Blob Storage |
| Backend store | RDS Postgres | Cloud SQL | Azure Database for PostgreSQL |
| Secretos | Secrets Manager | Secret Manager | Key Vault |

La fila de cómputo es la que importa: **Cloud Run y Container Apps hacen en una llamada
lo que en AWS hoy exige Express Mode o armar el service a mano.** Si el ejercicio se
hace en GCP, cambian los comandos y no cambia ni una idea.

---

## 3. Dos formas de llevar el modelo al servicio

Esta es la decisión que la demo toma distinto que la sesión 5, y hay que entenderla
antes de hacerla.

| | Resolver del registry al arrancar (Compose, sesión 5) | Empaquetar el modelo en la imagen (demo, paso 04) |
|---|---|---|
| Qué exige en runtime | un MLflow alcanzable desde el contenedor | nada |
| Cambiar de modelo | mover el alias y reiniciar el proceso | reconstruir la imagen y redesplegar |
| Qué identifica lo que corre | digest de la imagen **y** versión del registry | solo el digest de la imagen (la versión va como etiqueta de la imagen) |
| Rollback del modelo | mover el alias, menos de un segundo | redesplegar el digest anterior, minutos |
| `/modelo` responde | `model_version: "7"` | `model_version: "desconocida"`, y la API lo avisa en el log |
| Cuándo conviene | hay un registry en la misma red que el servicio | no hay red privada hacia el registry, serverless, borde, demos |

Lo que la sesión 5 rechaza **no es** empaquetar el modelo: es copiar a mano el
directorio de un run concreto (`shutil.copytree`, un `run_id` fijo escrito en el
código, sin saber qué versión es ni de dónde salió). En la demo, el modelo se exporta
del registry **por alias** con un comando de MLflow, y la versión que ese alias
resolvía queda escrita como etiqueta de la imagen. Se pierde la resolución en runtime;
se conserva el linaje.

Por qué la demo lo hace así y no monta un MLflow en AWS: para que el contenedor en
Fargate pueda pedirle el modelo a un registry, ese registry tiene que existir en la
nube (una base de datos RDS, un bucket S3, un servicio para el tracking server) y ser
alcanzable desde la tarea por red privada. Son cuatro recursos más, cada uno con su
costo por hora de existencia, para demostrar algo que Compose ya demuestra. La sección
5 pone los números.

---

## 4. IAM y secretos: privilegio mínimo, en concreto

IAM (Identity and Access Management) es el sistema de permisos de AWS. Todo lo que
hace una llamada a la API de AWS lo hace **como alguien**: un usuario, o un *rol* que un
servicio asume temporalmente. La regla es dar a cada identidad lo mínimo que necesita.

### Los tres principios, con su falla asociada

| Principio | Qué significa en la demo | Qué pasa si se ignora |
|---|---|---|
| **Privilegio mínimo** | el rol que ECS usa para arrancar la tarea puede *leer* imágenes de ECR y *escribir* logs, y nada más | una credencial filtrada da acceso a toda la cuenta en lugar de a un repositorio |
| **Identidad, no llaves** | la tarea asume un **rol**; no lleva `AWS_ACCESS_KEY_ID` dentro | una llave de larga vida no expira y suele acabar en un repositorio |
| **Los secretos son referencias** | si la app necesitara un secreto, la task definition apuntaría al ARN en Secrets Manager y ECS lo inyectaría al arrancar | un secreto en la imagen es público en cuanto la imagen lo es |

### Los dos roles de una tarea de ECS, y por qué la demo solo usa uno

| Rol | Quién lo usa | Para qué | En la demo |
|---|---|---|---|
| **Rol de ejecución** (*execution role*) | el agente de ECS y Fargate, **no tu código** | bajar la imagen de ECR, escribir en CloudWatch Logs, leer secretos para inyectarlos | se crea, con la política gestionada `AmazonECSTaskExecutionRolePolicy` |
| **Rol de tarea** (*task role*) | tu aplicación, desde dentro del contenedor | llamar a APIs de AWS (leer de S3, escribir en DynamoDB...) | **no se crea**: la API no llama a ninguna API de AWS. Privilegio mínimo es también no dar un rol cuando no hace falta ninguno |

La política gestionada del rol de ejecución es el ejemplo más limpio de privilegio
mínimo que vas a ver en la sesión: cinco acciones de lectura sobre ECR y dos de
escritura sobre logs. Ábrela en la consola de IAM y léela.

El permiso más peligroso de IAM, y hay que nombrarlo aunque la demo no lo ejercite:
`iam:PassRole`. Es el permiso de "entregarle un rol a un servicio". Quien pueda pasar
un rol de administrador a un servicio que ejecuta código, es administrador. Por eso, en
una cuenta compartida, `PassRole` se restringe a roles concretos y a servicios
concretos con una condición `iam:PassedToService`.

### Sobre las credenciales con las que TÚ operas la CLI

En orden de preferencia:

1. **IAM Identity Center** (`aws sso login`): credenciales temporales, sin llaves de
   larga vida. Es lo correcto para una organización.
2. **Un usuario IAM con MFA** y `aws configure`: lo práctico para una cuenta personal
   de laboratorio. La llave se borra al terminar el curso.
3. **Nunca el usuario root** para la CLI. Root no se puede acotar con políticas.

Reglas no negociables, sea cual sea la opción: la llave **nunca** se pega en un archivo
del repositorio, **nunca** en una variable dentro de un `Dockerfile`, **nunca** se
proyecta en clase. `gitleaks` corre en cada PR y escanea el historial completo, pero
es la última línea de defensa, no la primera.

### Un secreto en la imagen no se borra

Merece su propio párrafo porque es contraintuitivo:

```dockerfile
COPY .env .            # capa N: el secreto entra
RUN rm .env            # capa N+1: el secreto "se borra"
```

**El secreto sigue ahí.** Una imagen es una pila de capas inmutables; la capa N existe
y cualquiera con la imagen puede extraerla (`docker history` muestra las capas;
`docker save` las exporta). Lo mismo con `--build-arg` para pasar un token: queda en
los metadatos de la imagen.

Las tres defensas, en orden de preferencia: (1) el secreto **no entra** al contexto de
build, que es el trabajo del [`.dockerignore`](../../.dockerignore); (2) si hace falta
un secreto *durante* el build, `RUN --mount=type=secret` de BuildKit, que no deja capa;
(3) en runtime, variables de entorno inyectadas por la plataforma desde Secrets
Manager.

Y la regla operativa que cierra el tema: **un secreto que llegó a un repositorio remoto
está comprometido y hay que rotarlo.** Borrar el commit es cosmética: el secreto sigue
en el historial, en los forks y en las copias clonadas.

---

## 5. El costo se lee, no se supone

Un ingeniero de ML que no sabe qué cuesta lo que despliega toma malas decisiones de
arquitectura con total confianza. Los números de esta sección se leyeron en las páginas
de precios de AWS para la región `us-east-1` el **3 de septiembre de 2026**; envejecen,
y por eso la demo pide leerlos otra vez en la consola.

| Recurso | Cobra por | Precio leído | Lo que cuesta la demo |
|---|---|---|---|
| Fargate, tarea de 1 vCPU y 2 GB, ARM | segundo de existencia (mínimo 1 minuto) | 0,0324 USD/vCPU-hora + 0,00356 USD/GB-hora | **0,040 USD/hora** |
| Fargate, la misma tarea, x86 | igual | 0,0405 USD/vCPU-hora + 0,00444 USD/GB-hora | 0,049 USD/hora |
| IP pública IPv4 | hora en uso | 0,005 USD/hora | 0,005 USD/hora |
| ECR, almacenamiento | GB-mes del tamaño **comprimido** | 0,10 USD/GB-mes; 500 MB gratis los primeros 12 meses de la cuenta | centavos al mes |
| CloudWatch Logs | GB ingerido | centavos para los logs de una demo | despreciable |
| ECS (cluster, task definitions) | nada | 0 | 0 |
| **Total de la demo corriendo** | | | **≈ 0,045 USD/hora ≈ 33 USD/mes si se olvida** |

Las tres cosas que hay que sacar de la tabla:

- **La pregunta clave es qué se sigue cobrando si nadie manda un request.** La tarea de
  Fargate y su IP: sí, por segundo de existencia. El repositorio de ECR: sí, por
  almacenamiento. Por eso el teardown borra la tarea y el repositorio en lugar de
  dejarlos "por si acaso".
- **La demo cuesta centavos; olvidarla cuesta decenas de dólares.** Dos horas de demo
  son menos de 0,10 USD. Un mes olvidada, 33 USD. El costo no está en usar la nube:
  está en no apagarla.
- **Lo que la demo NO monta es lo caro.** Una base RDS `db.t3.micro` cobra por hora de
  existencia más almacenamiento y backups; un balanceador cobra por hora exista o no
  tráfico. Son los recursos que convierten un laboratorio olvidado en la factura
  inesperada clásica de los cursos de nube. No están en la demo a propósito.

### El presupuesto avisa, no frena

Antes de crear cualquier recurso, un presupuesto en la consola: **Billing and Cost
Management → Budgets → Create budget**, plantilla *Monthly cost budget*, 5 USD, tu
correo. Tarda un minuto.

Detalle que hay que decir en clase: **un presupuesto avisa, no frena.** No existe un
"corta el gasto en 5 USD" en AWS. Por eso el teardown es obligatorio y no se delega al
presupuesto.

Y la verificación que cierra el ciclo, al día siguiente: **Cost Explorer**, agrupado
por servicio. Tarda hasta 24 horas en reflejar el uso. Si la curva no baja a cero,
algo quedó vivo.

---

## 6. Qué NO cubre esta sesión, dicho explícitamente

Para que nadie confunda la demo con un despliegue de producción:

- **Sin HTTPS ni dominio propio.** La demo responde en `http://IP:8000`. TLS necesita un
  balanceador con certificado, que es el paso siguiente y otro recurso con costo.
- **Sin autenticación en la API.** Está abierta a quien llegue a la IP, y por eso el
  security group solo deja entrar a **tu** dirección IP. Es la razón por la que el
  teardown es obligatorio y por la que la API no sirve datos sensibles.
- **Sin red diseñada.** Se usa la VPC por defecto de la cuenta. Un despliegue real
  define subredes privadas y el contenedor no tiene IP pública.
- **Sin infraestructura como código.** Todo con comandos, para que se vea qué se crea.
  El siguiente paso real es Terraform o CDK: la diferencia no es la comodidad, es que
  el estado de la infraestructura pasa a estar versionado y revisable en un PR, y el
  teardown pasa a ser `terraform destroy`.
- **Sin despliegue progresivo.** Una tarea se detiene y otra se lanza. Canary y
  blue/green necesitan un *service* con balanceador.

**Siguiente paso:** [`04-demo-ecr-fargate/README.md`](04-demo-ecr-fargate/README.md),
la demo paso a paso, con el teardown al final.
