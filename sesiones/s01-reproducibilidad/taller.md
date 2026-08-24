# Taller S01 — Tu primer repositorio bien montado

Vamos a crear un repositorio desde cero y dejarlo con lo mínimo que un proyecto
serio de ML necesita: entorno declarado, un paquete pequeño, un test y un
Makefile. Es la base sobre la que después van a montar el proyecto del curso.

No hace falta nada de sesiones futuras: solo `uv`, `git` y una cuenta de GitHub.
Si `make smoke` te salió bien en la parte de la clase, tienes todo.

Los talleres son opcionales y suman al bonus del curso. Este se puede terminar
en la misma clase.

---

## Paso 1 — El repositorio (5 min)

Crea un repositorio **público** en GitHub llamado `taller-mlops` (sin README, sin
.gitignore: los vamos a hacer nosotros). Luego, en tu terminal:

```bash
git clone git@github.com:TU-USUARIO/taller-mlops.git
cd taller-mlops
```

> Si el clone por SSH falla, revisa la clase pasada: `ssh -T git@github.com`
> debe saludarte por tu nombre.

## Paso 2 — El proyecto con uv (5 min)

```bash
uv init --name taller
uv add pandas scikit-learn
uv add --dev pytest ruff
```

Mira lo que apareció: `pyproject.toml` (lo que pediste), `uv.lock` (lo que
realmente se instaló, con versiones exactas) y `.venv/` (donde vive todo).

Crea un `.gitignore` con una sola línea por ahora:

```
.venv/
```

¿Por qué se ignora `.venv` pero **no** `uv.lock`? Piénsalo un momento: es la
pregunta 1 del final.

## Paso 3 — Un módulo con una función de verdad (8 min)

Borra el `main.py` que creó `uv init` y arma esta estructura:

```
src/taller/__init__.py      (vacío)
src/taller/limpieza.py
```

En `limpieza.py`, una función que ya conoces del caso de los taxis:

```python
import pandas as pd


def filtrar_duracion(df: pd.DataFrame, minimo: float = 1.0, maximo: float = 60.0) -> pd.DataFrame:
    """Deja solo los viajes con duracion en [minimo, maximo] minutos."""
    return df[(df["duration"] >= minimo) & (df["duration"] <= maximo)].reset_index(drop=True)
```

Y dile a `uv` que esto es un paquete, agregando al final de `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/taller"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Corre `uv sync` y pruébalo:

```bash
uv run python -c "from taller.limpieza import filtrar_duracion; print('funciona')"
```

## Paso 4 — Un test (5 min)

Crea `tests/test_limpieza.py`:

```python
import pandas as pd

from taller.limpieza import filtrar_duracion


def test_filtra_fuera_de_rango():
    df = pd.DataFrame({"duration": [0.5, 10.0, 30.0, 90.0]})
    resultado = filtrar_duracion(df)
    assert list(resultado["duration"]) == [10.0, 30.0]


def test_no_modifica_el_original():
    df = pd.DataFrame({"duration": [0.5, 10.0]})
    filtrar_duracion(df)
    assert len(df) == 2
```

```bash
uv run pytest
```

Dos tests, dos verdes. El segundo protege algo que en pandas se rompe fácil:
que la función no mutile el dataframe que le pasaron.

## Paso 5 — El Makefile (5 min)

Crea un archivo llamado `Makefile` (sin extensión, y ojo: la sangría de cada
comando es un **tab**, no espacios):

```make
setup:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .
```

Pruébalos: `make test`, `make lint`. Si `ruff` se queja de algo, `make format`
lo arregla casi todo.

¿Para qué esto si los comandos son cortos? Porque a partir de ahora **la
interfaz de tu repo son cuatro palabras**, y cualquier compañero (o un CI) puede
usarlo sin saber qué hay detrás.

## Paso 6 — Commit y push (2 min)

```bash
git add .
git commit -m "feat: paquete taller con limpieza de duracion y tests"
git push -u origin main
```

Fíjate en el formato del mensaje: `tipo: descripción`, como vimos en la clase de
git.

---

## Entrega

La URL de tu repositorio, en el canal del curso.

**La prueba de fuego** — y esto es todo el punto del taller: tu compañero de al
lado clona **tu** repo y corre:

```bash
uv sync && uv run pytest
```

Si a él le da verde sin preguntarte nada, lo lograste. Eso es reproducibilidad:
no hay más criterio que ese.

## Checklist

- [ ] El repo está en GitHub y es público
- [ ] Tiene `pyproject.toml` y `uv.lock` commiteados, y `.venv/` ignorado
- [ ] `src/taller/limpieza.py` con la función
- [ ] `tests/` con los dos tests en verde
- [ ] `Makefile` con `setup`, `test`, `lint`, `format`
- [ ] Al menos un commit con mensaje `tipo: descripción`
- [ ] Un compañero lo clonó y `uv sync && uv run pytest` le dio verde

## Si te sobra tiempo

En orden de provecho:

1. Agrega `pre-commit` con `ruff` (la guía está en [`calidad.md`](calidad.md) §5)
2. Móntale un CI mínimo: un workflow de GitHub Actions que corra `uv sync` y
   `uv run pytest` en cada push ([`calidad.md`](calidad.md) §6 tiene el YAML)
3. Escribe en el README de tu repo, en tres líneas, qué hace y cómo se corre

Estos tres son justo lo que iremos agregando en las próximas sesiones, así que
nada se pierde si no llegas.

## Errores típicos

| Síntoma | Causa | Arreglo |
|---|---|---|
| `Makefile:2: *** missing separator` | usaste espacios en vez de tab | reemplaza la sangría por un tab |
| `ModuleNotFoundError: taller` | falta el bloque `[tool.hatch...]` o el `uv sync` | agrega el bloque del paso 3 y corre `uv sync` |
| `pytest: command not found` | lo corriste sin `uv run` y fuera del venv | `uv run pytest` |
| el push pide contraseña una y otra vez | el remote quedó por HTTPS | `git remote set-url origin git@github.com:TU-USUARIO/taller-mlops.git` |
| `Permission denied (publickey)` | la llave SSH no está en GitHub o no está cargada | revisa [`git.md`](git.md) §1 |
