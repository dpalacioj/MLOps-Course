#!/usr/bin/env bash
# =============================================================================
# teardown.sh — destruye todo lo que la demo de la sesión 6 creó en AWS
# =============================================================================
# Por qué esto es parte de la demo y no una nota al pie:
#
#   1. En la nube, la última operación del día decide la factura del mes. Una
#      tarea de Fargate olvidada cobra por segundo de EXISTENCIA, no de uso, y
#      su IP pública también.
#   2. Un equipo que no sabe destruir su infraestructura no crea entornos de
#      prueba; y sin entornos de prueba, prueba en producción.
#   3. AWS Budgets AVISA, no frena. No existe un "corta el gasto en 5 USD".
#      El teardown es el único mecanismo real de control.
#
# Dos propiedades que se le exigen a cualquier teardown, y que este tiene:
#
#   - IDEMPOTENTE: correrlo dos veces no falla. Si el recurso ya no existe, se
#     informa y se sigue. Un teardown que aborta a la mitad deja lo peor: la
#     mitad cara.
#   - VERIFICABLE: termina listando lo que quedó. "Corrí el teardown" no es
#     evidencia; la salida de los `list` sí.
#
# ORDEN DE BORRADO: inverso al de creación, porque hay dependencias.
#   tareas         -> antes que el cluster (un cluster con tareas no se borra)
#   cluster        -> antes que el security group (la tarea tiene una interfaz
#                     de red dentro de ese grupo; hasta que se libera, el grupo
#                     no se puede borrar)
#   task definition-> se DESREGISTRA (no se borra: ECS conserva las revisiones
#                     inactivas para auditoría)
#   log group      -> independiente
#   security group -> con reintentos, porque la interfaz de red tarda en soltarse
#   rol IAM        -> la política se desasocia antes de borrarlo
#   ECR            -> al final, con --force porque tiene imágenes
#
# Uso (desde la raíz del repositorio, con las mismas variables de la demo):
#   DEMO=taxi-demo bash sesiones/s06-cloud-cicd/04-demo-ecr-fargate/teardown.sh --dry-run
#   DEMO=taxi-demo bash sesiones/s06-cloud-cicd/04-demo-ecr-fargate/teardown.sh
#
# Variables:
#   DEMO        prefijo de todos los recursos de la demo   (default: taxi-demo)
#   AWS_REGION  región                                    (default: us-east-1)
#
# NOTA: `set -e` NO se usa a propósito. Cada borrado se evalúa por separado y un
# fallo (por ejemplo, un recurso que ya no existe) no debe impedir los demás.
# =============================================================================
set -uo pipefail

DEMO="${DEMO:-taxi-demo}"
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
    return 1
  fi
}

# --- Comprobaciones previas -------------------------------------------------
titulo "0. Comprobaciones previas"

if ! command -v aws >/dev/null 2>&1; then
  error "no hay 'aws' en el PATH. Instala la AWS CLI v2."
  exit 1
fi

AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text 2>/dev/null)"
if [ -z "$AWS_ACCOUNT_ID" ] || [ "$AWS_ACCOUNT_ID" = "None" ]; then
  error "no se pudo resolver la cuenta. ¿Están configuradas las credenciales? (aws configure)"
  exit 1
fi

CLUSTER="$DEMO"
FAMILIA="$DEMO"
LOG_GROUP="/ecs/${DEMO}"
SG_NOMBRE="${DEMO}-sg"
ROL="${DEMO}-ecs-execution"
POLITICA_EXEC="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
REPO_ECR="mlops-curso/${DEMO}"

echo "  cuenta:   $AWS_ACCOUNT_ID"
echo "  región:   $AWS_REGION"
echo "  prefijo:  $DEMO"
[ "$DRY_RUN" -eq 1 ] && echo "  modo:     DRY-RUN (no se borra nada)" \
                     || echo "  modo:     BORRADO REAL"

# --- 1. Tareas de ECS -------------------------------------------------------
# Primero, porque es lo que está cobrando ahora mismo (cómputo + IP pública), y
# porque un cluster con tareas activas no se puede borrar.
titulo "1. Tareas en el cluster $CLUSTER"

