# Proyecto final — MLOps

**Universidad de Medellín · 8 sesiones · 70 % de la nota del curso**

| Documento | Para qué |
|---|---|
| Este archivo | Enunciado, requisitos del dataset, hitos, fechas y evaluación |
| [`rubrica-instructor.md`](rubrica-instructor.md) | **La rúbrica completa con la que se califica.** Léela antes de empezar, no al final |
| [`mvp-minimo-aprobable.md`](mvp-minimo-aprobable.md) | Checklist de lo mínimo para aprobar, si vas justo de tiempo |
| [`datasets-curados.md`](datasets-curados.md) | Datasets verificados que cumplen los requisitos duros |
| [`starter-template/`](starter-template/) | Scaffold funcional: cópialo y trabaja sobre él |
| [`peer-review-template.md`](peer-review-template.md) | Plantilla de la revisión entre pares |

---

## 1. Objetivo

Construir y operar un **sistema** de machine learning de punta a punta: un
repositorio del que otra persona pueda partir, reproducir tu métrica, levantar tu
servicio, entender por qué decidiste lo que decidiste y saber cuándo tu modelo
dejó de servir.

Cada sesión del curso agrega una capa a este mismo sistema. No es un trabajo que
empieza en la semana ocho: si lo intentas, se nota, y la rúbrica lo detecta en la
primera dimensión.

## 2. Qué NO es este proyecto

**No es una competencia de Kaggle.** La calidad del modelo pesa poco: no hay
puntos por un RMSE espectacular ni penalización por uno mediocre, siempre que sea
un modelo honesto (`split` temporal correcto, sin `leakage`, con un `baseline` de
referencia declarado). Un `XGBoost` con AUC 0.94 en un repositorio que no corre en
otra máquina saca peor nota que una regresión logística dentro de un sistema
reproducible, monitoreado y documentado.

Lo que se evalúa es el sistema: reproducibilidad, contratos de datos, `tracking` y
`registry`, `pipeline`, `deployment`, monitoreo, ingeniería y documentación. Siete
dimensiones, y ninguna es "qué tan bueno es el modelo".

**Tampoco es un proyecto de investigación.** No hace falta un problema novedoso.
Un problema aburrido y bien operado vale más que uno ambicioso a medias.

## 3. Requisitos duros del dataset

Elegir mal el dataset es la causa de la mitad de los proyectos flojos, y el error
casi siempre se descubre en la sesión 7, cuando ya no hay tiempo de cambiar.

Cada requisito tiene un por qué operativo, no formal:

| Requisito | Por qué |
|---|---|
| **Eje temporal explícito** (o justificación escrita si no lo tiene) | Sin eje temporal no hay `split` honesto, ni `drift`, ni reentrenamiento. Un proyecto sin esto **no puede cumplir la fase de monitoreo**, que vale 15 % de la rúbrica |
| **≥2 particiones separables** para simular referencia vs producción | Es el insumo del módulo de monitoreo: hay que comparar dos distribuciones reales, no inventar `drift` con `numpy` |
| **≤500 MB, descargable sin autenticación** | Quien te haga `peer review` tiene que poder reproducirlo. Un dataset detrás de un login, o de 8 GB, convierte tu proyecto en algo que nadie puede verificar |
| **≥3 features categóricas y ≥3 numéricas, con nulos reales** | Si no, el contrato de datos y el preprocesamiento son triviales: sin nulos no hay estrategia de imputación que discutir, y sin categóricas no hay categoría nueva en producción que detectar |
| **Métrica de negocio articulable** | El umbral de decisión, la matriz de costos y la política de reentrenamiento tienen que significar algo. "Maximizar `accuracy`" no es una métrica de negocio |
| **Licencia que permita uso educativo** | Requisito, no formalidad. Va en la `dataset card` con nombre exacto y URL |

**Cómo cumplirlos sin riesgo:** elige de [`datasets-curados.md`](datasets-curados.md).
Todos están verificados contra esta tabla, con fecha de verificación y con las
trampas conocidas anotadas.

**Si traes otro dataset:** perfecto, pero justifícalo contra esta tabla en la
`dataset card` del hito 1. Si un requisito no se cumple, dilo y explica cómo lo
compensas. Un requisito incumplido y declarado es manejable; uno escondido rompe la
fase de monitoreo.

> **Sobre el caso guía (NYC Green Taxi).** Puedes usarlo, pero tendrás mucha menos
> ayuda de la que parece: el repositorio del curso ya lo resuelve, así que copiar
> es trivial y aprender es cero. La rúbrica evalúa tu sistema, no tu capacidad de
> reproducir el nuestro. Recomendación: elige otro dataset y usa el caso guía como
> referencia de arquitectura.

## 4. Alcance mínimo del sistema

