# Solución de referencia — Taller S01

> **No publicar antes del taller.**
> Enunciado: [`../taller.md`](../taller.md).

El repositorio del curso cumple los diez criterios, así que sirve de solución
ejecutable. Esta página recorre los diez y señala **qué archivo** los satisface y
**con qué comando** se comprueba, para que la revisión de los PR de los estudiantes
sea mecánica y no una discusión de gustos.

---

## Criterio 1 — El workflow del CI pasa

Archivo: [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml).

Cinco `jobs`: `calidad`, `tests` (matriz ubuntu + windows), `smoke`, `secretos`,
`imagen`. Para el taller basta con `calidad`, `tests` y `smoke`.

**Cómo revisar el PR de un estudiante:** el `check` verde no es suficiente. Abre el
`run` y comprueba que ningún paso tenga `continue-on-error`, `|| true` o `|| echo`.
Es el error que más se repite, porque las plantillas que circulan por internet lo
traen.

```bash
# Búsqueda rápida en el PR del estudiante
grep -rn -E "continue-on-error|\|\| *true|\|\| *echo" .github/workflows/
# Cualquier resultado es motivo de devolución.
```

## Criterio 2 — `make smoke` sale OK, y falla cuando debe

Archivos: [`Makefile`](../../../Makefile) (`target` `smoke`) y
[`scripts/smoke_test.py`](../../../scripts/smoke_test.py).

```bash
make smoke ; echo "exit code: $?"     # 0
```

**La comprobación que de verdad importa** es la segunda: que el diagnóstico pueda
fallar. Inyecta un fallo y verifica el exit code:

```bash
# Simula una dependencia que falta, en un entorno de usar y tirar
cd /tmp && rm -rf prueba && git clone <url> prueba && cd prueba
uv sync                                 # sin --group dev: falta ruff, pytest...
uv run python scripts/smoke_test.py ; echo "exit code: $?"   # != 0
```

Un `smoke_test.py` que imprime avisos y siempre devuelve `0` no cumple el criterio.
La estructura correcta está al final del script del curso:

```python
fallos = sum(1 for e, _, _ in resultados if e == "FAIL")
if fallos:
    return 1
return 0
```

Nota sobre `WARN` vs `FAIL`, que es una decisión de diseño que conviene comentar en
clase: Docker ausente es `WARN` (no se necesita hasta S05); punteros de Git LFS sin
resolver es `FAIL` (rompe la S04). La distinción tiene que estar razonada, no ser
casual.

## Criterio 3 — `pytest` corre ≥ 2 tests

Referencia: [`tests/`](../../../tests/), con 308 tests. Para el taller bastan dos,
pero **tienen que significar algo**. Ejemplos del repositorio, uno de cada tipo:

- **Coherencia de constantes** —
  [`tests/unit/test_config_y_convenciones.py`](../../../tests/unit/test_config_y_convenciones.py):
  que las particiones no se solapen, que el holdout no esté en `train`, que el
  puerto de MLflow sea uno solo en todo el repositorio.
- **Determinismo** —
  [`tests/unit/test_determinismo.py`](../../../tests/unit/test_determinismo.py):
  la misma entrada, dos veces, produce exactamente lo mismo.

Un test aceptable, escrito desde cero, se parece a esto:

```python
def test_las_particiones_no_se_solapan() -> None:
    """El holdout no puede estar en train: si esta, el gate no mide nada."""
    etiquetas = [p.etiqueta for p in PARTICIONES_TRAIN]
    assert PARTICION_TEST.etiqueta not in etiquetas
    assert PARTICION_VALID.etiqueta not in etiquetas
```

`assert True`, `assert 1 == 1` y un test que solo comprueba que un `import`
funciona no cuentan. Lee los dos tests del estudiante; es lo único que no se puede
automatizar de este criterio.

## Criterio 4 — `ruff check` sin errores

Configuración: [`pyproject.toml`](../../../pyproject.toml), sección `[tool.ruff]`.

```bash
uv run ruff check .
uv run ruff format --check --diff .
```

Detalle a mirar en el PR: que la configuración esté en `pyproject.toml` y no en un
`.ruff.toml` separado (una configuración menos que sincronizar), y que
`select` incluya al menos `E`, `F` e `I`. Si solo trae los `defaults`, el lint no
está ordenando imports y el primer PR con conflictos de `import` lo va a demostrar.

## Criterio 5 — Existe `uv.lock` y está commiteado

```bash
ls -la uv.lock
git log --oneline -1 -- uv.lock
grep -c '^\[\[package\]\]' uv.lock     # nº de paquetes resueltos de verdad
```

Y la comprobación indirecta, que es la buena: el CI instala con
`uv sync --group dev --locked`. Si el `lock` estuviera desfasado o ausente, ese paso
falla. Con Poetry el equivalente es `poetry install` con `poetry.lock` commiteado.

**Motivo de devolución:** un `requirements.txt` generado con `pip freeze` presentado
como `lockfile`. No lleva hashes, no distingue dependencias directas de transitivas
y es específico de la plataforma donde se ejecutó.

