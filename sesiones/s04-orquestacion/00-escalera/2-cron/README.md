# Peldaño 2 — CRON: "ejecuta código a cierta hora"

> Es el Acto 3 del bloque "El dolor", pero ejecutable: *"hay que reentrenar cada
> lunes a las 3 a.m. ¿Quién se levanta?"* La primera respuesta de casi todo el
> mundo es `cron`, y es una buena respuesta. Este peldaño la lleva hasta el final
> para ver dónde se acaba.

El script del peldaño 1 **no cambia una sola línea**. Lo que aparece es todo lo
que hay que construir alrededor para que se ejecute sin nadie delante.

| Archivo | Qué es |
|---|---|
| [`programar.sh`](programar.sh) | calcula la hora, arma la línea con tu ruta y la instala. Es lo único que se toca en clase |
| [`correr.sh`](correr.sh) | el envoltorio: PATH, directorio de trabajo y log. Sin él, la línea de crontab falla |
| [`crontab.txt`](crontab.txt) | plantilla de referencia, con las cinco columnas y las tres frecuencias explicadas |

> **Desde dónde se corren los comandos de este README:** desde esta carpeta
> (`.../00-escalera/2-cron/`). Los dos scripts resuelven su propia ubicación, así
> que también funcionan por ruta completa desde la raíz del repositorio; lo que
> no funciona es mezclar las dos formas.

---

## Antes de clase, si estás en macOS (una sola vez)

**Si el repositorio está en `~/Documents`, `~/Desktop` o `~/Downloads`, la demo
falla sin este paso.** Esas tres carpetas están protegidas por TCC. Tu terminal ya
tiene permiso —por eso `./correr.sh` funciona a mano— pero el proceso de cron es
otro y no lo tiene: el job muere con `Operation not permitted` y el log queda con
un traceback en vez de la corrida.

El arreglo pide tu contraseña, así que hazlo tú:

> Ajustes del Sistema → Privacidad y seguridad → **Acceso total al disco** → el
> botón `+` → `Mayús-Cmd-G` → escribe `/usr/sbin/cron` → Abrir → deja el
> interruptor encendido.

`programar.sh` detecta el caso y te lo recuerda solo. Para saber en qué carpeta
estás:

```bash
pwd
```

En Linux no hace falta nada de esto. En Windows no hay `cron`: el equivalente es
el Programador de tareas, y la parte conceptual de este peldaño aplica igual.

---

## La demo, en tres comandos

### 1. Probarlo a mano primero

```bash
./correr.sh && tail -20 "$HOME/escalera-cron.log"
```

Debe aparecer el bloque con la fecha, las tres líneas de los pasos y `estado: OK`.
Si esto no funciona a mano, tampoco va a funcionar a las 3 a.m.

### 2. Programarlo para dentro de cuatro minutos

```bash
./programar.sh --instalar
```

Imprime la hora exacta a la que va a disparar y la línea que instaló. Sin
`--instalar` solo la muestra y no toca nada, que es lo que conviene para
proyectarla y leer las cinco columnas antes de instalarla.

El número de minutos es el primer argumento, si cuatro no encajan con el ritmo de
la clase:

```bash
./programar.sh 6 --instalar
```

### 3. Dejar el log a la vista y seguir hablando

```bash
tail -f "$HOME/escalera-cron.log"
```

Esos cuatro minutos son para explicar la tabla de abajo. Cuando llegue la hora, el
bloque aparece solo en pantalla, sin que nadie toque el teclado. Ese es el
argumento entero del peldaño, y es más convincente visto que dicho.

### Y al terminar, borrarla

```bash
./programar.sh --quitar
```

**No es opcional.** Un crontab no tiene disparo único: esa línea vuelve a
disparar mañana a la misma hora, y al día siguiente. Un cron que nadie recuerda
haber instalado es una de las formas más comunes de dejar una máquina haciendo
trabajo inútil durante meses.

Para ver en cualquier momento qué hay instalado y qué dice el log:

```bash
./programar.sh --ver
```

---

## Qué se rompe, y por qué

Los **seis primeros** son de configuración: se arreglan una vez y no vuelven.
Los **cinco últimos** no se arreglan con configuración — son el límite del
peldaño.

