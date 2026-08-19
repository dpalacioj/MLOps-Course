#!/usr/bin/env bash
# =============================================================================
# teardown.sh — destruye todo lo que el laboratorio de la sesión 6 creó en AWS
# =============================================================================
# Por qué esto es parte del ejercicio y no una nota al pie:
#
#   1. En la nube, la última operación del día decide la factura del mes. Una
#      instancia RDS olvidada cobra por hora de EXISTENCIA, no de uso.
#   2. Un equipo que no sabe destruir su infraestructura no crea entornos de
#      prueba; y sin entornos de prueba, prueba en producción.
#   3. AWS Budgets AVISA, no frena. No existe un "corta el gasto en 10 USD".
#      El teardown es el único mecanismo real de control.
#
# Dos propiedades que se le exigen a cualquier teardown, y que este tiene:
#
#   - IDEMPOTENTE: correrlo dos veces no falla. Si el recurso ya no existe, se
#     informa y se sigue. Un teardown que aborta a la mitad deja lo peor: la
#     mitad caro.
#   - VERIFICABLE: termina listando lo que quedó. "Corrí el teardown" no es
#     evidencia; la salida de los `list` sí.
#
# ORDEN DE BORRADO: inverso al de creación, porque hay dependencias.
#   App Runner  -> antes que ECR (el servicio referencia la imagen)
#   RDS         -> antes que el secreto de Secrets Manager
#   S3          -> vaciar antes de borrar (un bucket con objetos no se borra)
#   IAM         -> las políticas se desasocian antes de borrarse
#
# Uso (desde la raíz del repositorio):
#   EQUIPO=equipo01 bash sesiones/s06-cloud-cicd/scripts/teardown.sh --dry-run
#   EQUIPO=equipo01 bash sesiones/s06-cloud-cicd/scripts/teardown.sh
#
# Variables:
#   EQUIPO      sufijo de los recursos del equipo   (obligatoria)
#   AWS_REGION  región                              (default: us-east-1)
#   BUCKET      nombre exacto del bucket S3         (opcional; si falta, se deduce)
#
# NOTA: `set -e` NO se usa a propósito. Cada borrado se evalúa por separado y un
# fallo (por ejemplo, un recurso que ya no existe) no debe impedir los demás.
# =============================================================================
set -uo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

SEP="========================================================================"
titulo() { printf '\n%s\n%s\n%s\n' "$SEP" "$1" "$SEP"; }
info()   { printf '  ..    %s\n' "$1"; }
ok()     { printf '  OK    %s\n' "$1"; }
salto()  { printf '  --    %s\n' "$1"; }
error()  { printf '  ERR   %s\n' "$1"; }

# ejecutar <descripción> <comando...>
# En --dry-run imprime el comando y no lo ejecuta. Es la diferencia entre un
# script que se puede revisar antes de correr y uno que hay que creer.
ejecutar() {
  local descripcion="$1"; shift
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  DRY   %s\n        %s\n' "$descripcion" "$*"
    return 0
  fi
  info "$descripcion"
  if "$@" >/dev/null 2>&1; then
    ok "$descripcion"
  else
    error "$descripcion (revísalo a mano; puede que ya no existiera)"
  fi
}

# --- Comprobaciones previas -------------------------------------------------
titulo "0. Comprobaciones previas"

if ! command -v aws >/dev/null 2>&1; then
  error "no hay 'aws' en el PATH. Instala la AWS CLI v2."
  exit 1
fi

if [ -z "${EQUIPO:-}" ]; then
  error "falta la variable EQUIPO. Ejemplo:  EQUIPO=equipo01 bash $0 --dry-run"
  exit 1
fi

AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text 2>/dev/null)"
if [ -z "$AWS_ACCOUNT_ID" ] || [ "$AWS_ACCOUNT_ID" = "None" ]; then
  error "no se pudo resolver la cuenta. ¿Están configuradas las credenciales?"
  exit 1
fi

SERVICIO="taxi-api-${EQUIPO}"
REPO_ECR="mlops-curso/api-${EQUIPO}"
DB_ID="mlflow-${EQUIPO}"
USUARIO="mlops-${EQUIPO}"
ROL_ECR="AppRunnerECRAccess-${EQUIPO}"
POLITICA_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/mlops-curso-${EQUIPO}"
BUCKET="${BUCKET:-mlops-curso-${EQUIPO}-artifacts-${AWS_ACCOUNT_ID}}"

