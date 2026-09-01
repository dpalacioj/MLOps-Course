#!/usr/bin/env bash
# =============================================================================
# Peldano 2 — programar la demo para que corra sola en unos minutos.
# =============================================================================
# Escribir a mano la linea del crontab en clase cuesta cinco minutos, se
# equivoca la ruta y `crontab -e` abre `vi` delante de treinta personas. Este
# script calcula la hora, arma la linea y la instala.
#
#   ./programar.sh              muestra la linea que instalaria (no toca nada)
#   ./programar.sh --instalar   la instala en tu crontab
#   ./programar.sh --ver        que hay instalado y que dice el log
#   ./programar.sh --quitar     la borra
#
# Por defecto son 4 minutos. Se cambia con el primer argumento:
#
#   ./programar.sh 6 --instalar
#
# La entrada queda marcada con un comentario, asi que `--quitar` la encuentra y
# borra solo la suya: no toca el resto de tu crontab.
# =============================================================================

set -euo pipefail

MARCA="escalera-mlops-demo"
CARPETA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ_REPO="$(cd "$CARPETA/../../../.." && pwd)"
LOG="${ESCALERA_LOG:-$HOME/escalera-cron.log}"

MINUTOS=4
ACCION="mostrar"
for arg in "$@"; do
  case "$arg" in
    --instalar) ACCION="instalar" ;;
    --quitar) ACCION="quitar" ;;
    --ver) ACCION="ver" ;;
    [0-9] | [0-9][0-9]) MINUTOS="$arg" ;;
    *)
      echo "Argumento no reconocido: $arg" >&2
      echo "Uso: $0 [minutos] [--instalar | --ver | --quitar]" >&2
      exit 2
      ;;
  esac
done

# `date` no es igual en macOS y en Linux, y este script se usa en las dos.
# BSD (macOS): date -v+4M ; GNU (Linux): date -d '+4 minutes'
if date -v+0M >/dev/null 2>&1; then
  MINUTO=$(date -v+"${MINUTOS}"M "+%M")
  HORA=$(date -v+"${MINUTOS}"M "+%H")
  RELOJ=$(date -v+"${MINUTOS}"M "+%H:%M")
else
  MINUTO=$(date -d "+${MINUTOS} minutes" "+%M")
  HORA=$(date -d "+${MINUTOS} minutes" "+%H")
  RELOJ=$(date -d "+${MINUTOS} minutes" "+%H:%M")
fi

