# Git: flujo diario, `conventional commits` y LFS

> **Bloque B de la sesión 1**, primera mitad (110-140 min).
> **Fecha de revisión:** agosto de 2026. `git-lfs 3.4.1` verificado en esta máquina.
> Referencias oficiales: [git-scm.com/doc](https://git-scm.com/doc) ·
> [git-lfs.com](https://git-lfs.com/) ·
> [conventionalcommits.org](https://www.conventionalcommits.org/es/v1.0.0/).

Este documento reemplaza a `01-git-github.md`, `01.1-conventional-commits.md` y
`10-git-lfs.md`. El cambio de fondo no es de contenido: es de **orden**. Git LFS era
el documento nº 10 de 13 y por eso los 12 diagramas de la sesión 4 aparecían como
archivos de texto de tres líneas para cualquiera que clonara el repositorio. Aquí es
la sección 5 de 8, y se hace **antes** del primer commit de un binario.

---

## 1. Lo mínimo, una vez por máquina

```bash
git config --global user.name "Tu Nombre"
git config --global user.email "tu@correo.edu.co"
git config --global init.defaultBranch main
git config --global pull.rebase true       # historial lineal, sin merges de "pull"
```

Verifica: `git --version`. Si no lo tienes, en macOS `brew install git` (o
`xcode-select --install`); en Windows,
`winget install --id Git.Git -e --source winget`.

### SSH, en tres comandos y una idea

La idea: creas un par de claves. La **privada** se queda en tu máquina y no se
comparte con nadie. La **pública** (`.pub`) se registra en GitHub. GitHub reconoce
tu máquina sin pedirte usuario y contraseña en cada `push`.

```bash
ssh-keygen -t ed25519 -C "tu@correo.edu.co"    # Enter para la ruta por defecto
eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519   # en macOS: --apple-use-keychain
cat ~/.ssh/id_ed25519.pub                       # pega esto en GitHub -> Settings -> SSH keys
ssh -T git@github.com                           # debe saludarte por tu usuario
```

En Windows PowerShell el equivalente del tercer paso es
`Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub`.

`Permission denied (publickey)` significa una de tres cosas: GitHub no tiene tu
clave pública, tu clave privada no está cargada en el `agent`, o estás usando otra
cuenta. Se diagnostica con `ssh -T git@github.com -v`.

### Firmar commits (opcional en el curso, recomendado)

Sin firma, Git solo registra el nombre y correo que **tú** configuraste: cualquiera
puede poner tu nombre y hacer commits "como si fuera tú". Una firma es la prueba
criptográfica de autoría; en GitHub aparece como **Verified**.

Hoy la ruta más simple es firmar con la **misma clave SSH** que ya creaste, en lugar
de montar GPG:

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true
```

Y en GitHub, la clave se registra **otra vez** en *Settings → SSH and GPG keys*,
pero con el tipo **Signing Key** (la misma clave, dos propósitos distintos: una
entrada para autenticar, otra para firmar).

Si tu organización exige GPG, la ruta es `gpg --full-generate-key` (RSA 4096, sin
expiración para simplificar), `gpg --list-secret-keys --keyid-format=long` para
obtener el ID, `gpg --armor --export <ID>` para exportar la pública y
`git config --global user.signingkey <ID>`. En macOS, si el commit falla con
`gpg: signing failed: No pinentry`, se arregla con
`brew install pinentry-mac` y añadiendo `pinentry-program $(which pinentry-mac)` a
`~/.gnupg/gpg-agent.conf`.

**SSH vs GPG en una línea:** SSH es para **entrar** (autenticación del `push`); la
firma es para **acreditar autoría** de un commit. Son cosas distintas aunque GitHub
las liste en la misma pantalla.

---

## 2. El flujo diario del curso

Una rama por entrega, un PR por entrega. Los hitos del proyecto se entregan **como
PR, no como zip**: un zip produce una nota, un PR produce comentarios en las líneas
de código.

```bash
# 1) Partir de main actualizado
git switch main
git pull

# 2) Una rama por trabajo
git switch -c feat/contrato-de-datos

# 3) Trabajar, y commitear en trozos que se entiendan solos
git add src/miproyecto/data/contract.py tests/data/test_contrato.py
git commit -m "feat(data): add pandera contract with 6 rules"

# 4) Antes de abrir el PR, ponerse al día sin ensuciar el historial
git fetch origin
git rebase origin/main

# 5) Subir y abrir PR
git push -u origin feat/contrato-de-datos
```

Sobre `rebase` frente a `merge`: `rebase` reescribe tus commits encima de `main` y
deja un historial lineal, que es mucho más fácil de leer y de bisecar. La regla que
lo hace seguro: **nunca reescribas una rama que otra persona ya tiene**. Para tus
propias ramas de trabajo, `rebase`; para integrar el PR a `main`, el `merge` o el
`squash` que use tu equipo.

Y una advertencia práctica de aula: si `git rebase` te intimida, `git merge
origin/main` no está prohibido ni te baja la nota. Lo que sí importa es que el PR
esté actualizado y el CI verde.

---

## 3. Commits que sirven de algo

### Por qué `conventional commits`

No es estética. En este repositorio hay un `hook` de `commit-msg`
([`conventional-pre-commit`](https://github.com/compilerla/conventional-pre-commit),
ver [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml)) que **rechaza** un
mensaje que no cumpla el formato. Además, un historial con tipos permite generar
`CHANGELOG` automáticamente y, en MLOps, responder la pregunta que siempre aparece:
*"¿qué cambió entre el modelo de marzo y el de agosto?"*.

```
<tipo>(<alcance opcional>): <descripción en imperativo, minúscula, sin punto final>
```

| Tipo | Cuándo | Ejemplo |
|---|---|---|
| `feat` | funcionalidad nueva | `feat(data): add temporal split to loaders` |
| `fix` | corregir un bug | `fix(api): validate PULocationID range before predict` |
| `docs` | solo documentación | `docs(s02): add dataset card` |
| `refactor` | reestructurar sin cambiar comportamiento | `refactor(features): extract contract module` |
| `test` | tests | `test(data): add three broken fixtures` |
| `perf` | rendimiento | `perf(loaders): read only required parquet columns` |
| `build` | empaquetado y dependencias | `build: bump scikit-learn to 1.9` |
| `ci` | pipeline de CI/CD | `ci: run tests on windows-latest too` |
| `chore` | mantenimiento | `chore: configure git lfs for png` |
| `style` | formato, sin cambio de lógica | `style: apply ruff format` |
| `revert` | revertir un commit | `revert: feat(api) add batch endpoint` |

Los once tipos anteriores son exactamente los que acepta el `hook` de este
repositorio. Cualquier otro **bloquea el commit**.

Un cambio que rompe compatibilidad se marca con `!` y se explica en el cuerpo:

```
feat(api)!: rename field trip_distance to distance_miles

BREAKING CHANGE: los clientes que envíen `trip_distance` reciben 422.
El nombre nuevo declara la unidad, que era la causa del incidente de S02.
```

### Errores frecuentes

| Mal | Bien | Por qué |
|---|---|---|
| `Updated stuff` | `fix(data): correct parquet path in config` | el mensaje tiene que decir qué y dónde |
| `feat: Add new feature` | `feat: add drift check to CI` | minúscula después de `:`, y sé concreto |
| `fix: fixed the bug.` | `fix(loaders): handle null trip_distance` | imperativo, sin punto final |
| `WIP` | no commitees trabajo incompleto en la rama que vas a revisar | `git stash`, o commitea en tu rama y haz `squash` al final |
| `arreglos varios` | tres commits, uno por arreglo | un commit que hace cinco cosas no se puede revertir |

### Nombres de rama

`<tipo>/<descripción-corta-con-guiones>`, en minúsculas y sin espacios:
`feat/add-data-validation`, `fix/null-in-loader`, `docs/dataset-card`,
`ci/windows-matrix`. Evita `fix/bug` y `feat/update`: no dicen nada.

### El PR

Título: mismo formato que el commit. Cuerpo: tres apartados que se responden en
cuatro líneas cada uno.

```markdown
## Qué cambia
- ...

## Por qué
- ...

## Cómo verificarlo
- comandos concretos, y el enlace al run del CI
```

Requisitos del PR en este curso: **CI verde** y el enlace al `run`. Un PR rojo no
se revisa.

---

## 4. `.gitignore`: qué no entra nunca

Copia [`templates/.gitignore-python`](templates/.gitignore-python) a la raíz de tu
proyecto y ajústalo. Lo que **nunca** se commitea, con su razón:

| No | Por qué |
|---|---|
| `.venv/`, `__pycache__/`, `.pytest_cache/` | se regeneran; solo generan conflictos |
| `.env` | secretos. Commitea `.env.example` |
| `data/raw/`, `data/processed/` | se descargan y se verifican por hash (`make data`) |
| `mlruns/`, `mlflow.db`, `mlartifacts/` | el estado del `tracking server`, no el código |
| `*.pkl`, `*.bin`, `*.ubj`, `*.onnx` | el modelo se obtiene del `registry`, no del control de versiones. En el repositorio anterior había tres artefactos binarios commiteados y la imagen de Docker servía uno de ellos en lugar del promovido |
| `reports/*.html` | se regeneran con `make drift` |
| Notebooks con `outputs` | no se ignoran, se **limpian** con `nbstripout` ([`calidad.md`](calidad.md) sección 4) |

Trampa real de este repositorio, que vale como lección: el `.gitignore` anterior
ignoraba globalmente `*.json`, `*.yaml`, `*.yml` y `*.txt`. Con eso desaparecían de
la vista los `metadata.json` de los modelos y varios `.yaml` de configuración, y dos
módulos del curso dejaban de funcionar al clonar. Un `.gitignore` demasiado amplio
no es "más seguro": es una forma de perder archivos sin enterarse. Por eso el actual
lleva excepciones explícitas (`!**/metadata.json`).

---

## 5. Git LFS — **antes** del primer binario, no después

### El problema

Git guarda **una copia completa de cada versión** de cada archivo. Con texto eso es
eficiente, porque comprime los diffs. Con un binario, no hay diff: un `.png` de
4 MB modificado diez veces son ~40 MB de historial permanente. `git clone` se
vuelve lento para todo el mundo, para siempre, y GitHub rechaza archivos de más de
100 MB.

Git LFS sustituye el binario por un **puntero de texto de ~130 bytes** y guarda el
contenido real en un servidor aparte, que se descarga bajo demanda.

```
Sin LFS:  .git/ contiene todas las versiones del binario         (crece sin límite)
Con LFS:  .git/ contiene punteros de ~130 bytes                  (constante)
          servidor LFS contiene las versiones reales             (descarga bajo demanda)
```

### El orden importa, y es el punto de esta sección

```bash
# 1) Instalar LFS y activarlo en tu usuario (una vez por máquina)
brew install git-lfs          # macOS
# winget install GitHub.GitLFS  # Windows
# sudo apt install git-lfs      # Debian/Ubuntu
git lfs install

# 2) Declarar QUÉ va a LFS, antes de agregar el archivo
git lfs track "*.png"
git lfs track "*.parquet"

# 3) Commitear .gitattributes PRIMERO, en su propio commit
git add .gitattributes
git commit -m "chore: track png and parquet with git lfs"

# 4) Ahora sí, el binario
git add diagrams/01-arquitectura.png
git commit -m "docs: add architecture diagram"
git push
```

**Si inviertes los pasos 3 y 4, el binario entra al historial como blob normal** y
agregarlo después a `.gitattributes` no lo saca de ahí. El historial ya está
contaminado; para limpiarlo hay que reescribirlo (`git lfs migrate import
--include="*.png" --everything`) y forzar el `push`, lo que rompe todos los clones
existentes. Eso responde la autoverificación nº 3 del README: **no, `git lfs pull`
no lo arregla** — `git lfs pull` trae objetos LFS, y ese archivo nunca fue un objeto
LFS.

### Verificar

```bash
git lfs ls-files          # qué archivos gestiona LFS
git lfs track             # qué patrones están declarados
git lfs env               # configuración y endpoint
cat .gitattributes
```

En este repositorio, `.gitattributes` contiene una sola línea:

```
*.png filter=lfs diff=lfs merge=lfs -text
```

Y los 12 diagramas de [`sesiones/s04-orquestacion/diagrams/`](../s04-orquestacion/diagrams/)
viven ahí. Si los ves como archivos de texto de tres líneas que empiezan por
`version https://git-lfs.github.com/spec/v1`, te falta `git lfs pull`.
`make smoke` lo detecta y lo reporta como **FAIL**, no como aviso, porque un
diagrama roto en la sesión 4 son diez minutos de clase perdidos:

```python
# scripts/smoke_test.py, comprobación de LFS
# Un puntero LFS sin traer pesa ~130 bytes. Si el archivo real es pequeño,
# el diagrama no se va a ver en el README.
```

El `job` `smoke` del CI hace `checkout` **con `lfs: true`** a propósito, para
verificar que los punteros se resuelven de verdad; los demás `jobs` no lo hacen,
para no gastar cuota de ancho de banda.

### Cuándo sí y cuándo no

| Usar LFS | No usar LFS |
|---|---|
| imágenes y diagramas que se versionan (PNG, JPG) | texto: código, markdown, YAML, CSV pequeño (Git ya los comprime y hace diff) |
| un `dataset` de muestra pequeño y **estable** que los tests necesitan | el `dataset` de entrenamiento completo: descárgalo con un script y verifica el hash |
| modelos serializados si tu flujo **exige** versionarlos en Git | modelos en general: van al `registry` de MLflow (S03) |
| binarios que cambian **pocas veces** | binarios que cambian en cada commit: LFS almacena cada versión y el storage crece igual de rápido, solo que en otro sitio y con cuota |

Límites de GitHub, a agosto de 2026: 1 GB de almacenamiento y 1 GB/mes de ancho de
banda en el plan gratuito. Para un curso sobra;
[la documentación de GitHub](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-storage-and-bandwidth-usage)
tiene las cifras vigentes, y conviene mirarlas antes de meter cinco `datasets` de
800 MB.

### LFS no es versionado de datos

Es importante no confundirlos, y es un error habitual. LFS resuelve **el tamaño del
blob en Git**. No te da `diff` de tablas, ni `time travel`, ni ramas de datos, ni
`lineage`. Para eso están DVC, lakeFS y Delta/Iceberg, cada uno resolviendo un
problema distinto, y es el contenido de
[`sesiones/s02-datos/versionado-de-datos.md`](../s02-datos/versionado-de-datos.md).

---

## 6. Los `hooks` de Git de este repositorio

Un `hook` es un script que **Git ejecuta solo**, en momentos concretos del flujo.
No lo invocas tú: se dispara al crear un commit, al validar su mensaje o antes de
un push. Es el eslabón más barato de la cadena de verificación — dos segundos en
tu terminal en lugar de cuatro minutos de CI, o de un incidente.

`make setup` los instala todos con `pre-commit`, en tres momentos:

| Momento | Qué valida |
|---|---|
| `pre-commit` | `ruff` (lint y formato), `gitleaks` (secretos), `nbstripout` (notebooks sin `outputs`), tamaño de archivos, y los `hooks` propios del curso |
| `commit-msg` | formato `conventional commits` |
| `pre-push` | convención del nombre de la rama |

El detalle de cada uno está en [`calidad.md`](calidad.md) sección 5.

### Por qué hay un solo sistema de `hooks`

Git admite **un único** lugar donde buscar `hooks`, definido por la variable
`core.hooksPath`. Este repositorio tenía dos sistemas compitiendo por ese puesto:
una carpeta `.githooks/` y `pre-commit`. El `make setup` apuntaba
`core.hooksPath` a `.githooks/` y a continuación intentaba instalar `pre-commit`,
que responde:

```
[ERROR] Cowardly refusing to install hooks with `core.hooksPath` set.
```

Se negaba, y el `make setup` **seguía adelante sin avisar**. Resultado: quedaban
activas las dos validaciones de `.githooks/` y no se instalaba nada de
`pre-commit`. El repositorio se quedaba sin `ruff`, sin `gitleaks` y sin
`nbstripout`, y nadie se enteraba hasta que un secreto llegaba al historial.

Se eliminó `.githooks/`: `pre-commit` ya cubría la validación del mensaje, y la
del nombre de rama se movió a
[`scripts/hooks/nombre_de_rama.py`](../../scripts/hooks/nombre_de_rama.py), en el
`stage` de `pre-push`.

**La lección es de MLOps, no de Git:** un mecanismo de verificación que falla en
silencio es peor que no tenerlo, porque produce confianza injustificada. Es el
mismo defecto que tenía el CI de este repositorio con su
`pytest -q || echo "No tests configured yet"`. Por eso `make smoke` ahora
comprueba que los `hooks` estén realmente instalados, en lugar de suponerlo.

---

## 7. Errores frecuentes de este bloque

| Síntoma | Causa | Arreglo |
|---|---|---|
| `Permission denied (publickey)` | la clave pública no está en GitHub, o la privada no está en el `agent` | `ssh-add ~/.ssh/id_ed25519` y verifica con `ssh -T git@github.com` |
| El `hook` rechaza tu mensaje de commit | no cumple `conventional commits` | usa uno de los once tipos de sección 3 |
| Los `.png` se ven como texto de tres líneas | falta `git lfs pull` (o LFS no estaba instalado al clonar) | `git lfs install && git lfs pull` |
| `warning: LF will be replaced by CRLF` en Windows | fin de línea distinto entre sistemas | el `hook` `mixed-line-ending --fix=lf` ya lo normaliza; ver [`troubleshooting-so.md`](troubleshooting-so.md) sección 3 |
| Commiteaste un `.env` | secreto en el historial | **rota el secreto** y luego límpialo del historial. Borrarlo en un commit nuevo no basta |
| El repositorio pesa 800 MB tras tres semanas | binarios commiteados sin LFS | `git lfs migrate import` + `push --force`, avisando a todo el equipo |

---

## 8. Autoverificación del bloque

1. ¿Qué contiene `uv.lock` que no contiene `pyproject.toml`, y qué pregunta
   responde cada uno? (Es de [`entorno.md`](entorno.md) sección 2, y va aquí porque en el
   PR los dos se commitean juntos.)
2. Explica en una frase por qué `.gitattributes` se commitea **antes** que el
   binario.
3. Alguien clona tu repositorio sin `git-lfs` instalado. ¿Qué ve? ¿Rompe algo o solo
   se ve mal?
4. ¿Por qué el `job` `smoke` del CI hace `checkout` con `lfs: true` y los demás
   `jobs` no?

Siguiente: [`calidad.md`](calidad.md) · Volver: [README](README.md)