## Criterio 6 — El entorno se reconstruye desde cero

Esto lo demuestra el `job` del CI, que parte de una máquina limpia. Pero el
instructor debería hacerlo una vez a mano con un PR de muestra, porque es lo que
hará quien haga `peer review`:

```bash
cd /tmp && rm -rf verificacion
git clone <url-del-estudiante> verificacion && cd verificacion
make setup && make smoke && make test
```

## Criterio 7 — El ADR tiene contexto, decisión y consecuencias

Ejemplo completo: [`adr-000-stack.md`](adr-000-stack.md).
Referencias del repositorio, con la forma que se espera:
[ADR 001](../../../docs/adr/001-caso-guia-y-particiones.md) (particiones),
[ADR 002](../../../docs/adr/002-aliases-en-vez-de-stages.md) (registry),
[ADR 003](../../../docs/adr/003-umbrales-de-drift.md) (umbrales).

Rúbrica de este criterio, en orden de importancia:

| Señal | Qué significa |
|---|---|
| Las tres secciones existen y tienen contenido | mínimo |
| Hay al menos una alternativa **descartada con razón** | el estudiante consideró opciones |
| La razón no es "es el más popular" ni "el profesor lo usa" | la decisión es suya |
| **Hay una consecuencia negativa** | entendió que toda decisión cuesta algo |
| Las versiones están nombradas | el ADR se puede fechar y revisar |

La ausencia de consecuencias negativas es el fallo más común y el más informativo:
un ADR con solo ventajas no es un ADR, es una justificación escrita después.

## Criterio 8 — El `Makefile` es la interfaz única

Comprobación: los pasos del CI son `make <target>`, o los mismos comandos que el
`Makefile` ejecuta. Si el CI corre `pytest --cov ...` y el `Makefile` corre
`pytest -q`, hay dos definiciones de "los tests pasan".

En este repositorio el `Makefile` lo dice en su encabezado:

```
# Interfaz unica del repositorio. El CI usa exactamente estos mismos targets,
# de modo que "pasa en mi maquina" y "pasa en CI" significan lo mismo.
```

## Criterio 9 — Un solo formatter

```bash
grep -rn -i "black" pyproject.toml .pre-commit-config.yaml .vscode/ 2>/dev/null
```

Si aparece Black junto con `ruff format`, se devuelve con la explicación de
[`calidad.md`](../calidad.md) §2. Ojo también con `.vscode/settings.json`
commiteado: `"editor.defaultFormatter": "ms-python.black-formatter"` cuenta como
segundo formatter, porque se lo impone a todo el equipo.

## Criterio 10 — Sin secretos ni binarios grandes

```bash
git ls-files | grep -E '\.(pkl|bin|ubj|onnx|parquet|h5)$'   # vacío, o todo en LFS
git ls-files | grep -E '^\.env$'                            # vacío
ls .env.example                                             # existe
git lfs ls-files                                            # lo que sí está en LFS
uv run pre-commit run detect-private-key --all-files
uv run pre-commit run check-added-large-files --all-files
```

Si algo apareció, la conversación no es "bórralo": es **rota el secreto**. Un
`token` que estuvo en un commit público está comprometido para siempre, y borrarlo
en un commit posterior no lo saca del historial.

---

## Errores más frecuentes en los PR, por orden de frecuencia

1. **CI verde que no comprueba nada** — `continue-on-error` o `|| echo` heredados de
   un tutorial. Es el fallo nº 1 y el más peligroso, porque produce confianza
   injustificada.
2. **`uv.lock` sin commitear**, o commiteado en un commit distinto del
   `pyproject.toml`.
3. **`smoke_test.py` que no puede fallar** — imprime avisos y devuelve siempre 0.
4. **ADR sin consecuencias negativas.**
5. **Dos formatters** — casi siempre Black en el editor.
6. **Paquete sin `src/` layout** — funciona en local por el directorio de trabajo, y
   falla en CI con `ModuleNotFoundError`.
7. **Constantes duplicadas** — el mismo umbral en `train.py` y en `predict.py`. Es el
   bug que la sesión 1 previene y el que reaparece en la sesión 5.

---

## Tiempos del taller, para el instructor

El taller son 55 minutos y **no** alcanza para hacer los nueve puntos de cero. Lo
que se espera al final de la clase, en orden de prioridad:

| Prioridad | Puntos | Por qué |
|---|---|---|
| Imprescindible | 1, 2, 3 (paquete, `lock`, `Makefile`) | sin esto no se puede seguir el curso |
| En clase si da tiempo | 4, 5, 8 (`smoke`, `ruff`/`hooks`, CI) | son mecánicos con las plantillas |
| Tarea | 6, 7, 9 (LFS, tests, ADR) | requieren pensar; el ADR es el más valioso y el que más tiempo pide |

Recomendación: pedir el PR abierto **al final de la clase** aunque esté incompleto,
con la descripción diciendo qué falta. Un PR incompleto y declarado se revisa; uno
que llega tres días tarde y completo no enseña la disciplina de entregar.