# Sin ceros a la izquierda: cron los acepta, pero "9" se lee mejor que "09" al
# proyectarlo, y evita que alguien crea que es notacion octal.
MINUTO=$((10#$MINUTO))
HORA=$((10#$HORA))
LINEA="$MINUTO $HORA * * * $CARPETA/correr.sh  # $MARCA"

# --- Preflight: los dos motivos por los que esto falla en una Mac ------------
preflight() {
  [[ "$(uname -s)" == "Darwin" ]] || return 0

  case "$RAIZ_REPO" in
    "$HOME"/Documents/* | "$HOME"/Desktop/* | "$HOME"/Downloads/*)
      cat <<AVISO

  AVISO (macOS): el repositorio esta en una carpeta protegida por el sistema.

    $RAIZ_REPO

  Documents, Desktop y Downloads estan bajo TCC. Tu terminal ya tiene permiso
  (por eso ./correr.sh funciona a mano), pero el proceso de cron es otro y no lo
  tiene: el job falla con "Operation not permitted" y NO se crea ningun log,
  porque el redirect vive dentro de correr.sh y el script no llega a ejecutarse.
  El error se va al correo local, que es donde nadie mira. Desde tu silla el
  sintoma es que no pasa nada.

  Dos arreglos. UNA sola vez, y antes de clase:

  A) Mover el repositorio fuera de esas tres carpetas. No pide contrasena ni
     toca permisos del sistema:

       mv "$RAIZ_REPO" ~/dev/$(basename "$RAIZ_REPO")

  B) Dar Acceso total al disco a cron. Necesita tu contrasena, asi que hazlo tu:

       Ajustes del Sistema -> Privacidad y seguridad -> Acceso total al disco
       -> el boton "+" -> Mayus-Cmd-G -> escribe  /usr/sbin/cron  -> Abrir
       -> deja el interruptor encendido

     Y despues reinicia cron, o el permiso no se aplica al proceso que ya
     estaba corriendo:

       sudo pkill -x cron

  Comprobacion (es la unica que vale, el permiso no se ve): programa uno a dos
  minutos, espera a que dispare, y pregunta con:

       $0 --ver

  Los pasos completos, con las teclas exactas, estan en el README de esta
  carpeta.

AVISO
      ;;
  esac

  if ! pgrep -qf "/usr/sbin/cron"; then
    cat <<AVISO
  Nota: el proceso de cron no esta corriendo ahora mismo. En macOS es normal
  cuando no hay ningun crontab: launchd lo arranca solo en cuanto instalas el
  primero. Se comprueba despues de --instalar con:

    pgrep -lf /usr/sbin/cron

AVISO
  fi
}

leer_crontab() { crontab -l 2>/dev/null || true; }

case "$ACCION" in
  mostrar)
    preflight
    cat <<RESUMEN
  La linea que se instalaria (dispara una vez, hoy a las $RELOJ):

    $LINEA

  Instalala con:

    $0 $MINUTOS --instalar

RESUMEN
    ;;

  instalar)
    preflight
    # Se reemplaza cualquier demo anterior en vez de acumularlas: al tercer
    # ensayo tendrias tres entradas disparando a horas distintas.
    { leer_crontab | grep -v "$MARCA" || true; echo "$LINEA"; } | crontab -
    cat <<INSTALADO
  Instalado. Hoy a las $RELOJ, cron ejecuta el pipeline sin nadie delante.

    $LINEA

  Mientras esperas, deja esto corriendo en la otra terminal:

    tail -f "$LOG"

  Si a esa hora NO aparece nada en el log, no significa que cron no disparara:
  significa que el comando murio antes de llegar al log. Preguntale a:

    $0 --ver

  Y cuando termine la demo, BORRALA. La entrada dispara todos los dias a la
  misma hora hasta que la quites:

    $0 --quitar

INSTALADO
    ;;

  ver)
    echo "  Entradas de la demo en tu crontab:"
    if leer_crontab | grep "$MARCA"; then :; else echo "    (ninguna)"; fi
    echo
    echo "  Ultimas lineas de $LOG:"
    if [[ -f "$LOG" ]]; then
      tail -20 "$LOG" | sed 's/^/    /'
    else
      echo "    (el log no existe)"
    fi

    # Si el job murio ANTES de entrar a correr.sh, el redirect a $LOG nunca llego
    # a aplicarse y el error se fue al correo local, que es donde nadie mira.
    # Es el caso tipico de "Operation not permitted" en macOS: cron disparo, pero
    # no pudo ni ejecutar el script. Sin esto, el sintoma es "no paso nada".
    BUZON="/var/mail/$USER"
    if [[ -r "$BUZON" ]] && grep -q "$MARCA" "$BUZON" 2>/dev/null; then
      echo
      echo "  AVISO: hay correo de cron sobre esta demo en $BUZON."
      echo "  Cron disparo pero el comando fallo antes de escribir el log:"
      echo
      # El cuerpo del correo va DESPUES de las cabeceras, no pegado al Subject:
      # se filtran las cabeceras y las lineas vacias, y queda el error de verdad.
      # El `|| true` es necesario porque con `set -e` un grep sin coincidencias
      # mataria el script justo cuando mas hace falta que hable.
      grep -vE '^(From|Return-Path|X-|Delivered-To|Received|To:|Subject:|Message-Id|Date:|[[:space:]])' \
        "$BUZON" 2>/dev/null | grep -v '^$' | tail -3 | sed 's/^/    /' || true
      echo
      if [[ "$(uname -s)" == "Darwin" ]] && grep -q "Operation not permitted" "$BUZON" 2>/dev/null; then
        echo "  \"Operation not permitted\" = falta el Acceso total al disco para"
        echo "  /usr/sbin/cron. Es el aviso del preflight de este script. El permiso"
        echo "  hay que darlo ANTES de que dispare: cron no reintenta."
        echo
      fi
      echo "  Para vaciar el buzon cuando lo hayas leido:  : > \"$BUZON\""
    fi
    ;;

  quitar)
    if ! leer_crontab | grep -q "$MARCA"; then
      echo "  No habia ninguna entrada de la demo. Nada que borrar."
      exit 0
    fi
    leer_crontab | grep -v "$MARCA" | crontab -
    echo "  Entrada de la demo borrada. El resto de tu crontab quedo intacto:"
    leer_crontab | sed 's/^/    /'
    ;;
esac