echo "  cuenta:   $AWS_ACCOUNT_ID"
echo "  región:   $AWS_REGION"
echo "  equipo:   $EQUIPO"
[ "$DRY_RUN" -eq 1 ] && echo "  modo:     DRY-RUN (no se borra nada)" \
                     || echo "  modo:     BORRADO REAL"

# --- 1. App Runner ----------------------------------------------------------
# Primero, porque un servicio en marcha mantiene una referencia a la imagen de
# ECR y porque es lo que está cobrando memoria provisionada ahora mismo.
titulo "1. App Runner: $SERVICIO"

SERVICIO_ARN="$(aws apprunner list-services --region "$AWS_REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICIO}'].ServiceArn" \
  --output text 2>/dev/null)"

if [ -n "$SERVICIO_ARN" ] && [ "$SERVICIO_ARN" != "None" ]; then
  # Se BORRA, no se pausa. `pause-service` reduce el cómputo a cero pero el
  # servicio sigue existiendo, y el objetivo es dejar la cuenta como estaba.
  ejecutar "borrar el servicio de App Runner" \
    aws apprunner delete-service --region "$AWS_REGION" --service-arn "$SERVICIO_ARN"
  if [ "$DRY_RUN" -eq 0 ]; then
    info "el borrado es asíncrono: puede tardar unos minutos en desaparecer"
  fi
else
  salto "no hay servicio '$SERVICIO'"
fi

# --- 2. ECR -----------------------------------------------------------------
# --force borra el repositorio aunque contenga imágenes. Sin él, el borrado
# falla y el repositorio queda (el almacenamiento de ECR también se cobra).
titulo "2. ECR: $REPO_ECR"

if aws ecr describe-repositories --region "$AWS_REGION" \
     --repository-names "$REPO_ECR" >/dev/null 2>&1; then
  ejecutar "borrar el repositorio de ECR (con sus imágenes)" \
    aws ecr delete-repository --region "$AWS_REGION" \
      --repository-name "$REPO_ECR" --force
else
  salto "no hay repositorio '$REPO_ECR'"
fi

# --- 3. RDS -----------------------------------------------------------------
# El paso que de verdad importa para la factura.
#
# --skip-final-snapshot: sin él, AWS crea un snapshot final que SE COBRA por
#   almacenamiento indefinidamente. Correcto para un laboratorio desechable;
#   NUNCA para una base con datos que importan.
# --delete-automated-backups: los backups automáticos también ocupan y cobran.
titulo "3. RDS: $DB_ID"

if aws rds describe-db-instances --region "$AWS_REGION" \
     --db-instance-identifier "$DB_ID" >/dev/null 2>&1; then
  # La protección contra borrado hace fallar el delete. Se desactiva primero,
  # porque si no el mensaje de error es poco claro y la instancia sigue cobrando.
  ejecutar "desactivar deletion protection" \
    aws rds modify-db-instance --region "$AWS_REGION" \
      --db-instance-identifier "$DB_ID" --no-deletion-protection --apply-immediately
  ejecutar "borrar la instancia RDS (sin snapshot final)" \
    aws rds delete-db-instance --region "$AWS_REGION" \
      --db-instance-identifier "$DB_ID" \
      --skip-final-snapshot --delete-automated-backups
  if [ "$DRY_RUN" -eq 0 ]; then
    info "el borrado tarda varios minutos; verifica al final con describe-db-instances"
  fi
else
  salto "no hay instancia '$DB_ID'"
fi

# --- 4. S3 ------------------------------------------------------------------
# Vaciar antes de borrar: un bucket con objetos no se puede eliminar. Si el
# bucket tuviera versionado, harían falta también las versiones y los delete
# markers; aquí no se activó versionado a propósito, para que el teardown sea
# de una línea.
titulo "4. S3: $BUCKET"

if aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  ejecutar "vaciar el bucket" aws s3 rm "s3://${BUCKET}" --recursive
  ejecutar "borrar el bucket"  aws s3api delete-bucket --bucket "$BUCKET" --region "$AWS_REGION"
else
  salto "no hay bucket '$BUCKET' (o no hay permiso para verlo)"
fi

