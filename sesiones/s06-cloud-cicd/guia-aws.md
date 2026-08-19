# Laboratorio opcional: desplegar la API en AWS

> **Este laboratorio es opcional y nada evaluable depende de él.** El taller de la
> sesión se aprueba con Docker Compose. Lo que se aprende aquí es a traducir cuatro
> necesidades de infraestructura a cuatro servicios gestionados, a aplicar privilegio
> mínimo y a **destruir lo que creaste**.

**Antes de empezar, lee esto:**

- La **demo la hace el instructor** sobre la cuenta del curso, con una grabación de
  respaldo por si la consola falla en vivo.
- Si lo haces tú, es con el **IAM user de tu equipo** y la política mínima de
  [`scripts/politica-iam-minima.json`](scripts/politica-iam-minima.json).
- **El presupuesto de 10 USD tiene que estar creado antes** (§0). Un presupuesto avisa,
  no frena: no existe un "corta el gasto" en AWS.
- **`teardown.sh` es obligatorio al terminar** (§7). No es opcional, es parte del
  ejercicio.
- Ninguna credencial se escribe en un archivo de este repositorio. `gitleaks` corre en
  cada PR y escanea el historial completo.

**Verificado el 19 de agosto de 2026** contra la documentación oficial de la AWS CLI v2
(enlaces al final de cada sección). Los nombres de servicio y los parámetros cambian:
**revisa los enlaces antes de cada cohorte** y no des por bueno un comando de este
archivo sin la doc al lado. Donde no se pudo confirmar algo, está dicho
explícitamente.

---

## 0. Preparación (instructor, antes de la clase)

### Variables de la sesión

Todos los comandos de esta guía usan estas variables. Ponlas en la terminal, no en un
archivo del repositorio:

```bash
export AWS_REGION="us-east-1"
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export EQUIPO="equipo01"                      # cámbialo por el de tu equipo
export REPO_ECR="mlops-curso/api-${EQUIPO}"
export SERVICIO="taxi-api-${EQUIPO}"
export REGISTRO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

aws sts get-caller-identity            # ¿con qué identidad estoy operando?
```

`aws sts get-caller-identity` es el primer comando de cualquier sesión de AWS. Operar
sin saber con qué identidad estás es la causa más común de "creé el recurso y no lo
encuentro": estaba en otra cuenta o en otra región.

### El presupuesto de 10 USD

```bash
aws budgets create-budget \
  --account-id "$AWS_ACCOUNT_ID" \
  --budget file://sesiones/s06-cloud-cicd/scripts/presupuesto.json \
  --notifications-with-subscribers file://sesiones/s06-cloud-cicd/scripts/presupuesto-notificaciones.json

aws budgets describe-budgets --account-id "$AWS_ACCOUNT_ID" \
  --query 'Budgets[].{Nombre:BudgetName,Limite:BudgetLimit.Amount}'
```

Antes de ejecutarlo, **edita el correo** en
[`scripts/presupuesto-notificaciones.json`](scripts/presupuesto-notificaciones.json): el
archivo trae un marcador, no una dirección real.

Las notificaciones están en 50%, 80% y 100% del presupuesto, y el umbral del 100% es
`FORECASTED` además de `ACTUAL`: avisa cuando la *proyección* del mes supera los 10 USD,
que es cuando todavía se puede hacer algo.

