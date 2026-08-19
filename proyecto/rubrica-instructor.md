# Rúbrica del instructor — proyecto final

**Vale el 40 % de la nota del curso.** Esta rúbrica se publica al inicio, no al
final: no hay criterios secretos. Si un aspecto de tu proyecto no aparece en las
siete dimensiones de abajo, no se califica.

## Cómo se calcula la nota

Siete dimensiones. Cada una se puntúa de **1 a 5**.

```
nota = Σ (puntaje_dimensión / 5) × peso_dimensión
```

| Dimensión | Peso |
|---|---:|
| 1. Reproducibilidad | 15 |
| 2. Datos | 15 |
| 3. `Tracking` y `registry` | 15 |
| 4. `Pipeline` | 15 |
| 5. `Deployment` | 15 |
| 6. Monitoreo | 15 |
| 7. Ingeniería y documentación | 10 |
| **Total** | **100** |

Las anclas se publican para los niveles **1, 3 y 5**. Los niveles **2 y 4** son
intermedios: 2 = cumple lo de 1 y algo de 3; 4 = cumple todo lo de 3 y parte de 5.

Dos consecuencias del diseño de pesos que conviene entender:

- **Ninguna dimensión vale más del 15 %.** Siete dimensiones en nivel 3 (nota 60)
  supera holgadamente a dos en nivel 5 y cinco en nivel 1 (nota 43). La estrategia
  ganadora es cubrir todo a un nivel razonable, no perfeccionar una parte.
- **La calidad del modelo no es una dimensión.** Aparece indirectamente en
  "Datos" (¿el `baseline` es honesto?) y en `Tracking` (¿la métrica se reproduce?),
  pero un RMSE mejor no sube la nota.

## Qué mira el instructor

La columna "evidencia" de cada dimensión dice el **comando o archivo concreto** que
se ejecuta o se abre para asignar el puntaje. La calificación se hace en una máquina
limpia, clonando el repositorio, sin ayuda del autor.

---

## 1. Reproducibilidad — 15 %

**Evidencia:** `git clone` en una máquina limpia → `make setup` → `make smoke` →
`make train`. Se revisan `uv.lock`, `Makefile`, `.python-version`, `config.py` y la
presencia de semillas.

| Nivel | Ancla |
|---|---|
| **1** | No corre desde cero. Falta el `lockfile`, o hay rutas absolutas del autor, o el README pide pasos que no están documentados, o hay `pip install` dentro de un notebook. El instructor no logra ejecutar nada sin preguntar |
| **3** | Corre siguiendo el README. Hay `lockfile` commiteado y `Makefile` con los targets básicos. Requiere 1-2 intervenciones manuales (crear una carpeta, exportar una variable, ajustar un puerto) que el README no menciona. La métrica reportada se reproduce aproximadamente |
| **5** | `make setup && make smoke && make train` reproduce la métrica reportada **sin intervención manual**. Semillas explícitas pasadas a cada componente (no `np.random.seed` global). Particiones de datos fijas, nunca `datetime.now()`. `make smoke` diagnostica el entorno y sale con código ≠ 0 si algo falta. La tolerancia de reproducibilidad está declarada por escrito |

**Se penaliza aquí:** rutas absolutas del directorio personal del autor (`/Users/<nombre>/…` en macOS, `/home/<nombre>/…` en Linux, `C:\Users\<nombre>\…` en Windows),
`sys.path.append` para resolver imports, ausencia de `uv.lock`.

---

## 2. Datos — 15 %

**Evidencia:** `src/<paquete>/data/contract.py`, `tests/data/`, `docs/dataset-card.md`,
`data/raw/metadata.json`. Se ejecuta `make test`, y después se **corrompe un fixture
a propósito** y se vuelve a ejecutar: debe fallar.