if aws ecs describe-clusters --region "$AWS_REGION" --clusters "$CLUSTER" \
     --query "clusters[?status=='ACTIVE'].clusterName" --output text 2>/dev/null | grep -q .; then
  TAREAS="$(aws ecs list-tasks --region "$AWS_REGION" --cluster "$CLUSTER" \
    --query 'taskArns[]' --output text 2>/dev/null)"
  if [ -n "$TAREAS" ] && [ "$TAREAS" != "None" ]; then
    for tarea in $TAREAS; do
      ejecutar "detener la tarea ${tarea##*/}" \
        aws ecs stop-task --region "$AWS_REGION" --cluster "$CLUSTER" --task "$tarea" \
          --reason "teardown de la demo"
    done
    if [ "$DRY_RUN" -eq 0 ]; then
      info "esperando a que las tareas terminen (libera la interfaz de red)..."
      aws ecs wait tasks-stopped --region "$AWS_REGION" --cluster "$CLUSTER" --tasks $TAREAS 2>/dev/null \
        && ok "tareas detenidas" || error "el wait terminó con aviso; se sigue"
    fi
  else
    salto "no hay tareas corriendo"
  fi

  # --- 2. Cluster -----------------------------------------------------------
  titulo "2. Cluster $CLUSTER"
  ejecutar "borrar el cluster" aws ecs delete-cluster --region "$AWS_REGION" --cluster "$CLUSTER"
else
  salto "no hay cluster '$CLUSTER'"
  titulo "2. Cluster $CLUSTER"
  salto "nada que borrar"
fi

# --- 3. Task definitions ----------------------------------------------------
# ECS no borra revisiones: las DESREGISTRA (quedan INACTIVE, consultables, sin
# poder lanzar tareas nuevas). No cobran. Se desregistran igual para que
# `list-task-definitions` quede vacío y la verificación sea limpia.
titulo "3. Task definitions de la familia $FAMILIA"

REVISIONES="$(aws ecs list-task-definitions --region "$AWS_REGION" \
  --family-prefix "$FAMILIA" --status ACTIVE --query 'taskDefinitionArns[]' --output text 2>/dev/null)"
if [ -n "$REVISIONES" ] && [ "$REVISIONES" != "None" ]; then
  for rev in $REVISIONES; do
    ejecutar "desregistrar ${rev##*/}" \
      aws ecs deregister-task-definition --region "$AWS_REGION" --task-definition "$rev"
  done
else
  salto "no hay revisiones activas de '$FAMILIA'"
fi

# --- 4. CloudWatch Logs -----------------------------------------------------
titulo "4. Log group $LOG_GROUP"

if aws logs describe-log-groups --region "$AWS_REGION" --log-group-name-prefix "$LOG_GROUP" \
     --query "logGroups[?logGroupName=='${LOG_GROUP}'].logGroupName" --output text 2>/dev/null | grep -q .; then
  ejecutar "borrar el log group" aws logs delete-log-group --region "$AWS_REGION" --log-group-name "$LOG_GROUP"
else
  salto "no hay log group '$LOG_GROUP'"
fi

# --- 5. Security group ------------------------------------------------------
# Puede fallar con DependencyViolation mientras la interfaz de red de la tarea
# detenida no se haya liberado del todo. Se reintenta con espera en vez de
# fallar a la primera: es la diferencia entre "no se pudo" y "todavía no".
titulo "5. Security group $SG_NOMBRE"

SG_ID="$(aws ec2 describe-security-groups --region "$AWS_REGION" \
  --filters "Name=group-name,Values=${SG_NOMBRE}" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)"
