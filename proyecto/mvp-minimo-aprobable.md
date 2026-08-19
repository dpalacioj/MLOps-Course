# MVP mínimo aprobable

Una página para el caso realista: se acaba el tiempo y hay que decidir dónde
ponerlo.

**La aritmética que hay que entender.** La nota del instructor es
`Σ (puntaje/5 × peso)` sobre siete dimensiones de 15, 15, 15, 15, 15, 15 y 10
puntos. Eso significa:

| Estrategia | Cuenta | Nota |
|---|---|---:|
| Las 7 dimensiones en nivel 3 | 0.6 × 100 | **60** |
| 2 dimensiones de peso 15 en nivel 5, las otras 5 en nivel 1 | 30 + 0.2 × 70 | 44 |
| 4 dimensiones en nivel 4 (incluida la de peso 10), las otras 3 en nivel 1 | 0.8 × 55 + 0.2 × 45 | 53 |
| 6 dimensiones en nivel 3 y monitoreo abandonado en nivel 1 | 0.6 × 85 + 0.2 × 15 | 54 |

**Cubrir las siete a nivel 3 gana siempre.** Ninguna dimensión vale más del 15 %, así
que perfeccionar una a costa de abandonar otra es matemáticamente una mala apuesta.
Y hay una asimetría adicional: si el proyecto no corre, las otras seis dimensiones no
tienen evidencia que evaluar.

Corolario útil: **subir una dimensión de nivel 1 a nivel 3 vale 6 puntos** si pesa 15
(y 4 si pesa 10). Subirla de 3 a 5 vale otros 6. El primer tramo es mucho más barato
en horas que el segundo.

---

## El checklist

Cada ítem es verificable con un comando o abriendo un archivo. Si puedes marcar todo
lo de abajo, tienes un proyecto aprobado y completo. Nada de esto exige nivel 5.

### 0. Antes que nada (bloquea todo lo demás)

- [ ] `git clone` en una carpeta limpia + `make setup` + `make smoke` → **OK**
- [ ] `uv.lock` está commiteado
- [ ] `make test` pasa
- [ ] El CI está verde
- [ ] `grep -rn "/Users/\|C:\\\\Users" .` no devuelve nada
- [ ] No hay `.env` ni credenciales en el repositorio ni en su historial

> Si algo de esta sección falla, arréglalo antes de tocar cualquier otra cosa. Es la
> única sección que puede llevar la nota a cero por sí sola.

### 1. Reproducibilidad → nivel 3

- [ ] `Makefile` con `setup`, `smoke`, `train`, `test`, `lint`
- [ ] El README dice, en orden, los comandos exactos para reproducir la métrica
- [ ] Semillas explícitas en el código
- [ ] Particiones de datos fijas en `config.py`, sin `datetime.now()`

### 2. Datos → nivel 3

- [ ] Contrato de datos con tipos y rangos de las columnas principales
- [ ] Se valida en el `pipeline`, no solo en un notebook
- [ ] `Split` **temporal** (o justificación escrita de por qué no aplica)
- [ ] Al menos 1 test de datos que verifica que el contrato **rechaza** un dato roto
- [ ] `docs/dataset-card.md` con procedencia y **licencia con su URL**
- [ ] La estrategia para los nulos está declarada por escrito

### 3. `Tracking` y `registry` → nivel 3

- [ ] MLflow (o equivalente) registrando `params` y métricas
- [ ] Más de un `run`, comparables en la UI
- [ ] El mejor modelo está **registrado** en el `registry`
- [ ] Se referencia por **alias** (`@champion`), no por `stage` ni por ruta de archivo
- [ ] `docs/model-card.md` existe (a mano ya alcanza para nivel 3)

### 4. `Pipeline` → nivel 3

- [ ] Un `flow` con `tasks` separadas: cargar → validar → preparar → entrenar → evaluar
- [ ] Corre de punta a punta con **un comando**
- [ ] Tiene `logging`
- [ ] **No promueve** el modelo automáticamente

### 5. `Deployment` → nivel 3