Al final, tu repositorio tiene que contener, y **funcionar**:

1. Un paquete Python instalable, con entorno reproducible (`uv.lock` commiteado) y
   `Makefile` como interfaz única.
2. Un contrato de datos ejecutable con ≥6 reglas no triviales, y tests que
   verifican que **rechaza** un dato roto.
3. Entrenamiento instrumentado con `experiment tracking`: `params`, métricas,
   `signature`, `input_example`, y ≥20 `runs` comparables.
4. Un modelo en el `model registry` referenciado por alias (`@champion`), con
   `model card` generada por script.
5. Un `pipeline` orquestado con `retries`, `caching`, `schedule` y `artifacts`, que
   registra el candidato y **no lo promueve**.
6. Un servicio: API contenedorizada que carga el modelo desde el `registry`, con
   contrato validado, o un `pipeline` `batch` que persiste predicciones junto con la
   versión del modelo. Con tests que corren en CI.
7. Un CI que no puede pasar por accidente, con un **`gate` de promoción** que
   rechaza un candidato peor (y la evidencia de que lo rechazó).
8. Monitoreo con entregable material: reporte de `drift` generado desde el
   `pipeline`, umbral justificado y política de reentrenamiento escrita.
9. Documentación: ADR del `stack`, `dataset card`, `model card`, contrato de la
   API, política de reentrenamiento, registro de riesgos.

Todo eso está andamiado en [`starter-template/`](starter-template/). El scaffold
arranca con el CI verde y los tests pasando; lo que falta son 33
`TODO(estudiante)` numerados, que son el trabajo real.

## 5. Hitos, fechas y definición de "hecho"

Las fechas son **relativas a la sesión**. El instructor publica las fechas
absolutas en el aula virtual al inicio del curso.

<!-- INSTRUCTOR: publicar aquí la tabla de fechas absolutas de la cohorte -->

| Hito | Entrega | Peso |
|---|---|---|
| **H1 — Dato y `baseline`** | S2 + 5 días | 5 % |
| **H2 — `Tracking`, `registry` y `pipeline`** | S4 + 5 días | 5 % |
| **H3 — `Deployment`, CI/CD y `gate`** | S6 + 5 días | 5 % |
| **Entrega final** | S8 + 10 días | 40 % (instructor) + 15 % (`peer review`) |

### Cada hito se entrega como Pull Request, no como zip

Abres un PR desde tu rama de trabajo hacia `main` de tu propio repositorio y pegas
el enlace en el aula virtual. La revisión llega como comentarios **en las líneas de
código**, que es donde sirven de algo. Un zip produce una nota; un PR produce
aprendizaje.

Requisitos del PR: título descriptivo, descripción que diga qué contiene y qué
falta, **CI verde**, y el enlace al `run` del CI.

---

### H1 — Dato y `baseline` (S2 + 5 días)

**Entregables**

- Propuesta del problema: qué se predice, para qué se usaría la predicción, quién
  decidiría distinto por tenerla.
- Métrica de negocio y métrica técnica, y la relación entre las dos.
- Dataset elegido, justificado contra la tabla de requisitos duros.
- `docs/dataset-card.md` completa: procedencia, licencia, esquema con unidades,
  nulos y por qué los hay, particiones, población representada, limitaciones.
- Contrato de datos con ≥6 reglas no triviales + 3 `fixtures` rotos y 3 tests que
  verifican que el contrato los rechaza.
- Descarga con verificación de hash y particiones fijas en `config.py`.
- EDA en `notebooks/01_eda.ipynb`, sin `outputs` commiteados.
- `Baseline` honesto con `split` temporal, y su métrica anotada en el README.
- ADR del `stack` (`docs/adr/000-stack.md`).

**Definición de "hecho"** — verificable, no opinable:

- [ ] `make setup && make smoke` sale OK en una máquina limpia.
- [ ] `uv.lock` está commiteado.
- [ ] `make test` pasa y el CI está verde en el PR.
- [ ] Si corrompes un `fixture` a propósito, el CI se pone **rojo**. Hazlo: ver un
      CI fallar es la mitad del aprendizaje de esta sesión.
- [ ] La `dataset card` nombra la licencia exacta con su URL.
- [ ] El `baseline` está reportado con el número, la partición y el comando que lo
      reproduce.
- [ ] El ADR no tiene `TODO` puestos.

---

### H2 — `Tracking`, `registry` y `pipeline` (S4 + 5 días)

**Entregables**

- Entrenamiento instrumentado: `params`, métricas, `artifacts`, `signature`,
  `input_example`.
- ≥20 `runs` comparables de una búsqueda de hiperparámetros, anidados.
- Mejor modelo registrado, con `tag` `validation_status=passed` y alias `@champion`.
- `docs/model-card.md` **generada por script**, no escrita a mano.
- `Pipeline` orquestado con ≥4 `tasks`, `retries` con `backoff` en la de red,
  `caching` en la de preparación de datos, un `artifact` con la tabla de métricas y
  un `deployment` con `schedule`.
