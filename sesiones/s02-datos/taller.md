# Taller S02 — Poner el contrato de datos a fallar

**Duración:** 55 min en clase. Se entrega en clase.
**Sobre:** **tu propio** repositorio de proyecto, no el del curso.
**Entregable:** un PR hacia `main` de tu repositorio, con el CI **verde** corriendo los
tests de datos, y el enlace al `run` en la descripción.

---

## Contexto

Tu repositorio ya es reproducible (S01): entorno declarado, `lockfile` commiteado,
`Makefile`, CI que puede fallar. Hoy le añades la capa que la S01 **no** cubre: qué
pasa cuando el **dato** cambia.

El objetivo **no** es "usar Pandera". Es que tu `pipeline` **se niegue a entrenar** con
un dato que cambió de significado, y que exista una prueba automática de que ese
mecanismo está encendido.

Recuerda el resultado de la sesión: un cambio de unidades no lanza excepciones, no
produce nulos, no cambia tipos, y degrada la métrica lo justo para que nadie lo note.
Tu `ruff`, tu `mypy` y tus tests de la S01 no lo detectan. Hoy construyes lo que sí.

> **Este taller es casi literalmente el [hito 1 del
> proyecto](../../proyecto/README.md), que se entrega 5 días después de esta sesión.**
> No es trabajo desechable: es el hito, menos la propuesta del problema y la métrica de
> negocio. Aprovéchalo.

---

## 1. Un contrato con ≥ 6 reglas **no triviales**

Sobre el `dataset` de **tu** proyecto. Pandera o Great Expectations Core 1.x, a tu
elección (comparativa en el [README](README.md) §5).

**Qué cuenta como regla no trivial:** una que codifique conocimiento del dominio o del
proveedor. **Qué no cuenta:** `pa.Field()` sin ningún argumento, o comprobar que una
columna existe.

Y el requisito que ordena todo: las 6 reglas tienen que cubrir **los tres niveles**.

| Nivel | Mínimo exigido | Ejemplos válidos |
|---|---|---|
| **1. Por fila** | ≥ 2 reglas | rango de un ID categórico, `nullable=False` en una columna obligatoria, `isin` de un conjunto cerrado, `str_matches` de un formato |
| **2. Por distribución** | ≥ 2 reglas | **la fracción** de filas fuera de rango; volumen mínimo del lote; cardinalidad máxima de una categórica; fracción máxima de nulos |
| **3. Entre columnas** | ≥ 2 reglas | una relación de orden entre dos fechas; un ratio implícito plausible; una suma que tiene que cuadrar con un total |

**El nivel 2 es el que casi nadie escribe y el que atrapa los incidentes reales.** Si
tu contrato solo tiene reglas por fila, un cambio sistemático de escala se te pasa
entero: cada fila individual sigue siendo válida.

Cada regla lleva un **comentario o `docstring` de una línea que diga qué protege**. Una
regla sin justificación es una regla que alguien relajará en seis meses para desbloquear
un `pipeline`.

Referencia: [`src/taxi/data/contract.py`](../../src/taxi/data/contract.py) tiene los
tres niveles con su razonamiento escrito.

## 2. Cotas anchas por fila, calibradas con **tus** datos

**No copies los umbrales del curso.** El `0,003` del caso guía sale de haber medido
`0,054 %` en datos reales. El tuyo saldrá de otro número.

Entrega, en el PR o en un ADR, una tabla con **tres columnas por regla de nivel 2**:

| Regla | Valor medido en tus datos | Umbral que fijaste | Margen |
|---|---|---|---|

Y la comprobación que hay que hacer explícitamente: **tu contrato tiene que pasar sobre
tu partición real completa.** Si falla, no relajes la regla sin pensar: decide si el
problema es la regla (demasiado estricta por fila) o el dato (sistemático, y entonces la
regla está haciendo su trabajo).

> Un contrato que falla con datos buenos se desactiva en la primera semana. Uno que
> acepta cualquier cosa no protege nada. El taller evalúa que hayas encontrado el punto
> intermedio **midiendo**, no adivinando.

## 3. Tres `fixtures` rotos, y sus tests

Tres `fixtures` que **generen** datos rotos en código (no CSV commiteados: mira el
razonamiento en [`tests/conftest.py`](../../tests/conftest.py)), cada uno con un
`docstring` que diga **qué fallo real reproduce**.

Los tres tienen que cumplir una propiedad: **ninguno debe lanzar una excepción por sí
mismo.** Los tres tienen que poder entrenar un modelo y producir una métrica plausible.
Si tu `fixture` roto hace que `pandas` lance un error, no estás demostrando nada — eso
ya lo atrapaba el `try/except`.

Ideas que sí valen, adaptadas a tu dominio:

- un **cambio de unidades o de escala** en una columna numérica;
- una **categoría nueva** que no existía en entrenamiento;
- **nulos** en una columna obligatoria (descarga cortada, `join` sin pareja);
- un **`timestamp` en el futuro**;
- una columna **desplazada** una posición (un error de `parsing` de CSV clásico).

Más los tests:

```python
@pytest.mark.parametrize(
    ("fixture", "motivo"),
    [
        ("df_en_kilometros", "cambio de unidades"),
        ("df_categoria_nueva", "categoria no vista en fit"),
        ("df_con_nulos", "nulos en columna obligatoria"),
    ],
)
def test_el_contrato_rechaza_los_fixtures_rotos(request, fixture, motivo):
    with pytest.raises(ERRORES_CONTRATO):
        validar(request.getfixturevalue(fixture))
```

**Y el cuarto test, el que decide la nota: el control negativo.**

```python
def test_el_contrato_no_inventa_fallos():
    """Varios lotes independientes de datos BUENOS pasan el contrato."""
    for semilla in (1, 2, 3):
        validar(generar_validos(semilla=semilla))
```

Sin él, "mi contrato detecta el fallo" no demuestra nada: un contrato que rechaza
**todo** también lo detecta.

## 4. Descarga con hash y particiones fijas

En tu `config.py`:

- las particiones **declaradas como constantes**, fijas y del pasado. **Nunca
  `datetime.now()`**;
- la semilla, explícita;
- la descarga registra **SHA-256, URL, tamaño, fuente y licencia** en un
  `metadata.json` **que sí se commitea** (cuidado con un `.gitignore` que ignore
  `*.json` globalmente: es un bug real de este repositorio);
- si el hash registrado y el actual no coinciden, se **avisa fuerte**: el proveedor
  republicó el archivo y tus métricas históricas ya no son comparables.

Si tu `dataset` no se descarga (te lo dieron una vez), sirve igual: registra el hash del
archivo que tienes y su procedencia. Lo que se evalúa es que puedas responder *"¿es
este el mismo dato con el que medí?"*.

Referencia: [`src/taxi/data/loaders.py`](../../src/taxi/data/loaders.py), §2 de
[`versionado-de-datos.md`](versionado-de-datos.md).

## 5. `Split` temporal (o la justificación escrita)

**Si tu `dataset` tiene eje temporal:** un `split` por corte de fecha, con las
particiones declaradas en `config.py`, y un `holdout` que **no** se usa para
seleccionar nada. Y `TimeSeriesSplit` en la validación cruzada, no `KFold(shuffle=True)`.

Entrega la medición: el RMSE (o tu métrica) con `TimeSeriesSplit` **y** con
`KFold(shuffle=True)` sobre los mismos datos, y una frase interpretando la diferencia.

**Si tu `dataset` NO tiene eje temporal:** escribe la justificación, en tres puntos:

1. por qué no lo tiene;
2. qué usas en su lugar para que `train` y `test` sean independientes (¿agrupación por
   entidad con `GroupKFold`? ¿estratificación?);
3. **cómo vas a simular referencia vs producción en la sesión 7**, porque sin dos
   particiones separables no puedes medir `drift` y eso vale un 15 % de la rúbrica del
   proyecto.

El punto 3 es el importante: un `dataset` sin eje temporal no descalifica tu proyecto,
pero **descubrirlo en la sesión 7 sí lo hunde**.

Además, y aunque tu `split` sea correcto: **la tabla de disponibilidad temporal por
feature**, una fila por feature, con el instante en que su valor queda disponible. Es
la que detecta `leakage` sin entrenar nada. Plantilla en
[`dataset-card.md`](dataset-card.md) §7.

## 6. `dataset-card.md`

En `docs/dataset-card.md` de tu repositorio. Usa
[`dataset-card.md`](dataset-card.md) como plantilla. Las cinco secciones que se
revisan:

1. **procedencia y licencia** con nombre exacto y URL, más el hash de tus particiones;
2. **esquema con unidades** por columna;
3. **nulos por columna**, distinguiendo el estructural del fallo de captura, con la
   decisión escrita;
4. **población representada y ≥ 3 sesgos conocidos**, con evidencia medida. *"No conozco
   sesgos"* no es una respuesta aceptable para ningún `dataset` real;
5. **disponibilidad temporal por feature** (la tabla del punto 5).

## 7. El CI corre los tests de datos

Tu workflow tiene que ejecutar los tests de datos y **poder fallar**:

```yaml
      - run: uv run pytest tests/data -q
```

Sin `continue-on-error`, sin `|| true`, sin `|| echo`. Y los tests de datos **no deben
necesitar red**: por eso los `fixtures` se generan en código.

---

## Criterios de aceptación

Se revisan en el PR, en este orden. Cada uno es una comprobación, no una opinión.