| Nivel | Ancla |
|---|---|
| **1** | Sin validación. `pd.read_csv` directo al `fit`. `df.fillna(0)` sin justificar. `train_test_split(shuffle=True)` sobre datos con eje temporal. No hay `dataset card` o no menciona la licencia |
| **3** | Contrato de datos básico: tipos y rangos de las columnas principales, validado en algún punto del `pipeline`. `Split` temporal correcto. `Dataset card` con procedencia y licencia. Al menos un test de datos. Los nulos se tratan con una estrategia declarada |
| **5** | Contrato con ≥6 reglas **no triviales**, incluyendo al menos una relación entre columnas y un check de volumen. Validación en la frontera (`crudo` y `procesado`, con contratos distintos y el motivo explicado). ≥3 `fixtures` rotos con tests que verifican el **rechazo**: al corromper el fixture, el CI se pone rojo. Versionado por hash con `metadata.json` commiteado. `Dataset card` completa: unidades por columna, por qué hay nulos en cada una, población representada, sesgos, limitaciones. Las tres formas de `leakage` descartadas por escrito |

**Reglas triviales que no cuentan:** "la columna existe", "el tipo es `int`",
"no hay nulos" en una columna que nunca los tiene.

---

## 3. `Tracking` y `registry` — 15 %

**Evidencia:** UI de MLflow (o el `backend` equivalente) sobre el `tracking store`
del proyecto; `docs/model-card.md` y el script que la genera; el código de
entrenamiento.

| Nivel | Ancla |
|---|---|
| **1** | Métricas en `print`. El modelo es un `.pkl` en el repositorio, o se copia entre carpetas con `shutil.copytree`. No hay forma de saber qué datos ni qué parámetros produjeron el artefacto |
| **3** | `Runs` en MLflow con `params` y métricas. El mejor modelo está registrado. Se puede comparar visualmente entre corridas. Hay una `model card`, aunque esté escrita a mano |
| **5** | ≥20 `runs` comparables de una búsqueda estructurada (anidados: `parent` + `child` por `trial`). Modelo registrado con **alias** (`@champion`, `@candidate`) y `tags` (`validation_status`), no con `stages`. `Signature` e `input_example` presentes. El preprocesamiento va **dentro** del artefacto, no como archivo aparte. El modelo se carga por alias y **reproduce la métrica reportada**. `Model card` **generada por script** (`make model-card`), con métricas globales y por subgrupo |

**Se penaliza aquí:** `transition_model_version_stage` o `models:/<nombre>/Production`
(API deprecada desde MLflow 2.9, y el curso enseña aliases); `preprocessor.b` y
`model.pkl` como dos archivos que hay que mantener sincronizados a mano.

---

## 4. `Pipeline` — 15 %

**Evidencia:** el código del `flow`, la UI del orquestador, y **dos ejecuciones
consecutivas cronometradas** para verificar el `caching`.

| Nivel | Ancla |
|---|---|
| **1** | Script manual, o celdas de notebook que hay que correr en orden. Si falla en el paso 3, hay que empezar de cero. No hay registro de quién lo corrió ni con qué parámetros |
| **3** | `Flow` con `tasks` separadas que corre de punta a punta con un comando. Los pasos están bien delimitados (cargar, validar, preparar, entrenar, evaluar). Hay `logging` |
| **5** | ≥4 `tasks` con el grafo derivado de las dependencias de datos. `Retries` con `backoff` en las `tasks` de I/O (y el motivo del `backoff` explicado). `Caching` con `cache_key_fn` cuya efectividad **se mide**: la segunda ejecución es medible­mente más rápida y el número está reportado. `Artifacts` con la tabla de métricas junto a la corrida. `Deployment` con `schedule` visible en la UI. El `flow` registra el candidato y **NO lo promueve**: la promoción es del `gate` |

**Se penaliza aquí:** auto-promoción a producción en cada corrida (un modelo llega a
producción por el hecho de que el entrenamiento no lanzó excepciones);
`cron="*/2 * * * *"` reentrenando el modelo completo.

---

## 5. `Deployment` — 15 %

