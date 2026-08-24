# Troubleshooting por sistema operativo: macOS y Windows

> **Documento de consulta, no de lectura lineal.** Busca tu síntoma en la tabla de sección 1
> y salta a la sección.
> **Fecha de revisión:** agosto de 2026. Reemplaza a `07-os-notes.md`, que tenía dos
> errores que hacían fallar la primera hora de clase en Windows (sección 2 y sección 3 explican
> cuáles).

Los estudiantes de este curso trabajan mayoritariamente en Windows, y la matriz del
CI incluye `windows-latest` **a propósito**: casi todos los fallos de la sesión 1
eran específicos de esa plataforma, y un curso que solo se prueba en Linux los
descubre en el aula.

---

## 1. Tabla de síntomas

| Síntoma | Sistema | Sección |
|---|---|---|
| `... no se puede cargar porque la ejecución de scripts está deshabilitada` / `UnauthorizedAccess` | Windows | [sección 2](#2-executionpolicy-el-primer-error-de-la-sesión) |
| `Activate.ps1` "no existe" o apunta a un sitio raro | Windows | [sección 3](#3-activar-el-entorno-el-punto-inicial-importa) |
| `chmod: command not found` / `./script.sh` no arranca | Windows | [sección 4](#4-los-scripts-sh-no-funcionan-en-windows) |
| `python` es 3.14 y el proyecto pide 3.11 | ambos | [sección 5](#5-versión-de-python) |
| `make: command not found` | Windows | [sección 6](#6-make-no-existe-en-windows) |
| Puerto 5000 ocupado, MLflow no arranca | macOS | [sección 7](#7-puertos-ocupados) |
| `warning: LF will be replaced by CRLF` | Windows | [sección 8](#8-fines-de-línea-crlf-vs-lf) |
| Los `.png` se ven como texto de tres líneas | ambos | [sección 9](#9-git-lfs) |
| `xcrun: error: invalid active developer path` | macOS | [sección 10](#10-macos-command-line-tools) |
| Rutas con espacios o con acentos que rompen comandos | ambos | [sección 11](#11-rutas-con-espacios-y-caracteres-no-ascii) |
| Nada de lo anterior y llevas 10 minutos | ambos | [sección 12](#12-el-plan-b-el-devcontainer) |

---

## 2. `ExecutionPolicy`: el primer error de la sesión

**Windows.** Es el error nº 1 de la sesión 1 y hay que atajarlo **antes** de
ejecutar cualquier `.ps1`, incluido `Activate.ps1` y los scripts de
[`scripts/`](scripts/).

Windows viene con la política `Restricted` por defecto: **ningún** script de
PowerShell se ejecuta. El error se ve así:

```
.\.venv\Scripts\Activate.ps1 : No se puede cargar el archivo ... porque la
ejecución de scripts está deshabilitada en este sistema.
    + CategoryInfo : SecurityError: (:) [], PSSecurityException
    + FullyQualifiedErrorId : UnauthorizedAccess
```

El arreglo, en el **paso 1** de tu setup:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Y para comprobar en qué estado estás:

```powershell
Get-ExecutionPolicy -List
```

Tres notas que evitan hacer esto mal:

- **`-Scope CurrentUser`** no necesita permisos de administrador y solo afecta a tu
  usuario. Es lo correcto en una máquina compartida o gestionada por la
  universidad. `-Scope LocalMachine` sí requiere administrador.
- **`RemoteSigned`** permite ejecutar scripts locales y exige firma solo a los
  descargados de internet. Es el nivel razonable. `Unrestricted` y `Bypass` quitan
  la comprobación entera: no los uses como estado permanente.
- Si tu equipo es gestionado por la universidad, una **política de grupo** puede
  sobrescribir esto y `Set-ExecutionPolicy` fallará en silencio o con un aviso. En
  ese caso, salta a [sección 12](#12-el-plan-b-el-devcontainer): no pierdas la clase
  peleando con una GPO.

> **Qué se corrigió aquí.** En el material anterior, este remedio estaba en
> `07-os-notes.md`, es decir en el documento nº 7, mientras que
> `setup_uv_windows.ps1` se ofrecía en el nº 0. El estudiante ejecutaba el script,
> fallaba, y la solución estaba siete documentos más adelante. Ahora está en el paso
> 1 del [Quick Start](README.md#5-quick-start) y en el encabezado del propio
> [`scripts/setup_uv_windows.ps1`](scripts/setup_uv_windows.ps1).

---

## 3. Activar el entorno: el punto inicial importa

| Sistema / shell | Comando correcto |
|---|---|
| macOS / Linux (`zsh`, `bash`) | `source .venv/bin/activate` |
| Windows **PowerShell** | `.\.venv\Scripts\Activate.ps1` |
| Windows **Cmd** | `.\.venv\Scripts\activate.bat` |
| Git Bash en Windows | `source .venv/Scripts/activate` |
| Cualquiera (recomendado) | **no activar**: `uv run <comando>` |
| Desactivar | `deactivate` |

**El error que corrige esta tabla.** El material anterior
(`07-os-notes.md`, líneas 8-9) escribía la activación de Windows como
`` `\.venv\Scripts\Activate.ps1` `` — **sin el punto inicial**. En PowerShell, una
ruta que empieza por `\` es absoluta desde la **raíz de la unidad actual**, así que
ese comando busca el entorno en la raíz del disco, no en tu proyecto. El síntoma es
un `ObjectNotFound` que parece decir que el entorno no se creó, cuando el entorno
está perfectamente:

```powershell
.\.venv\Scripts\Activate.ps1     # correcto:  .\  = directorio actual
\.venv\Scripts\Activate.ps1      # INCORRECTO: \  = raíz de la unidad
.venv\Scripts\Activate.ps1       # funciona, pero PowerShell prefiere el .\ explícito
```

La razón por la que PowerShell insiste en `.\` es de seguridad: no ejecuta nada del
directorio actual sin que se lo pidas explícitamente, para que un archivo malicioso
llamado `ls.ps1` no se ejecute cuando escribes `ls`.

**Y la recomendación de fondo:** no actives. `uv run pytest`, `uv run python ...`
funciona igual en los cuatro shells de la tabla, no depende del estado de tu
terminal y es lo único que funciona dentro de un contenedor o de un `cron`.

---

## 4. Los scripts `.sh` no funcionan en Windows

Si un tutorial —o un compañero— te dice:

```bash
chmod +x setup.sh && ./setup.sh
```

eso **no funciona en Windows**, y no es que "falte configurar algo":

- `chmod` es un comando POSIX: no existe en PowerShell ni en Cmd;
- el **bit de ejecución** no es un concepto de NTFS. Windows decide si algo es
  ejecutable por la extensión (`.exe`, `.bat`, `.ps1`), no por un permiso;
- `./setup.sh` no tiene con qué interpretarse, porque no hay un `bash` en el `PATH`.

Tienes tres salidas, en orden de recomendación:

1. **Usa el `.ps1` equivalente.** En esta carpeta están los cuatro:
   [`setup_uv_windows.ps1`](scripts/setup_uv_windows.ps1),
   [`setup_poetry_windows.ps1`](scripts/setup_poetry_windows.ps1) y sus dos gemelos
   de macOS.
2. **Git Bash**, que viene con Git para Windows. Ahí `chmod +x` y `./script.sh`
   funcionan, porque es un entorno POSIX emulado. Cuidado: las rutas cambian de
   forma (empiezan por `/c/` en lugar de por `C:\`) y algunos programas nativos de
   Windows no las entienden.
3. **WSL 2** (`wsl --install`), que es Linux de verdad. Es la mejor opción si vas a
   trabajar en serio con Docker y `Makefile`, y la peor si tienes 15 minutos: hay que
   entender que el `.venv` de WSL y el de Windows son entornos distintos, y que
   acceder a archivos de Windows desde WSL a través de `/mnt/c/` es lento.

**Regla del curso:** cuando un documento traiga un comando de shell, tiene que decir
para qué sistema es. Si no lo dice, asume Linux/macOS.

---

## 5. Versión de Python

**Ruta recomendada (los dos sistemas):**

```bash
uv python install 3.11
uv python pin 3.11        # escribe .python-version
uv sync
```

Este repositorio ya trae `.python-version` con `3.11`, así que basta con que `uv`
tenga ese intérprete disponible.

**El problema clásico.** `python -m venv .venv` usa **el primer Python del `PATH`**,
sin preguntar y sin avisar. Si Homebrew o la Microsoft Store te instalaron 3.14, ese
es el que se usa, y tu entorno no es el del proyecto. Diagnóstico:

```bash
python -V
which python        # macOS / Linux
where.exe python    # Windows
```

En Windows hay una trampa adicional: si escribes `python` y no lo tienes instalado,
Windows abre la **Microsoft Store**. Es un "alias de ejecución de aplicación" que se
desactiva en *Configuración → Aplicaciones → Alias de ejecución de aplicaciones*.

**`pyenv` como alternativa.** Sigue siendo una herramienta correcta, y en macOS es
cómoda:

```bash
brew install pyenv
echo 'eval "$(pyenv init -)"' >> ~/.zshrc && exec "$SHELL"
pyenv install 3.11.9
pyenv local 3.11.9
```

En Windows, `pyenv-win` **no** es la ruta por defecto de este curso, y la razón es
operativa: su instalación descarga un `.ps1` crudo de GitHub con
`Invoke-WebRequest`, lo ejecuta contra la `ExecutionPolicy` de [sección 2](#2-executionpolicy-el-primer-error-de-la-sesión),
edita el `PATH` del usuario y **exige cerrar y volver a abrir la terminal**. Son
cuatro puntos de fallo antes de tener un intérprete. Si aun así la necesitas —por
ejemplo, porque administras proyectos que no usan `uv`—, la referencia oficial es
[github.com/pyenv-win/pyenv-win](https://github.com/pyenv-win/pyenv-win) y el paso
de `ExecutionPolicy` va **antes**.

---

## 6. `make` no existe en Windows

El repositorio usa el [`Makefile`](../../Makefile) como interfaz única, y `make` no
viene con Windows. Tres opciones:

1. **`devcontainer`** ([sección 12](#12-el-plan-b-el-devcontainer)): trae `make`, Docker y
   todo lo demás. Es lo que se recomienda.
2. **Instalarlo:** `winget install ezwinports.make` (o `choco install make`). Ojo:
   el `Makefile` de este repositorio declara `SHELL := /bin/bash`, así que necesitas
   un `bash` disponible —el de Git for Windows sirve— o algunos `targets` fallarán.
3. **Ejecutar los comandos a mano.** Abre el `Makefile` y cópialos: son dos o tres
   líneas por `target`. El equivalente de `make setup` está en el
   [Quick Start](README.md#5-quick-start).

---

## 7. Puertos ocupados

Este curso usa el puerto **5001** para MLflow en **todo** el material, y el motivo es
macOS: el puerto 5000 lo ocupa **AirPlay Receiver** desde Monterey. Se apaga en
*Ajustes del Sistema → General → AirDrop y Handoff → Receptor de AirPlay*, pero es
más barato no usar el 5000.

Antes del rediseño el repositorio mezclaba 5000 y 5001 entre scripts, notebooks y
`.env.example`, y el resultado típico era un servidor escuchando en un puerto y un
cliente apuntando al otro. Hoy el puerto está declarado una sola vez, en
[`src/taxi/config.py`](../../src/taxi/config.py):

```python
MLFLOW_PORT: Final[int] = 5001
```

Los puertos del curso son 5001 (MLflow), 4200 (Prefect), 8000 (API), 9090
(Prometheus), 3000 (Grafana), 9001 (MinIO). `make smoke` comprueba los tres
primeros. Para ver quién ocupa uno:

```bash
lsof -nP -iTCP:5001 -sTCP:LISTEN        # macOS / Linux
```

```powershell
Get-NetTCPConnection -LocalPort 5001 | Select-Object OwningProcess
Get-Process -Id <PID>
```

---

## 8. Fines de línea: CRLF vs LF

Windows termina las líneas con `CRLF`; macOS y Linux con `LF`. Si el repositorio
mezcla los dos, cada `git diff` muestra archivos completos como modificados aunque
nadie los tocara.

Este repositorio lo resuelve con el `hook` `mixed-line-ending --fix=lf`
(ver [`calidad.md`](calidad.md) sección 5): todo se normaliza a `LF` al commitear. El aviso
`warning: LF will be replaced by CRLF` en Windows es informativo, no un error.

Si quieres además que Git convierta al hacer `checkout`:

```bash
git config --global core.autocrlf true      # solo en Windows
```

Un caso donde el fin de línea **sí** rompe algo de verdad: un script `.sh` con
`CRLF` dentro de un contenedor Linux falla con
`/usr/bin/env: 'bash\r': No such file or directory`. Es el mismo problema, con un
mensaje que no lo parece.

---

## 9. Git LFS

Si los `.png` de [`sesiones/s04-orquestacion/diagrams/`](../s04-orquestacion/diagrams/)
se ven como archivos de texto de tres líneas que empiezan por
`version https://git-lfs.github.com/spec/v1`, es que faltan los objetos de LFS.

```bash
git lfs install
git lfs pull
git lfs ls-files      # deben aparecer los 12 diagramas
```

Instalación: `brew install git-lfs` (macOS),
`winget install GitHub.GitLFS` (Windows), `sudo apt install git-lfs` (Debian).
Detalle completo en [`git.md`](git.md) sección 5.

---

## 10. macOS: Command Line Tools

```
xcrun: error: invalid active developer path (/Library/Developer/CommandLineTools)
```

Aparece tras actualizar macOS y rompe `git`, `make` y cualquier compilación:

```bash
xcode-select --install
```

Si Homebrew se queja del `PATH` en un Mac con Apple Silicon, es que `brew` vive en
`/opt/homebrew` y no en `/usr/local`:

```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
```

---

## 11. Rutas con espacios y caracteres no ASCII

Clonar el repositorio en una carpeta que se llame `Mis Documentos/Proyectos MLOps
2026` funciona… hasta que un script pasa la ruta sin comillas a otro programa, o
hasta que una herramienta escrita en un lenguaje descuidado la parte por el espacio.

Recomendación práctica, no dogma: clona en una ruta **corta, sin espacios y sin
tildes**. Por ejemplo `~/dev/mlops-udem` en macOS, o `C:\dev\mlops-udem` en Windows.
En Windows hay un segundo motivo: el límite histórico de 260 caracteres de `MAX_PATH`
sigue afectando a algunas herramientas, y `.venv/Lib/site-packages/...` gasta muchos
de esos caracteres. Se puede levantar el límite:

```bash
git config --global core.longpaths true
```

Y no uses OneDrive, iCloud Drive ni Dropbox para el repositorio. La sincronización
compite con Git por los mismos archivos, bloquea `.git/index` en el peor momento y
produce conflictos que no son de Git y no se arreglan con Git.

---

## 12. El plan B: el `devcontainer`

**Regla de la sesión 1: si llevas más de 10 minutos peleando con tu máquina, para.**
No bloquees la clase ni te bloquees a ti mismo. Abre el
[`devcontainer`](../../.devcontainer/) y sigue la sesión desde ahí:

- **GitHub Codespaces:** en tu fork, botón *Code → Codespaces → Create codespace*.
  No necesitas instalar nada en tu máquina.
- **Docker local + VS Code:** extensión *Dev Containers*, y
  *Reopen in Container*.

Trae Python 3.11, `uv`, `git-lfs`, `make` y las dependencias del curso ya
sincronizadas, y `make setup && make smoke` funciona dentro. Los detalles y las
limitaciones honestas están en [`.devcontainer/README.md`](../../.devcontainer/README.md).

Arreglas tu máquina en la pausa o después de clase. El objetivo de hoy es entender
qué hace reproducible a un entorno, no ganarle una discusión al `PATH` de Windows.

---

Volver: [README](README.md) · [`entorno.md`](entorno.md) · [`git.md`](git.md) ·
[`calidad.md`](calidad.md)