if [ -n "$SG_ID" ] && [ "$SG_ID" != "None" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    ejecutar "borrar el security group $SG_ID" \
      aws ec2 delete-security-group --region "$AWS_REGION" --group-id "$SG_ID"
  else
    borrado=0
    for intento in 1 2 3 4 5 6; do
      if aws ec2 delete-security-group --region "$AWS_REGION" --group-id "$SG_ID" >/dev/null 2>&1; then
        ok "security group $SG_ID borrado (intento $intento)"
        borrado=1
        break
      fi
      info "todavía tiene una interfaz de red asociada; reintento en 20 s ($intento/6)"
      sleep 20
    done
    [ "$borrado" -eq 0 ] && error "no se pudo borrar $SG_ID. Vuelve a correr el teardown en unos minutos"
  fi
else
  salto "no hay security group '$SG_NOMBRE'"
fi

# --- 6. IAM: rol de ejecución -----------------------------------------------
# Una política gestionada hay que DESASOCIARLA antes de borrar el rol; si no,
# `delete-role` falla con DeleteConflict.
titulo "6. IAM: rol $ROL"

if aws iam get-role --role-name "$ROL" >/dev/null 2>&1; then
  ejecutar "desasociar AmazonECSTaskExecutionRolePolicy" \
    aws iam detach-role-policy --role-name "$ROL" --policy-arn "$POLITICA_EXEC"
  ejecutar "borrar el rol" aws iam delete-role --role-name "$ROL"
else
  salto "no hay rol '$ROL'"
fi

# --- 7. ECR -----------------------------------------------------------------
# --force borra el repositorio aunque contenga imágenes. Sin él, el borrado
# falla con RepositoryNotEmptyException y el almacenamiento sigue cobrando.
titulo "7. ECR: $REPO_ECR"

if aws ecr describe-repositories --region "$AWS_REGION" \
     --repository-names "$REPO_ECR" >/dev/null 2>&1; then
  ejecutar "borrar el repositorio de ECR (con sus imágenes)" \
    aws ecr delete-repository --region "$AWS_REGION" --repository-name "$REPO_ECR" --force
else
  salto "no hay repositorio '$REPO_ECR'"
fi

# --- 8. Verificación --------------------------------------------------------
# Esta es la parte que se pega en el PR. "Corrí el teardown" no es evidencia.
titulo "8. Verificación: qué queda en la cuenta (región $AWS_REGION)"

echo "-- Clusters de ECS ----------------------------------------------------"
aws ecs list-clusters --region "$AWS_REGION" --query 'clusterArns[]' --output table 2>/dev/null || echo "  (sin datos)"

echo "-- Task definitions activas ------------------------------------------"
aws ecs list-task-definitions --region "$AWS_REGION" --status ACTIVE \
  --query 'taskDefinitionArns[]' --output table 2>/dev/null || echo "  (sin datos)"

echo "-- Security groups de la demo ----------------------------------------"
aws ec2 describe-security-groups --region "$AWS_REGION" \
  --filters "Name=group-name,Values=${DEMO}-*" \
  --query 'SecurityGroups[].{Id:GroupId,Nombre:GroupName}' --output table 2>/dev/null || echo "  (sin datos)"

echo "-- Log groups /ecs/ --------------------------------------------------"
aws logs describe-log-groups --region "$AWS_REGION" --log-group-name-prefix /ecs/ \
  --query 'logGroups[].logGroupName' --output table 2>/dev/null || echo "  (sin datos)"

echo "-- Repositorios de ECR -----------------------------------------------"
aws ecr describe-repositories --region "$AWS_REGION" \
  --query 'repositories[].repositoryName' --output table 2>/dev/null || echo "  (sin datos)"

echo "-- Roles IAM de la demo ----------------------------------------------"
aws iam list-roles --query "Roles[?starts_with(RoleName, '${DEMO}')].RoleName" --output table 2>/dev/null || echo "  (sin datos)"

titulo "Fin"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "Fue un DRY-RUN: no se borró nada. Vuelve a correrlo sin --dry-run."
else
  cat <<'TEXTO'
Borrado lanzado. Dos cosas pendientes, y las dos son parte del ejercicio:

  1. Si la sección 5 no pudo borrar el security group, vuelve a correr este
     script en unos minutos: es idempotente y la sección 8 te dirá si quedó algo.
  2. Cost Explorer tarda hasta 24 h en reflejar el uso. MAÑANA revisa que la
     curva de gasto baje a cero. Las fechas se calculan con Python para que el
     comando sea el mismo en macOS, Linux y Windows (`date -d` no existe en BSD):

       aws ce get-cost-and-usage \
         --time-period "$(python3 -c 'import datetime as d; h=d.date.today(); print(f"Start={h-d.timedelta(days=2)},End={h}")')" \
         --granularity DAILY --metrics UnblendedCost \
         --group-by Type=DIMENSION,Key=SERVICE

Pega la salida de la sección 8 en el PR del taller.
TEXTO
fi