**Evidencia:** `docker compose up` → `curl /health` → `curl /predict`;
`docker run --rm --entrypoint sh <imagen> -c 'id -u'`; el `Dockerfile`; los tests de
API en el CI; `.github/workflows/`.

| Nivel | Ancla |
|---|---|
| **1** | Solo local. `uvicorn` a mano, o un notebook con predicciones. No hay contenedor, o el contenedor no arranca. La API devuelve `str(e)` al cliente. No hay tests |
| **3** | Contenedor que arranca y responde. Hay un `Dockerfile` y un endpoint (o un `batch`) que funciona. Instrucciones de uso en el README. Algún test de la API |
| **5** | Imagen reproducible: instala desde el `lockfile`, **multi-stage**, `.dockerignore`, **no corre como root** (verificado por un paso de CI que falla si el UID es 0), `healthcheck` que usa un binario que la imagen realmente trae. Carga el modelo desde el `registry` por alias, no un archivo copiado. Contrato de entrada validado con rangos que coinciden con el contrato de datos. `/health` reporta la **versión del modelo**. ≥4 tests de API en CI. CI completo (`lint` → tipos → tests → `build`) sin ningún paso con `|| true`, con **`gate` de promoción** y evidencia de un candidato rechazado |

**Se penaliza aquí:** `debug=True` en un servicio expuesto; `allow_origins=["*"]`
junto a `allow_credentials=True`; `HTTPException(detail=str(e))`; `latest` como
referencia de despliegue; `@app.on_event` (deprecado desde FastAPI 0.93).

---

## 6. Monitoreo — 15 %

**Evidencia:** el comando que genera el reporte de `drift` y el HTML resultante; el
`exit code` del check con y sin `drift`; `curl /metrics`; el JSON del `dashboard`;
`docs/politica-de-reentrenamiento.md`.

Esta dimensión era, en la versión anterior del proyecto, un solo `checkbox`
("proponer ideas de monitoreo"). Ahora pesa lo mismo que las demás y exige
entregables materiales.

| Nivel | Ancla |
|---|---|
| **1** | Solo ideas. Un párrafo en el README que dice "se podría monitorear con Evidently". Nada ejecutable |
| **3** | Un reporte de `drift` generado a mano (notebook o script suelto) comparando dos particiones, con el HTML en el repositorio. Hay un umbral, aunque sin justificar. Se menciona el reentrenamiento sin política escrita |
| **5** | Reporte de `drift` **generado desde el `pipeline`** y subido como `artifact`. Check con `exit code` ≠ 0 que se demuestra fallando con datos con `drift` y pasando sin él. Umbral **justificado por escrito**, con el tamaño del efecto y no solo el p-valor (y la explicación de por qué `p < 0.05` no alcanza con n grande). ≥3 métricas Prometheus en el servicio y `dashboard` versionado como JSON. Distinción explícita entre lo que mide Prometheus (el servicio) y lo que mide el reporte de `drift` (los datos). `docs/politica-de-reentrenamiento.md` que nombra `trigger`, datos, aprobador, mecanismo de `rollback` y qué queda registrado. `docs/riesgos.md` con 5 riesgos y su detección |

**Se penaliza aquí:** `drift` inventado con `numpy` en lugar de comparar dos
particiones reales; `ColumnMapping` de Evidently (eliminado en 0.7); alertas sin
destinatario ni acción esperada.

---

## 7. Ingeniería y documentación — 10 %

**Evidencia:** `make check`, `git log --oneline`, `docs/`, `git ls-files`, salida de
`gitleaks`.