- [ ] Un `Dockerfile` que construye y arranca
- [ ] Un endpoint que responde (o un `batch` que persiste predicciones)
- [ ] `/health` responde
- [ ] Instrucciones de uso en el README
- [ ] Al menos 1 test de la API o del `batch` corriendo en CI

### 6. Monitoreo → nivel 3

Esta es la dimensión que la gente abandona, y es la que más barato sube la nota:
pasar de 1 a 3 aquí vale 6 puntos por unas dos horas de trabajo.

- [ ] Un reporte de `drift` comparando dos particiones reales, con el HTML en el
      repositorio
- [ ] Un umbral declarado en `config.py`
- [ ] `docs/politica-de-reentrenamiento.md`, aunque sea corta, que nombre el
      `trigger` y el mecanismo de `rollback`

### 7. Ingeniería y documentación → nivel 3

- [ ] `ruff check` limpio
- [ ] `pre-commit` instalado y funcionando
- [ ] CI que corre `lint` y tests, **sin** ningún `|| true`
- [ ] README que explica qué hace el proyecto y cómo ejecutarlo
- [ ] Estructura de carpetas con sentido
- [ ] Notebooks **sin** `outputs`
- [ ] `docs/adr/000-stack.md` completo, sin `TODO` puestos

---

## Orden en el que hacerlo, si vas contra el reloj

1. **Sección 0.** No es negociable y es lo más rápido.
2. **Monitoreo a nivel 3.** Es la dimensión con peor relación esfuerzo/puntos entre
   los proyectos reales: casi todo el mundo la deja en 1, y subirla cuesta dos horas.
3. **Datos a nivel 3.** El contrato con rangos de negocio y un test de rechazo es
   media hora de trabajo y vale 6 puntos sobre el nivel 1.
4. **Documentación.** ADR, `dataset card` y política de reentrenamiento son texto: se
   escriben en una tarde y valen 10 + parte de otras dos dimensiones.
5. **Lo que falte de `pipeline` y `deployment`.**
6. **Recién entonces**, si sobra tiempo, subir alguna dimensión de 3 a 5.

## Lo que NO hay que hacer para aprobar

Nombrarlo importa, porque es donde se pierde el tiempo:

- **Un modelo mejor.** La calidad del modelo no es una dimensión de la rúbrica. Un
  `baseline` honesto y bien documentado puntúa igual que un `XGBoost` afinado.
- **Búsqueda de hiperparámetros exhaustiva.** Para nivel 3 en `tracking` bastan unos
  cuantos `runs` comparables. Los 20 `runs` anidados son para nivel 5.
- **Despliegue en la nube.** Es una bonificación acotada (+3, con tope global de +5),
  no un requisito. Local con `docker compose` alcanza para nivel 5 en `deployment`.
- **Herramientas adicionales.** Un `feature store`, Kubernetes o un segundo
  orquestador no suben ninguna dimensión. Justificar por escrito **por qué no los
  usas** sí cuenta en la dimensión 7.
- **Más notebooks.** Uno de EDA es suficiente. Tres notebooks con lógica dentro bajan
  la nota de ingeniería.

## Lo que sí conviene admitir por escrito

Un `TODO` declarado en el README con su motivo lee como criterio; el mismo hueco sin
mencionar lee como descuido. Ejemplos que funcionan:

> "No implementé métricas de subgrupo en el `gate` porque mi dataset no tiene una
> categórica con suficiente muestra por grupo (el mayor tiene 40 filas). El código
> del `gate` está preparado para recibirlas; lo que falta es el dato."

> "La búsqueda de hiperparámetros quedó en 8 `runs` en lugar de 20 por tiempo. Los 8
> están anidados y comparables, y el script acepta `--trials` para ampliarla."

Y un recordatorio de la rúbrica: **lo que no funcionó vale nota.** Un ADR que
documenta una decisión revertida, con qué salió mal y qué aprendiste, bonifica +2.
Un proyecto donde todo salió perfecto lee como un proyecto que no se probó.