# --- 5. IAM: rol de acceso a ECR -------------------------------------------
# Una política gestionada hay que DESASOCIARLA antes de borrar el rol; si no,
# `delete-role` falla con DeleteConflict.
titulo "5. IAM: rol $ROL_ECR"

if aws iam get-role --role-name "$ROL_ECR" >/dev/null 2>&1; then
  ejecutar "desasociar AWSAppRunnerServicePolicyForECRAccess" \
    aws iam detach-role-policy --role-name "$ROL_ECR" \
      --policy-arn "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
  ejecutar "borrar el rol" aws iam delete-role --role-name "$ROL_ECR"
else
  salto "no hay rol '$ROL_ECR'"
fi

# --- 6. IAM: usuario del equipo y sus llaves -------------------------------
# Las access keys se borran SIEMPRE, aunque el usuario se conserve para la
# siguiente sesión: una llave de IAM user no expira nunca por su cuenta.
titulo "6. IAM: usuario $USUARIO"

if aws iam get-user --user-name "$USUARIO" >/dev/null 2>&1; then
  LLAVES="$(aws iam list-access-keys --user-name "$USUARIO" \
    --query 'AccessKeyMetadata[].AccessKeyId' --output text 2>/dev/null)"
  if [ -n "$LLAVES" ] && [ "$LLAVES" != "None" ]; then
    for llave in $LLAVES; do
      ejecutar "borrar la access key ${llave:0:6}..." \
        aws iam delete-access-key --user-name "$USUARIO" --access-key-id "$llave"
    done
  else
    salto "el usuario no tiene access keys"
  fi

  ejecutar "desasociar la política del equipo" \
    aws iam detach-user-policy --user-name "$USUARIO" --policy-arn "$POLITICA_ARN"
  ejecutar "borrar el usuario" aws iam delete-user --user-name "$USUARIO"
  ejecutar "borrar la política del equipo" \
    aws iam delete-policy --policy-arn "$POLITICA_ARN"
else
  salto "no hay usuario '$USUARIO'"
fi

# --- 7. Verificación --------------------------------------------------------
# Esta es la parte que se pega en el PR. "Corrí el teardown" no es evidencia.
titulo "7. Verificación: qué queda en la cuenta"

echo "-- App Runner --------------------------------------------------------"
aws apprunner list-services --region "$AWS_REGION" \
  --query 'ServiceSummaryList[].{Nombre:ServiceName,Estado:Status}' \
  --output table 2>/dev/null || echo "  (sin datos)"

echo "-- ECR ---------------------------------------------------------------"
aws ecr describe-repositories --region "$AWS_REGION" \
  --query 'repositories[].repositoryName' --output table 2>/dev/null || echo "  (sin datos)"

echo "-- RDS ---------------------------------------------------------------"
aws rds describe-db-instances --region "$AWS_REGION" \
  --query 'DBInstances[].{Id:DBInstanceIdentifier,Estado:DBInstanceStatus}' \
  --output table 2>/dev/null || echo "  (sin datos)"

echo "-- S3 ----------------------------------------------------------------"
aws s3 ls 2>/dev/null || echo "  (sin datos)"

echo "-- Secretos gestionados por RDS (deben desaparecer con la instancia) --"
aws secretsmanager list-secrets --region "$AWS_REGION" \
  --query "SecretList[?contains(Name, 'rds')].Name" --output table 2>/dev/null || echo "  (sin datos)"

titulo "Fin"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "Fue un DRY-RUN: no se borró nada. Vuelve a correrlo sin --dry-run."
else
  cat <<'TEXTO'
Borrado lanzado. Dos cosas pendientes, y las dos son parte del ejercicio:

  1. App Runner y RDS borran de forma ASÍNCRONA. Vuelve a correr este script en
     unos minutos: es idempotente y la sección 7 te dirá si quedó algo.
  2. Cost Explorer tarda hasta 24 h en reflejar el uso. MAÑANA revisa que la
     curva de gasto baje a cero:

       aws ce get-cost-and-usage \
         --time-period Start=$(date -u -d '2 days ago' +%F),End=$(date -u +%F) \
         --granularity DAILY --metrics UnblendedCost \
         --group-by Type=DIMENSION,Key=SERVICE

Pega la salida de la sección 7 en el PR del taller.
TEXTO
fi