- ADR del `trigger` de reentrenamiento: cuál eliges, con qué frecuencia y qué te
  costaría equivocarte.

**Definición de "hecho"**

- [ ] Existe un `run_id` cuya métrica se reproduce cargando el modelo **por
      alias**, dentro de una tolerancia que tú declaras.
- [ ] El modelo tiene `signature` e `input_example`, visibles en la UI.
- [ ] `make model-card` regenera la `model card`; el archivo no se edita a mano.
- [ ] La segunda ejecución del `pipeline` es **mediblemente** más rápida por
      `caching`. Se mide y se reporta el número, no se asume.
- [ ] El `deployment` aparece con su próxima ejecución programada.
- [ ] El `pipeline` registra el candidato y **no** mueve `@champion`.
- [ ] CI verde.

---

### H3 — `Deployment`, CI/CD y `gate` (S6 + 5 días)

**Entregables**

- API que carga el modelo desde el `registry` por alias, con `/health` que reporta
  la versión y contrato validado. (Alternativa válida: `pipeline` `batch` con
  persistencia y `model_version` por predicción.)
- `Dockerfile` reproducible: instala desde el `lockfile`, no corre como root,
  `healthcheck` que funciona de verdad.
- ≥4 tests de la API o del `batch`, corriendo en CI.
- CI completo: `lint` → tipos → tests → `build` de imagen. Ningún paso con
  `|| true`.
- `gate` de promoción implementado, con logs de la decisión.
- Secretos gestionados fuera del código.
- `docs/api-contract.md`.

**Definición de "hecho"**

- [ ] `docker compose up` levanta el servicio y `/health` responde con la versión
      del modelo.
- [ ] La imagen **no** corre como root, y hay un paso de CI que falla si lo hiciera.
- [ ] **Evidencia de un candidato rechazado por el `gate`**: el log del workflow
      donde el `gate` rechazó un modelo peor, y el del caso donde aceptó uno mejor.
      Los dos casos, no solo el feliz.
- [ ] `gitleaks` limpio en todo el historial.
- [ ] CI verde.

---

### Entrega final (S8 + 10 días)

Todo lo anterior consolidado, más la fase de monitoreo, que ahora tiene
entregables **materiales**. Esto reemplaza el antiguo "proponer ideas de
monitoreo", que era un solo `checkbox` para una fase entera:

1. **Reporte de `drift` generado desde el `pipeline`**, no a mano en un notebook.
   Referencia vs producción simulada, guardado como HTML y subido como `artifact`
   del CI o del orquestador.
2. **Umbral justificado por escrito.** Qué fracción de columnas con `drift`
   dispara la alerta, por qué ese número, y por qué `p < 0.05` no alcanza como
   criterio (con n grande todo sale significativo). El umbral vive en `config.py`;
   la justificación, en `docs/politica-de-reentrenamiento.md`.
3. **Check de `drift` con `exit code`**: un comando que sale ≠ 0 cuando el `drift`
   supera el umbral y = 0 cuando no. Se demuestra que hace las dos cosas.
4. **≥3 métricas Prometheus** en el servicio y un `dashboard` versionado como JSON
   en el repositorio. Prometheus mide el **servicio** (latencia, errores,
   `throughput`); el reporte de `drift` mide los **datos**. Son dos preguntas
   distintas y hacen falta las dos.
5. **`docs/politica-de-reentrenamiento.md`** (1 página): `trigger`, datos que se
   usan, quién aprueba, cómo se hace `rollback`, qué queda registrado.
6. **`docs/riesgos.md`**: 5 riesgos del sistema con mecanismo, impacto, mitigación
   implementada y forma de detección; más la clasificación tentativa bajo el
   AI Act.

**Además**

- README que permita a otra persona reproducir todo desde cero.
- **Demo de 8 minutos** (grabada o en vivo): el problema, el sistema corriendo, y
  una cosa que no funcionó y qué aprendiste de eso. Los 8 minutos son un límite,
  no una meta.
- 2 `peer reviews` completados (ver
  [`peer-review-template.md`](peer-review-template.md)).

**Definición de "hecho"**

- [ ] `make setup && make smoke && make train` reproduce la métrica que reportas,
      sin intervención manual, en una máquina que no es la tuya.
- [ ] `make smoke` es **un solo comando** que verifica el entorno completo. Es lo
      primero que corre tu revisor.
- [ ] El reporte de `drift` se genera con un comando y queda como `artifact`.
- [ ] El check de `drift` falla con datos con `drift` y pasa sin él, demostrado.
- [ ] `/metrics` expone las métricas y el `dashboard` las grafica.
- [ ] La política de reentrenamiento nombra `trigger`, aprobador y mecanismo de
      `rollback`.