Doc: [`create-budget` con la CLI](https://docs.aws.amazon.com/code-library/latest/ug/budgets_example_budgets_CreateBudget_section.html)

---

## 1. Los cuatro recursos y para qué son

| Paso | Servicio | Necesidad | Equivalente local |
|---|---|---|---|
| §3 | **ECR** | guardar la imagen | registry local |
| §4 | **App Runner** | ejecutar el contenedor y darle una URL | `docker compose` |
| §5 | **S3** | artifact store de MLflow | MinIO |
| §6 | **RDS Postgres** | backend store de MLflow | Postgres en Compose |

Puedes hacer solo §3 y §4 (la API con un modelo que se resuelve del MLflow local o que
arranca degradado). §5 y §6 son el stack de MLflow gestionado y son los que cuestan
dinero de verdad.

**Orden de creación y de destrucción son inversos.** Si esto suena obvio, mira el
[`teardown.sh`](scripts/teardown.sh): borra App Runner antes que ECR porque un servicio
en marcha mantiene una referencia a la imagen.

---

## 2. El IAM user del equipo

Lo crea el instructor, uno por equipo. La política mínima está en
[`scripts/politica-iam-minima.json`](scripts/politica-iam-minima.json) y hay que
sustituir los marcadores `<ACCOUNT_ID>`, `<REGION>` y `<EQUIPO>` antes de aplicarla.

```bash
# 1. Rellenar los marcadores de la plantilla (no se comitea el resultado)
sed -e "s/<ACCOUNT_ID>/${AWS_ACCOUNT_ID}/g" \
    -e "s/<REGION>/${AWS_REGION}/g" \
    -e "s/<EQUIPO>/${EQUIPO}/g" \
    sesiones/s06-cloud-cicd/scripts/politica-iam-minima.json > /tmp/politica-${EQUIPO}.json

# 2. Crear la política y el usuario
aws iam create-policy \
  --policy-name "mlops-curso-${EQUIPO}" \
  --policy-document "file:///tmp/politica-${EQUIPO}.json"

aws iam create-user --user-name "mlops-${EQUIPO}"

aws iam attach-user-policy \
  --user-name "mlops-${EQUIPO}" \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/mlops-curso-${EQUIPO}"
```

### Qué dice la política, statement por statement

El archivo JSON **no lleva comentarios**: IAM rechaza un documento de política con
claves que no reconoce, así que la explicación vive aquí y los `Sid` son el puente.
Léelos en paralelo.

| `Sid` | Qué permite | Por qué así |
|---|---|---|
| `EcrTokenDeAutenticacion` | `ecr:GetAuthorizationToken` sobre `*` | es una acción **de cuenta**: la API no admite recurso. El `*` es obligado, no descuido |
| `EcrSoloElRepositorioDelEquipo` | push y pull, **solo** en `mlops-curso/api-<EQUIPO>` | sin `ecr:DeleteRepository`: el teardown lo corre el instructor, y un equipo no debe poder borrar el repositorio de otro por un error de tipeo |
| `AppRunnerSoloElServicioDelEquipo` | crear, actualizar, describir, pausar y borrar `taxi-api-<EQUIPO>/*` | el comodín final del ARN cubre el id que App Runner asigna al servicio |
| `AppRunnerListarNoAdmiteRecurso` | `apprunner:ListServices` sobre `*` | otra acción de cuenta. **Compromiso aceptado:** el equipo puede *ver* los nombres de los servicios de los demás. No puede tocarlos, porque el statement anterior acota las acciones que modifican |
| `PasarSoloElRolDeAccesoAEcr` | `iam:PassRole`, restringido al ARN del rol del equipo **y** con `iam:PassedToService = build.apprunner.amazonaws.com` | **es el permiso más peligroso de la política.** `PassRole` sin restringir permite escalar privilegios: quien pueda pasar un rol de administrador a un servicio que ejecuta código, es administrador |
| `S3SoloElBucketDelEquipo` | leer y escribir en el bucket del equipo | **dos ARNs, no uno**: el bucket (para `ListBucket`) y `bucket/*` (para los objetos). Confundirlos es el error más común de las políticas de S3: `ListBucket` funciona y `GetObject` falla |
| `LeerElCostoEsParteDelAprendizaje` | Cost Explorer y Budgets, solo lectura | si el equipo no puede ver lo que gasta, el ejercicio de costo de la §4 del README no se puede hacer |
| `SaberConQueIdentidadEstoyOperando` | `sts:GetCallerIdentity` | primer comando de cualquier sesión de AWS |
| `DenyEscaladoDePrivilegiosYRecursosCaros` | **niega** `ec2:*`, `organizations:*`, `rds:Create/DeleteDBInstance` y las acciones de IAM que permiten escalar | un `Deny` explícito, y no la simple ausencia de `Allow`, porque **un `Deny` gana frente a cualquier `Allow`**: sigue valiendo si alguien adjunta otra política por error, que es justo el escenario contra el que protege. `iam:PassRole` **no** está en la lista, a propósito: negarlo anularía el `Allow` acotado de arriba y App Runner no podría crearse |

Ejercicio de dos minutos que vale más que la tabla: quita el `Condition` del statement
de `PassRole`, piensa qué se vuelve posible, y vuelve a ponerlo.

### Sobre las llaves de acceso

Para usar la CLI, el equipo necesita credenciales. Las opciones, en orden de
preferencia:

1. **IAM Identity Center (SSO)** con `aws sso login`. Credenciales temporales, sin
   llaves de larga vida. **Es lo correcto** y es lo que debería usar una organización.
2. **Access key del IAM user**, con MFA obligatorio y rotación al terminar el curso.
   Es lo práctico para un laboratorio de una tarde.

Si se usa (2):

```bash
aws iam create-access-key --user-name "mlops-${EQUIPO}"
```

**La salida contiene el secreto y solo se muestra una vez.** Reglas no negociables: se
configura con `aws configure --profile mlops-<equipo>`, **nunca** se pega en un archivo
del repositorio, **nunca** en una variable dentro de un `Dockerfile`, y se borra al
cerrar el laboratorio (el `teardown.sh` lo hace).

Por qué insistir: una llave de IAM user **no expira**. Una que se filtra sigue siendo
válida hasta que alguien la revoca, y quien la encuentre en un repositorio público
tendrá los permisos de esa política. Es la razón por la que la política es mínima.

Doc: [IAM y App Runner](https://docs.aws.amazon.com/apprunner/latest/dg/security_iam_service-with-iam.html)

---

## 3. ECR: el registro de imágenes

### Crear el repositorio

```bash
aws ecr create-repository \
  --repository-name "$REPO_ECR" \
  --region "$AWS_REGION" \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true
```

Las dos banderas son la lección del paso:

- **`--image-tag-mutability IMMUTABLE`.** Impide sobrescribir un tag existente. Es el
  refuerzo, a nivel de registro, de lo que la sesión 5 explicó: un tag que se puede
  repuntar significa que lo que probaste puede no ser lo que corre. Con `IMMUTABLE`, un
  `push` a un tag ya usado **falla** en lugar de reescribir la historia. Valores
  posibles: `MUTABLE`, `IMMUTABLE`, `IMMUTABLE_WITH_EXCLUSION`,
  `MUTABLE_WITH_EXCLUSION`.
- **`scanOnPush=true`.** Escaneo de vulnerabilidades del sistema operativo y de las
  dependencias en cada push. No detecta problemas de tu código; sí detecta que la base
  `python:3.11-slim` que llevas seis meses sin actualizar acumuló CVEs.

### Autenticarse y publicar

```bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$REGISTRO"
```

El usuario es literalmente `AWS` y el token vale **12 horas**. Nótese que la contraseña
entra por `--password-stdin`: pasarla como argumento la dejaría en el historial del
shell y en la lista de procesos.

```bash
# Se construye desde la raíz del repositorio
docker build -t "${REGISTRO}/${REPO_ECR}:v1" .
docker push "${REGISTRO}/${REPO_ECR}:v1"
```

### El digest, que es lo que vas a desplegar

```bash
DIGEST="$(aws ecr describe-images \
  --repository-name "$REPO_ECR" \
  --image-ids imageTag=v1 \
  --query 'imageDetails[0].imageDigest' --output text)"

export IMAGEN_URI="${REGISTRO}/${REPO_ECR}@${DIGEST}"
echo "$IMAGEN_URI"
```

Ese string —con `@sha256:…`, no con `:v1`— es la unidad de despliegue. Es exactamente lo
que produce el job `imagen` de [`cd.yml`](../../.github/workflows/cd.yml) como salida.

Docs: [`create-repository`](https://docs.aws.amazon.com/cli/latest/reference/ecr/create-repository.html)
· [autenticación del registro](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html)

---

## 4. App Runner: ejecutar el contenedor

### 4.1 El rol de acceso a ECR

App Runner necesita un rol para **leer** la imagen de un ECR privado. No hace falta para
ECR Public.

```bash
# Trust policy: quién puede asumir el rol. El principal para el access role de ECR es
# build.apprunner.amazonaws.com (confirmado en la doc de IAM de App Runner).
cat > /tmp/trust-apprunner.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "build.apprunner.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

aws iam create-role \
  --role-name "AppRunnerECRAccess-${EQUIPO}" \
  --assume-role-policy-document file:///tmp/trust-apprunner.json

aws iam attach-role-policy \
  --role-name "AppRunnerECRAccess-${EQUIPO}" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"

export ROL_ECR_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/AppRunnerECRAccess-${EQUIPO}"
```

La política gestionada `AWSAppRunnerServicePolicyForECRAccess` concede exactamente
cinco acciones de lectura: `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage`,
`ecr:DescribeImages`, `ecr:GetAuthorizationToken` y
`ecr:BatchCheckLayerAvailability`. Ninguna de escritura. **Ábrela y léela**: es el
ejemplo más limpio de privilegio mínimo que vas a ver en la sesión.

> Alternativa si algo de esto falla: crear el rol desde la consola al crear el
> servicio. La consola lo genera correctamente y evita el paso manual. Se muestra el
> camino de la CLI porque es el que se automatiza.

Docs: [política `AWSAppRunnerServicePolicyForECRAccess`](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AWSAppRunnerServicePolicyForECRAccess.html)
· [cómo App Runner trabaja con IAM](https://docs.aws.amazon.com/apprunner/latest/dg/security_iam_service-with-iam.html)

### 4.2 Crear el servicio

```bash
cat > /tmp/source-config.json <<JSON
{
  "ImageRepository": {
    "ImageIdentifier": "${IMAGEN_URI}",
    "ImageRepositoryType": "ECR",
    "ImageConfiguration": {
      "Port": "8000",
      "RuntimeEnvironmentVariables": {
        "TAXI_MODELO_URI": "ninguno",
        "TAXI_LOG_LEVEL": "INFO"
      }
    }
  },
  "AutoDeploymentsEnabled": false,
  "AuthenticationConfiguration": {
    "AccessRoleArn": "${ROL_ECR_ARN}"
  }
}
JSON

aws apprunner create-service \
  --service-name "$SERVICIO" \
  --region "$AWS_REGION" \
  --source-configuration "file:///tmp/source-config.json" \
  --instance-configuration Cpu="1 vCPU",Memory="2 GB" \
  --health-check-configuration Protocol=HTTP,Path=/health,Interval=10,Timeout=5,HealthyThreshold=1,UnhealthyThreshold=5
```

Cada parte, y por qué:

| Parámetro | Valor | Por qué |
|---|---|---|
| `ImageIdentifier` | `…@sha256:…` | **el digest**, no un tag. El patrón de la API acepta las dos formas; se usa la inmutable |
| `Port` | `8000` | el `EXPOSE` del `Dockerfile`. Si no coinciden, el servicio nunca pasa el health check |
| `TAXI_MODELO_URI` | `ninguno` | primer despliegue **sin modelo**: la API arranca degradada, `/health` responde 200 y así se verifica la plataforma antes de meter MLflow en la ecuación |
| `AutoDeploymentsEnabled` | `false` | con un digest no tendría sentido: el digest no cambia. Con auto-deploy y un tag, App Runner redespliega solo cuando el tag se repunta — cómodo, y exactamente el comportamiento que la sesión 5 argumenta que **no** se quiere en producción |
| `AccessRoleArn` | el rol de §4.1 | obligatorio para ECR privado |
| `Cpu` / `Memory` | `1 vCPU` / `2 GB` | valores válidos: CPU `0.25\|0.5\|1\|2\|4 vCPU`; memoria `0.5\|1\|2\|3\|4\|6\|8\|10\|12 GB` |
| `Path=/health` | | **el default de App Runner es `Protocol=TCP` y `Path=/`.** Con TCP basta que el puerto acepte conexiones: un proceso vivo que devuelve 500 en todo pasaría el check. Ponerlo en HTTP contra `/health` es la diferencia entre "el puerto está abierto" y "el servicio funciona" |

El `Interval` acepta 1-20 s y el `Timeout` 1-20 s; los defaults son 5 y 2.

### 4.3 Verificar

```bash
export SERVICIO_ARN="$(aws apprunner list-services \
  --query "ServiceSummaryList[?ServiceName=='${SERVICIO}'].ServiceArn" --output text)"

# Esperar a que quede RUNNING (la creación tarda varios minutos; mídelo)
aws apprunner describe-service --service-arn "$SERVICIO_ARN" \
  --query 'Service.{Estado:Status,Url:ServiceUrl}'

export URL="https://$(aws apprunner describe-service --service-arn "$SERVICIO_ARN" \
  --query 'Service.ServiceUrl' --output text)"

curl -fsS "$URL/health" | jq
curl -fsS "$URL/docs" -o /dev/null -w 'docs: %{http_code}\n'
```

App Runner sirve **HTTPS con un certificado gestionado** en su dominio, sin que hayas
configurado nada. Es una de las cosas por las que valía la pena: montar TLS a mano en una
EC2 —lo que hacía el [contraejemplo](_contraejemplo-insegure-aws/), que directamente no
lo montaba— es media hora de trabajo y una fuente permanente de errores.

Si el servicio no llega a `RUNNING`:

```bash
aws apprunner list-operations --service-arn "$SERVICIO_ARN" \
  --query 'OperationSummaryList[0].{Tipo:Type,Estado:Status,Fin:EndedAt}'
```

Las tres causas frecuentes: el `Port` no coincide con el del contenedor, el rol de ECR
no está bien (revisa la política adjunta), o el contenedor muere al arrancar (los logs
están en CloudWatch, grupo `/aws/apprunner/<servicio>/<id>/application`).

### 4.4 Desplegar una versión nueva

```bash
docker build -t "${REGISTRO}/${REPO_ECR}:v2" .
docker push "${REGISTRO}/${REPO_ECR}:v2"

DIGEST_V2="$(aws ecr describe-images --repository-name "$REPO_ECR" \
  --image-ids imageTag=v2 --query 'imageDetails[0].imageDigest' --output text)"

# El mismo archivo de configuración, con el digest nuevo
sed -i.bak "s|@sha256:[a-f0-9]*|@${DIGEST_V2}|" /tmp/source-config.json

aws apprunner update-service \
  --service-arn "$SERVICIO_ARN" \
  --source-configuration "file:///tmp/source-config.json"
```

**El rollback es este mismo comando con el digest anterior.** Esa simetría es el punto:
desplegar y revertir son la misma operación con distinto argumento, igual que promover y
revertir un modelo son `asignar_alias` con distinta versión.

Docs: [`create-service`](https://docs.aws.amazon.com/cli/latest/reference/apprunner/create-service.html)
· [crear un servicio](https://docs.aws.amazon.com/apprunner/latest/dg/manage-create.html)
· [servicio desde una imagen](https://docs.aws.amazon.com/apprunner/latest/dg/service-source-image.html)

---

## 5. S3: el artifact store de MLflow

```bash
export BUCKET="mlops-curso-${EQUIPO}-artifacts-${AWS_ACCOUNT_ID}"

# us-east-1 es el único caso sin LocationConstraint. En cualquier otra región es
# obligatorio, y omitirlo crea el bucket donde no querías o falla.
if [ "$AWS_REGION" = "us-east-1" ]; then
  aws s3api create-bucket --bucket "$BUCKET" --region "$AWS_REGION"
else
  aws s3api create-bucket --bucket "$BUCKET" --region "$AWS_REGION" \
    --create-bucket-configuration "LocationConstraint=${AWS_REGION}"
fi

# Bloquear todo acceso público. Es el default desde 2023, y se declara explícito
# igual: un artifact store con modelos no tiene ninguna razón para ser público.
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Cifrado en reposo con claves gestionadas por S3
aws s3api put-bucket-encryption --bucket "$BUCKET" \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Y aquí está el punto de la sesión, en dos líneas:

```bash
# --- Contra MinIO, en local (es lo que hace docker-compose.yml) ---
mlflow server \
  --artifacts-destination "s3://mlflow/" \
  --serve-artifacts ...
# más, en el entorno del servidor:
#   MLFLOW_S3_ENDPOINT_URL=http://minio:9000
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY  (las de MinIO)

# --- Contra AWS ---
mlflow server \
  --artifacts-destination "s3://${BUCKET}/mlflow" \
  --serve-artifacts ...
# y en el entorno del servidor se BORRA MLFLOW_S3_ENDPOINT_URL (el default es el
# de AWS) y las credenciales las provee el rol de la instancia, no dos variables.
```

**El código de MLflow no cambia. Ni una línea.** MinIO implementa el protocolo S3, así que
boto3 habla con los dos: lo único que se mueve es el destino y el endpoint. Compáralo con
el servicio `mlflow` de [`docker-compose.yml`](../../docker-compose.yml), donde está
exactamente el mismo `--artifacts-destination` apuntando al bucket local.

Ese es el motivo por el que el taller es local y este laboratorio es opcional: lo que se
ejercita en Compose es el mismo camino de código que correría en AWS.

Doc: [`s3api create-bucket`](https://docs.aws.amazon.com/cli/latest/reference/s3api/create-bucket.html)

---

## 6. RDS Postgres: el backend store de MLflow

> **Este es el paso que cuesta dinero.** Una instancia RDS cobra por **hora de
> existencia**, con tráfico o sin él, más el almacenamiento y los backups. Es la causa
> número uno de facturas inesperadas en cursos de nube. Si tienes dudas, sáltalo: MLflow
> funciona con SQLite para el laboratorio.

```bash
export DB_ID="mlflow-${EQUIPO}"

aws rds create-db-instance \
  --db-instance-identifier "$DB_ID" \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --allocated-storage 20 \
  --master-username mlflow \
  --manage-master-user-password \
  --no-publicly-accessible \
  --backup-retention-period 0 \
  --no-multi-az \
  --region "$AWS_REGION"
```

Los parámetros que son decisiones, no relleno:

| Parámetro | Por qué |
|---|---|
| `--manage-master-user-password` | AWS genera la contraseña y **la guarda en Secrets Manager**. No pasa por tu terminal, ni por tu historial, ni por este repositorio. Es incompatible con `--master-user-password`, a propósito |
| `--no-publicly-accessible` | la base **no** se expone a internet. El default depende de si hay `DBSubnetGroup`, así que se declara explícito en lugar de confiar en él |
| `--backup-retention-period 0` | desactiva los backups automáticos. Correcto para un laboratorio desechable, **incorrecto para cualquier cosa real** |
| `--no-multi-az` | una sola zona: la mitad del costo y ninguna alta disponibilidad. Mismo criterio |

Para leer la contraseña cuando MLflow la necesite:

```bash
SECRETO_ARN="$(aws rds describe-db-instances --db-instance-identifier "$DB_ID" \
  --query 'DBInstances[0].MasterUserSecret.SecretArn' --output text)"

# No imprimas esto en la proyección de la clase.
aws secretsmanager get-secret-value --secret-id "$SECRETO_ARN" \
  --query SecretString --output text
```

**Cómo llega el secreto al contenedor.** App Runner soporta
`RuntimeEnvironmentSecrets` en la `ImageConfiguration`: se le pasa el ARN del secreto y
la plataforma lo inyecta como variable de entorno en el arranque, con el **instance
role** (principal `tasks.apprunner.amazonaws.com`) autorizado a leerlo. El secreto no
entra a la imagen ni al repositorio.

> **No verificado en esta guía:** no se ejecutó el flujo completo de
> `RuntimeEnvironmentSecrets` con RDS gestionado, ni la configuración de red necesaria
> para que App Runner alcance una RDS privada (requiere un *VPC connector*, que es un
> recurso adicional con su propio costo). Si haces este paso, **verifica los dos** en la
> documentación antes de la clase. Para el laboratorio de una tarde, la ruta corta es
> dejar la API con `TAXI_MODELO_URI=ninguno` y MLflow en local.

Docs: [`create-db-instance`](https://docs.aws.amazon.com/cli/latest/reference/rds/create-db-instance.html)
· [`delete-db-instance`](https://docs.aws.amazon.com/cli/latest/reference/rds/delete-db-instance.html)

---

## 7. Teardown: obligatorio

```bash
bash sesiones/s06-cloud-cicd/scripts/teardown.sh --dry-run   # qué borraría
bash sesiones/s06-cloud-cicd/scripts/teardown.sh             # borrarlo
```

El script borra en el orden inverso al de creación (dependencias primero), es
**idempotente** y termina listando lo que quedó. Lee sus comentarios: cada `delete`
explica por qué va en esa posición.

### La verificación es el criterio de aceptación

No basta con haber corrido el script:

```bash
aws apprunner list-services --query 'ServiceSummaryList[].ServiceName'
aws ecr describe-repositories --query 'repositories[].repositoryName'
aws rds describe-db-instances --query 'DBInstances[].DBInstanceIdentifier'
aws s3 ls
aws iam list-access-keys --user-name "mlops-${EQUIPO}" --query 'AccessKeyMetadata[].AccessKeyId'
```

Las cinco salidas sin ninguno de los recursos del laboratorio. **Pega esa salida en el
PR del taller.**

Y al día siguiente, la verificación que de verdad cierra el ciclo:

```bash
# Cost Explorer tarda hasta 24 h en reflejar el uso. Mira que la curva baje a cero.
aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d '2 days ago' +%F),End=$(date -u +%F) \
  --granularity DAILY --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --query 'ResultsByTime[].{Fecha:TimePeriod.Start,Grupos:Groups[].{Servicio:Keys[0],Costo:Metrics.UnblendedCost.Amount}}'
```

---

## 8. Errores frecuentes

| Síntoma | Causa habitual |
|---|---|
| `denied: Your authorization token has expired` | el token de ECR dura 12 h; repite `get-login-password` |
| `tag invalid` al hacer push | el repositorio es `IMMUTABLE` y el tag ya existe. Usa otro tag: es la protección funcionando |
| App Runner se queda en `OPERATION_IN_PROGRESS` y falla | el `Port` no coincide con el del contenedor, o el health check apunta a una ruta que no existe |
| `AccessDenied` al crear el servicio | falta la política adjunta al rol de ECR, o el `AccessRoleArn` está mal |
| El bucket se creó en `us-east-1` "sin querer" | faltó `--create-bucket-configuration LocationConstraint=...` |
| `InvalidParameterCombination` en RDS | se pasaron `--master-user-password` y `--manage-master-user-password` juntos: son mutuamente excluyentes |
| `delete-db-instance` falla | la instancia tiene *deletion protection* activada; hay que desactivarla primero |
| El servicio "no cuesta" porque está pausado | `pause-service` reduce el cómputo a cero, pero el servicio **sigue existiendo**. El teardown lo borra |

---

## 9. Lo que este laboratorio no cubre

Dicho explícitamente, para que nadie crea que esto es un despliegue de producción:

- **Sin dominio propio ni certificado propio.** Se usa el dominio de App Runner.
- **Sin VPC diseñada.** Se usan los defaults de la cuenta. Un despliegue real define
  subredes privadas y un *VPC connector* para que la API alcance la RDS.
- **Sin autenticación en la API.** Está abierta en su URL de App Runner mientras el
  laboratorio dure. Es la razón por la que el teardown es obligatorio y por la que la
  API no sirve datos sensibles.
- **Sin infraestructura como código.** Todo con comandos, para que se vea qué se crea.
  El siguiente paso real es Terraform o CDK: la diferencia no es la comodidad, es que
  el estado de la infraestructura pasa a estar versionado y revisable en un PR — y el
  teardown pasa a ser `terraform destroy`.
- **Sin despliegue progresivo.** `update-service` reemplaza la versión. Canary y
  blue/green necesitan otra capa.