| # | Síntoma | Causa | Arreglo |
|---|---|---|---|
| 1 | `uv: command not found` en el log | cron arranca con un PATH mínimo y no lee tu `~/.bashrc` ni tu `~/.zshrc` | exportar el PATH en el envoltorio (línea 2 de `correr.sh`) o poner `PATH=` en el crontab |
| 2 | error de proyecto no encontrado | el directorio de trabajo de cron es tu `HOME`, no el del repositorio | `cd` a la raíz del repo en el envoltorio (línea 3) |
| 3 | `Operation not permitted` (macOS) | el repo está en una carpeta protegida por TCC y el proceso de cron no tiene Acceso total al disco | la sección de arriba; es lo primero que hay que verificar |
| 4 | no aparece nada en ningún sitio | cron manda stdout y stderr al **correo local** del usuario, que en una máquina de desarrollo nadie lee y a veces ni existe | redirigir a un archivo (`>>"$LOG" 2>&1`) |
| 5 | corre a una hora que no es la esperada | cron usa la zona horaria de la máquina; un servidor suele estar en UTC | fijar `CRON_TZ=America/Bogota` en el crontab, o razonar en UTC a propósito |
| 6 | dos corridas se pisan | si una corrida tarda más que el intervalo, cron lanza otra encima sin preguntar | un lock: `flock -n /tmp/escalera.lock ./correr.sh` |
| 7 | **falló a las 3 a.m. y nadie se enteró** | cron no tiene noción de aviso | escribirlo a mano: enviar a Slack, y no repetir el mismo aviso cien veces |
| 8 | **falló por un timeout de dos segundos y se perdió la corrida entera** | cron no reintenta | escribirlo a mano, con backoff, y decidir qué errores merecen reintento y cuáles no |
| 9 | **"¿esto ya corrió bien alguna vez?"** | `crontab -l` dice cuándo *debería* correr, no qué pasó | escribirlo a mano: una base de datos de corridas con su estado, su duración y sus logs |
| 10 | **"córrelo otra vez pero con 2024-01 en vez de 2024-02"** | la línea del crontab es fija; no hay parámetros por corrida | escribirlo a mano: argumentos, y una forma de lanzarlo fuera de horario |
| 11 | **"el paso 3 falló; ¿hay que repetir los pasos 1 y 2?"** | cron ejecuta *un comando*, no conoce los pasos de adentro | escribirlo a mano: estado por paso, y saltarse los que ya terminaron |

Los cinco últimos tienen la misma columna de arreglo: **escribirlo a mano**. Se
puede, y hay gente que lo hace bien. Un orquestador es, en buena medida, esos
cinco arreglos ya escritos, probados y con una interfaz para mirarlos.

## Cuándo `cron` es la respuesta correcta

Esto no es un espantapájaros. `cron` lleva cuarenta años funcionando y sigue
siendo la herramienta adecuada cuando se cumplen las cuatro condiciones:

1. **Un solo paso.** No hay nada intermedio que valga la pena conservar si falla.
2. **Idempotente y barato.** Volver a correrlo completo no cuesta nada ni duplica
   efectos.
3. **El fallo se puede esperar.** Que no corra hoy y sí mañana es tolerable.
4. **A nadie le van a preguntar qué pasó.** No hay auditoría, ni linaje, ni un
   "¿por qué el modelo de producción salió de esta corrida?".

Rotar logs, refrescar un caché, limpiar archivos temporales, mandar un correo de
resumen: cron, sin dudar. Meter un orquestador ahí es agregar un servidor, un
worker y un deployment para algo que se resuelve con una línea.

Un pipeline de reentrenamiento **no cumple ninguna de las cuatro**. Tiene varios
pasos con resultados intermedios caros, no es barato, un fallo el lunes importa,
y la pregunta *"¿de qué corrida salió el modelo que está sirviendo?"* es la
pregunta central de la sesión.

## En Windows y en macOS

| Sistema | Situación |
|---|---|
| Linux | `cron` tal cual está descrito aquí |
| macOS | `cron` existe y funciona, pero necesita **Acceso total al disco** si el repo está en Documents, Desktop o Downloads (ver arriba). La alternativa nativa es `launchd` con un `.plist`, bastante más verboso |
| Windows | no hay `cron`. El equivalente es el **Programador de tareas** (`schtasks` en la línea de comandos), con las mismas limitaciones de los puntos 7 a 11 |

Que el peldaño 2 sea distinto en cada sistema operativo, y el peldaño 3 sea
idéntico en los tres, es también parte del argumento.

---

Siguiente: [`../3-orquestador.py`](../3-orquestador.py) — el mismo pipeline, con
los puntos 7 a 11 ya resueltos.