- [ ] Ningún secreto en el repositorio ni en su historial.
- [ ] CI verde en la rama entregada.
- [ ] Tus 2 `peer reviews` están enviados.

## 6. Evaluación

| Componente | Peso | Quién evalúa | Cómo |
|---|---|---|---|
| Talleres de sesión (8, se descarta el más bajo) | 30 % | CI | Verificados automáticamente: si el CI pasa, el taller cuenta |
| Hitos del proyecto (H1, H2, H3) | 15 % | Instructor | 5 % cada uno, contra la definición de "hecho" del hito |
| **Proyecto final — instructor** | **40 %** | Instructor | [`rubrica-instructor.md`](rubrica-instructor.md), 7 dimensiones |
| Proyecto final — `peer review` recibido | 10 % | Compañeros | Promedio recortado: se descartan la nota más alta y la más baja |
| Participación en `peer review` | 5 % | Instructor | Binario: completaste tus **2** revisiones (5 %) o no (0 %) |

Tres cosas sobre esto:

- **La rúbrica del instructor está publicada.** No hay criterios secretos. Si un
  aspecto de tu proyecto no aparece en las siete dimensiones, no se califica.
- **El `peer review` recibido usa promedio recortado**, no promedio simple: un
  revisor generoso y uno duro se cancelan.
- **La participación es binaria y no negociable.** Revisar código ajeno es donde se
  aprenden los patrones que no se te ocurrieron. Es también la parte más fácil de
  ganar de todo el curso.

## 7. `Peer review`

**Cada persona** (no cada grupo) revisa **2 proyectos**. La asignación se publica
por el canal del curso cuando se cierren las entregas.

El procedimiento completo, con las anclas de puntuación y el tiempo real que toma,
está en [`peer-review-template.md`](peer-review-template.md).

Una nota para el autor, no para el revisor: **tu nota de `peer review` depende
mucho de que `make smoke` funcione.** Un revisor que pasa 40 minutos peleando con
tu instalación llega al modelo de mal humor y sin tiempo. Reducir la instalación a
un comando es la inversión con mejor retorno de todo el proyecto.

## 8. Consejos honestos

1. **Empieza por el dato, no por el modelo.** El 80 % de los problemas del
   proyecto van a ser problemas de datos. Los 20 minutos que ahorras eligiendo el
   dataset rápido los pagas con intereses en la sesión 7.
2. **Un MVP completo antes que seis piezas a medias.** Ver
   [`mvp-minimo-aprobable.md`](mvp-minimo-aprobable.md). La rúbrica premia siete
   dimensiones en nivel 3 muy por encima de dos en nivel 5 y cinco en nivel 1.
3. **Commitea `uv.lock` el primer día.** Es el archivo que más se olvida y el que
   más cuesta olvidar.
4. **Escribe la decisión cuando la tomas, no al final.** Reconstruir a posteriori
   por qué elegiste Prefect sobre Airflow produce una racionalización, no un ADR.
5. **Haz que el CI falle a propósito una vez.** Corrompe un `fixture`, mira el
   rojo, arréglalo. De un CI que nunca has visto fallar no sabes si funciona.
6. **No sobre-ingenierices.** Un `feature store` en un proyecto individual es
   sobre-ingeniería, y la rúbrica no da puntos por complejidad. Da puntos por
   decisiones justificadas, y "no lo necesito, y aquí está por qué" es una decisión
   excelente.
7. **Lo que no funcionó vale nota.** Un riesgo declarado, una limitación admitida y
   un ADR que dice "esto salió mal y lo revertí" leen como madurez técnica. Un
   proyecto donde todo salió perfecto lee como un proyecto que no se probó.

## 9. Recursos

- Arquitectura de referencia y ejemplos ejecutables: el repositorio del curso
  (`src/taxi/`, `scripts/promote.py`, `Makefile`, `.github/workflows/ci.yml`,
  `docker-compose.yml`, `observabilidad/`).
- Material por sesión: `sesiones/s01-reproducibilidad/` … `sesiones/s08-llmops/`.
- Decisiones de diseño del caso guía: `docs/adr/`.
- Fuentes generales de datasets, si ninguno de los curados te sirve:
  [UCI](https://archive.ics.uci.edu/datasets),
  [OpenML](https://www.openml.org/search?type=data),
  [Google Dataset Search](https://datasetsearch.research.google.com/),
  [AWS Open Data](https://registry.opendata.aws/),
  [awesome-public-datasets](https://github.com/awesomedata/awesome-public-datasets).
  Verifica cualquier candidato contra la tabla de requisitos duros **antes** de
  enamorarte de él.