| # | Criterio | Cómo se verifica |
|---|---|---|
| 1 | El contrato tiene **≥ 6 reglas no triviales**, con **≥ 2 de cada nivel** | se leen. Cada regla tiene su justificación de una línea. `pa.Field()` vacío no cuenta |
| 2 | El contrato **pasa** sobre tu partición real completa | un comando en el PR que valide el lote real y salga con exit code 0 |
| 3 | **3 `fixtures` rotos**, generados en código, y **3 tests** que verifican que el contrato los rechaza | `pytest tests/data -q` en verde, con los tres tests nombrados |
| 4 | Ninguno de los `fixtures` rotos lanza excepción **por sí mismo** | los tres entrenan un modelo y producen una métrica. Si uno rompe `pandas`, no demuestra nada |
| 5 | **Control negativo**: el contrato acepta ≥ 3 lotes independientes de datos buenos | el test existe y pasa. **Sin este criterio, el 3 no vale nada** |
| 6 | Hay **≥ 1 check de nivel 2** (distribución) y está **calibrado con tus datos** | la tabla del punto 2, con el valor medido, el umbral y el margen |
| 7 | **Descarga con hash**: `metadata.json` con SHA-256, URL, fuente y licencia, **commiteado** | `git ls-files \| grep metadata.json` y `cat` del archivo |
| 8 | **Particiones fijas** en `config.py`, sin `datetime.now()` | `grep -rn "datetime.now\|date.today" src/` no aparece en la selección de particiones |
| 9 | **`Split` temporal** implementado, o la justificación escrita de 3 puntos | el código, o el documento con los tres puntos incluido el de la S07 |
| 10 | La **medición** `TimeSeriesSplit` vs `KFold(shuffle=True)` | las dos métricas en el PR, con una frase interpretándolas |
| 11 | **`docs/dataset-card.md`** con las cinco secciones | se lee. Sin `TODO` sin rellenar |
| 12 | La tabla de **disponibilidad temporal por feature** | una fila por feature, en la `dataset card` |
| 13 | El **CI corre los tests de datos** y puede fallar | el `job` existe, no tiene `continue-on-error`, y el `run` está enlazado |

### Autocomprobación antes de abrir el PR

```bash
uv run pytest tests/data -q          # los tests de datos, sin red
uv run ruff check .
uv run pre-commit run --all-files
git ls-files | grep -c metadata.json # >= 1
ls docs/dataset-card.md
grep -rn "datetime.now" src/ | grep -i partic   # tiene que estar vacío
```

Y la prueba que de verdad decide, porque es lo que hará tu revisor:

```bash
uv run python -c "
# tu contrato, contra tu lote real completo
from miproyecto.data.contract import validar_crudos
from miproyecto.data.loaders import descargar
validar_crudos(cargar_lote_real())
print('el contrato pasa sobre el dato real')
"
```

---

## Si acabas antes

1. **Mide el límite de tu contrato**, como hace la §4 del [README](README.md): ¿a
   partir de qué factor de escala tu contrato deja de detectar el cambio? Es el
   ejercicio más valioso del taller, porque el resultado suele ser incómodo.
2. Añade un **check de nivel 3** más ambicioso: una relación entre tres columnas.
3. Deja el contrato como **paso del `pipeline` con `exit code`**, no solo como test:
   `python -m miproyecto.data.validar && echo $?`.
4. Escribe el **ADR de tu estrategia de versionado de datos**, contra las cinco
   preguntas de [`versionado-de-datos.md`](versionado-de-datos.md) §6. Si tu respuesta
   es "hash + partición inmutable y nada más", **defiéndelo**: es una respuesta
   correcta y bien argumentada vale más que un `lake` innecesario.
5. Adelanta la propuesta del problema y la métrica de negocio del
   [hito 1](../../proyecto/README.md). Con eso, el hito queda hecho.

---

## Errores que van a aparecer, con su causa

| Síntoma | Causa habitual |
|---|---|
| El contrato falla sobre tu partición real | cotas por fila demasiado estrictas. Es el bug del curso: `trip_distance <= 100` por fila fallaba por 37 filas de 68.211. Mueve la señal al nivel 2 |
| El contrato no detecta **nada** de lo que le metes | solo tiene reglas de nivel 1, o los rangos son tan anchos que aceptan cualquier cosa |
| Tus `fixtures` rotos lanzan `KeyError` o `ValueError` de `pandas` | están rotos de forma **ruidosa**. El punto del ejercicio son los fallos **silenciosos** |
| `pytest tests/data` necesita red | estás leyendo el `dataset` real en un test. Genera los datos en código |
| `FutureWarning` al importar Pandera | usaste `import pandera as pa` para clases de `pandas`. Es `import pandera.pandas as pa` |
| `AttributeError: SchemaModel` | fue renombrado a `DataFrameModel` y el nombre viejo se eliminó |
| Un `snippet` de Great Expectations no ejecuta | es de la API 0.18. GX Core 1.x reorganizó el modelo por completo |
| `TypeError: mean_squared_error() got an unexpected keyword argument 'squared'` | el parámetro se **eliminó** en `scikit-learn` 1.6. Usa `root_mean_squared_error` |
| Tu métrica con `KFold(shuffle=True)` es mejor y la usas para reportar | es el `leakage` del punto 5. Reporta la del `split` temporal |
| `metadata.json` no aparece en `git ls-files` | un `.gitignore` con `*.json` global. Añade `!**/metadata.json` |
| El CI verde con los tests de datos rotos | `continue-on-error` o `|| true` en el `step` |

---

Solución de referencia: [`_soluciones/`](_soluciones/). **No la abras antes de
intentarlo**: el valor está en el intento, y con la solución delante el intento no
ocurre.
