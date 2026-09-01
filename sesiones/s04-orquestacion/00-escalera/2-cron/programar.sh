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
  tiene: el job va a fallar con "Operation not permitted" y el log va a quedar
  con un traceback en vez de la corrida.

  El arreglo, UNA sola vez y antes de clase. Necesita tu contrasena, asi que
  hazlo tu:

    Ajustes del Sistema -> Privacidad y seguridad -> Acceso total al disco
    -> el boton "+" -> Mayus-Cmd-G -> escribe  /usr/sbin/cron  -> Abrir
    -> deja el interruptor encendido

  Comprobacion: instala la demo, espera a que dispare, y si el log dice
  "Operation not permitted", el permiso no quedo puesto.

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
    if [[ -f "$LOG" ]]; then tail -20 "$LOG" | sed 's/^/    /'; else echo "    (el log no existe todavia)"; fi
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
