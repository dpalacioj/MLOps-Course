# `devcontainer` del curso — el plan B de la sesión 1

> **Fecha de revisión:** agosto de 2026.
> Referencia oficial: [containers.dev](https://containers.dev/) ·
> [docs.github.com/codespaces](https://docs.github.com/en/codespaces).

## Para qué existe

Para que **nadie pierda una sesión por un problema de entorno**.

La sesión 1 tiene una regla: si llevas más de 10 minutos peleando con tu máquina,
paras y sigues la clase desde aquí. Arreglas tu `PATH` en la pausa. El objetivo de la
sesión es entender qué hace reproducible a un entorno, no ganarle una discusión a la
`ExecutionPolicy` de Windows.

No es "la forma correcta" de trabajar en el curso: la forma correcta es que el setup
local funcione, porque es lo que el estudiante va a tener que hacer en su trabajo. Es
una **red de seguridad**, y su valor está en que existe antes de necesitarla.

## Cómo se usa

### Opción A — GitHub Codespaces (no instalas nada)

En tu fork del repositorio: botón **Code → Codespaces → Create codespace on
`<rama>`**.

El contenedor se construye y `onCreateCommand` deja el entorno listo. Cuando la
terminal esté disponible:

```bash
make smoke
```

**Cuenta gratuita de GitHub, a agosto de 2026:** 120 horas-núcleo y 15 GB-mes de
almacenamiento incluidos. Con la máquina de 2 núcleos que este `devcontainer` pide
son ~60 horas al mes, que sobran para el curso. **Verifica las cifras vigentes** en
[la documentación de facturación de Codespaces](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-codespaces/about-billing-for-github-codespaces)
antes de la cohorte: cambian.

Y **para el Codespace cuando no lo uses** (`Code → Codespaces → Stop`): un Codespace
encendido consume horas aunque no estés escribiendo.

### Opción B — Docker local + VS Code

Requisitos: Docker Desktop (o Docker Engine) y la extensión
[Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).

1. abre el repositorio en VS Code;
2. paleta de comandos → **Dev Containers: Reopen in Container**;
3. cuando termine: `make smoke`.

### Opción C — CLI, sin VS Code

```bash
npm install -g @devcontainers/cli
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . make smoke
```

## Qué trae

| Pieza | De dónde sale | Por qué |
|---|---|---|
| Python 3.11 | imagen base `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` | la versión del curso (`.python-version`) |
| `uv` | instalador oficial, en `post-create.sh` | la imagen base no lo trae |
| Dependencias del curso | `uv sync --group dev --locked` | **desde el `lockfile`**, no resueltas de nuevo |
| `git-lfs` | `feature` `git-lfs:1` con `autoPull` | los 12 diagramas de S04 son `.png` en LFS |
| `make` | viene en la imagen base (Debian) | es la interfaz única del repositorio |
| Docker (`docker` + `compose`) | `feature` `docker-in-docker:2` | `make up` de S05 y S07 |
| `hooks` de `git` y de `pre-commit` | `post-create.sh` | para que el taller se pueda entregar desde aquí |
| Kernel de Jupyter registrado | `post-create.sh` | evita el error nº 1 con notebooks: un kernel que no ve las dependencias del proyecto |
| Puertos reenviados | `forwardPorts` | 5001 MLflow · 4200 Prefect · 8000 API · 9090 Prometheus · 3000 Grafana · 9001 MinIO · 8888 Jupyter |

Detalle no obvio: `UV_PROJECT_ENVIRONMENT` apunta a `/workspaces/.venv-curso`, es
decir **fuera** del directorio del repositorio. Es a propósito: en Docker Desktop
para macOS y Windows, un `.venv` dentro de un volumen montado desde el host es
notablemente más lento, y además evita que el `.venv` del contenedor y el de tu
máquina se pisen si usas las dos cosas.

Y `UV_LINK_MODE=copy` está puesto porque el caché de `uv` y el entorno acaban en
sistemas de archivos distintos dentro del contenedor; sin él, `uv` avisa en cada
paquete de que no puede usar `hardlink`.

## Qué **no** trae, a propósito

- **Los datos.** Son ~200 MB de parquet. Se descargan cuando hagas falta con
  `make data`, que además verifica el SHA-256 de cada partición contra
  `data/raw/metadata.json`. Meterlos en la imagen la haría enorme y rompería la
  lección de la sesión 2 sobre procedencia y verificación.
- **Los servicios levantados.** `make up` los levanta cuando toque (S05, S07). Un
  contenedor que arranca cinco servicios que nadie está usando consume la cuota de
  Codespaces sin dar nada.
- **Las dependencias de la sesión 8** (`llmops`: `openai`, `litellm`, `tiktoken`).
  Están en un `extra` opcional y se instalan con `uv sync --extra llmops` cuando
  llegue esa sesión.
- **Claves ni tokens.** Copia `.env.example` a `.env` y rellena lo que necesites. En
  Codespaces, lo correcto para un secreto real son los
  [Codespaces secrets](https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces),
  no un `.env` que puede acabar commiteado.

## Limitaciones honestas

Conviene decirlas antes de que sorprendan en clase:

1. **La primera construcción tarda.** No prometemos una cifra: depende de la red y de
   si la imagen base está en caché. **Mide la tuya** una vez, apúntala, y así el
   instructor sabe qué esperar en el aula. La promesa de "3 minutos" del plan B se
   refiere a *pasarle el enlace al estudiante*, no a que el contenedor esté
   construido.
2. **Docker dentro de Docker** funciona pero pesa. En una máquina de 2 núcleos,
   `make up` con el stack completo de S07 (MLflow + MinIO + Postgres + API +
   Prometheus + Grafana) va justo. Para esas dos sesiones, sube la máquina del
   Codespace a 4 núcleos.
3. **Un `devcontainer` esconde el problema, no lo resuelve.** Si un estudiante hace
   las ocho sesiones aquí, no habrá aprendido a montar el entorno, que es un objetivo
   real de la sesión 1. Úsalo como red, no como casa.
4. **Los puertos son del contenedor.** En Codespaces, VS Code los reenvía a una URL
   `https://...app.github.dev`. Si un notebook o un `.env` tiene `127.0.0.1:5001`
   escrito a mano, dentro del contenedor funciona; desde tu navegador, hay que usar
   la URL reenviada. Ver la pestaña **Ports**.
5. **`git lfs pull` puede fallar** si el `fork` no tiene los objetos LFS o si se agotó
   la cuota de ancho de banda de LFS del `fork`. El script lo avisa y sigue: los
   diagramas se verán mal, el resto funciona.

## Si algo falla dentro del `devcontainer`

```bash
# 1. El diagnóstico de siempre
make smoke

# 2. Reconstruir el entorno de Python sin reconstruir el contenedor
uv sync --group dev --locked

# 3. Volver a correr el post-create completo
bash .devcontainer/post-create.sh

# 4. Reconstruir el contenedor entero
#    VS Code: paleta -> "Dev Containers: Rebuild Container"
#    Codespaces: Code -> Codespaces -> ... -> Rebuild container
```

## Archivos

```
.devcontainer/
├── devcontainer.json    la configuración (JSON estricto: sin comentarios, sin comas finales)
├── post-create.sh       lo que se ejecuta una vez al crear el contenedor
└── README.md            este archivo
```

`devcontainer.json` se escribe como **JSON estricto** a propósito, aunque la
especificación permita JSONC: así el `hook` `check-json` del repositorio puede
validarlo. Los comentarios que explicarían cada campo están aquí, que es donde
alguien los va a leer.

---

Relacionado: [`sesiones/s01-reproducibilidad/README.md`](../sesiones/s01-reproducibilidad/README.md) ·
[`sesiones/s01-reproducibilidad/troubleshooting-so.md`](../sesiones/s01-reproducibilidad/troubleshooting-so.md) ·
[`Makefile`](../Makefile) · [`scripts/smoke_test.py`](../scripts/smoke_test.py)