| Nivel | Ancla |
|---|---|
| **1** | README mínimo. Sin `linter`, sin tests, sin CI (o con CI que no puede fallar). Commits del tipo "cambios", "fix", "asdf". Todo en un archivo, o carpetas que no significan nada. Artefactos binarios en el repositorio |
| **3** | `Linter`/`formatter` configurado y aplicado. `Pre-commit` instalado. CI que corre `lint` y tests. README que explica qué hace el proyecto y cómo ejecutarlo. Estructura de carpetas con sentido. Commits legibles |
| **5** | `Ruff` + `mypy` limpios (`make check` pasa). `Pre-commit` con `gitleaks` y `nbstripout`. CI verde y sin escapatorias. Cobertura razonable en los módulos que importan (no perseguir el 100 %). Docstrings que dicen **por qué**, no solo qué. ADRs con contexto / decisión / alternativas / consecuencias. `Model card`, `dataset card`, `api-contract`, política de reentrenamiento y riesgos, todos completos y coherentes entre sí. Commits atómicos con mensajes que explican el motivo. Notebooks sin `outputs` |

---

## Penalizaciones

Se aplican **sobre la nota final** y son acumulativas. Existen porque son fallas de
categoría distinta a "hacerlo a medias": son cosas que no deberían estar ahí.

| Falla | Penalización | Por qué es de otra categoría |
|---|---:|---|
| **Secreto real en el repositorio o en su historial** (llave de API, credencial de nube, token) | **−15** | No se arregla borrándolo en el commit siguiente: queda en el historial y hay que rotar la credencial. Es el único ítem que puede convertir un buen proyecto en un incidente |
| **El código no corre** en una máquina limpia tras seguir el README, y el autor no responde | **−10** | Un sistema que no se puede ejecutar no se puede evaluar |
| **Artefacto binario grande commiteado** (>10 MB: modelo, dataset, base de datos) | **−5** | Contradice directamente lo que enseña el curso, e infla el repositorio de forma permanente |
| **Notebooks con `outputs`** commiteados (imágenes en base64, rutas del autor) | **−3** | Ruido ilegible en el diff y fuga de información del entorno |
| **CI con pasos que no pueden fallar** (`\|\| true`, `\|\| echo`, `continue-on-error` sin justificar) | **−5** | Un pipeline que no puede fallar produce confianza injustificada, que es peor que no tener pipeline |
| **Rutas absolutas del autor** en código o configuración | **−3** | No rompe nada para el autor y rompe todo para el resto |
| **Auto-promoción a producción** sin `gate` | **−5** | Es el anti-patrón central que el curso corrige |
| **Entrega tardía** | −5 por día | Hasta 3 días; después no se recibe |
| **`Peer reviews` no entregados** | 0 en ese componente | No se compensa con el proyecto |

Todas las penalizaciones se notifican con la evidencia concreta (archivo y línea, o
comando y salida). Ninguna se aplica en silencio.

## Bonificaciones

Acotadas a **+5 en total**, sin importar cuántas se cumplan. El tope es a propósito:
la rúbrica premia cubrir bien las siete dimensiones, no acumular extras.

| Extra | Bonificación |
|---|---:|
| `Deployment` en la nube funcionando, con el costo estimado documentado y `teardown` ejecutado | +3 |
| ADR que documenta una decisión **revertida**, con qué salió mal y qué se aprendió | +2 |
| Tests de propiedades (`hypothesis`) sobre el contrato de datos o las features | +2 |
| Análisis de equidad por subgrupo que va más allá de reportar la métrica: identifica la causa y propone una mitigación | +2 |
| Versionado de datos con DVC o `lakeFS`, integrado al `pipeline` (no una demo aparte) | +2 |
| Instrumentación con LLMOps (`tracing` + `evals` en CI) si el proyecto incluye un LLM | +3 |

**No bonifica:** usar más herramientas, más modelos, más `notebooks`, o una
arquitectura más compleja de lo que el problema pide. La sobre-ingeniería no es un
extra; en la dimensión 7 puede costar puntos.

## Nota final sobre el criterio

Dos proyectos con la misma nota pueden verse muy distintos, y eso es correcto: la
rúbrica mide propiedades del sistema, no una lista de herramientas. Un proyecto con
un `pipeline` `batch` sin API puede sacar 5 en `Deployment` si el `batch` está bien
hecho, contenedorizado, trazable y testeado.

Lo que **no** se puede compensar: si el proyecto no corre, ninguna otra dimensión
tiene evidencia que evaluar.
