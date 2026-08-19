# Peer review — plantilla

**Tiempo:** ~25 minutos de revisión, **más el tiempo de instalación**. Ese segundo
tiempo no depende de ti: depende de que el autor haya reducido la instalación a un
comando. Si te toma 40 minutos instalar, eso **es** un hallazgo de la sección 1 y
así hay que reportarlo.

**Cuántos:** cada persona revisa **2 proyectos**. No es por grupo: es por persona.

**Por qué lo haces:** al revisar código ajeno aprendes patrones, errores comunes y
soluciones que no se te habían ocurrido. Es la parte con mejor relación
aprendizaje/tiempo del curso, y vale un 5 % binario de tu nota.

---

## Antes de empezar

```bash
git clone <repo-del-proyecto-asignado>
cd <repo>
make setup      # el autor debe haber commiteado uv.lock
make smoke      # UN comando. Esto verifica que el entorno quedó bien
```

**Regla:** ejecuta `make smoke`. **No instales a mano.** Si el proyecto no tiene un
`make smoke` (o equivalente de un comando), no lo compenses reconstruyendo el
entorno por tu cuenta: anótalo en la sección 1 y sigue con lo que sí puedas revisar.
El objetivo es que el autor aprenda que su instalación tiene que funcionar, y
compensárselo le quita esa lección.

**Si algo falla, no te quedes ahí.** Reporta el error exacto y evalúa el resto
leyendo el código. Un proyecto que no corre puede tener un contrato de datos
excelente, y eso también hay que verlo.

---

## Cómo puntuar

Cada sección se puntúa de **1 a 5** con anclas escritas para 1, 3 y 5. Los niveles 2
y 4 son intermedios (2 = lo de 1 y algo de 3; 4 = todo lo de 3 y parte de 5).

Puntúa **lo que verificaste**, no lo que supones. Si no pudiste verificar una
sección, márcala como "no verificable" y di por qué; eso vale más que un número
inventado.

---

## Datos de la revisión

- **Revisor:** [tu nombre]
- **Proyecto revisado:** [autor o grupo]
- **Repositorio:** [enlace]
- **Commit revisado:** [salida de `git rev-parse --short HEAD`]
- **Fecha:** [fecha]
- **Sistema operativo del revisor:** [Windows / macOS / Linux]
- **Tiempo real de instalación:** [minutos]

---

## 1. Reproducibilidad

**Comandos que ejecutaste** (los reales, con la salida relevante):

```bash

```

**Anclas**

| Nivel | Qué observaste |
|---|---|
| **1** | No pude ejecutar nada. Falta el `lockfile`, o hay rutas absolutas del autor, o el README pide pasos que no existen |
| **3** | Corrió siguiendo el README, con 1-2 pasos manuales que el README no menciona |
| **5** | `make setup && make smoke` funcionó sin intervención, y `make train` reprodujo la métrica que el README reporta |

- [ ] `uv.lock` (o equivalente) está commiteado
- [ ] `make smoke` existe y sale OK
- [ ] La métrica del README se reproduce, dentro de la tolerancia que el autor declara
- [ ] No hay rutas absolutas del autor (`grep -rn "/Users/\|C:\\\\Users" .`)

**Si algo falló, el error exacto:**

>

**Puntuación (1-5):**

---

## 2. Datos

**Qué mirar:** `src/*/data/contract.py`, `tests/data/`, `docs/dataset-card.md`.

**Prueba concreta que vale la pena hacer** (30 segundos, y es el hallazgo más útil
que puedes darle al autor): corrompe un `fixture` de test a propósito —cambia un
valor a algo fuera de rango— y corre `make test`. Si sigue pasando, el contrato no
está protegiendo nada.

**Anclas**

| Nivel | Qué observaste |
|---|---|
| **1** | Sin validación de datos. `read_csv` directo al modelo. `fillna(0)` sin justificar, o `train_test_split(shuffle=True)` sobre datos temporales |
| **3** | Contrato con tipos y rangos, `split` temporal correcto, `dataset card` con licencia |
| **5** | ≥6 reglas no triviales incluida alguna relación entre columnas; `fixtures` rotos con tests que verifican el rechazo (lo comprobé); versionado por hash; `dataset card` con unidades, nulos explicados y limitaciones |

- [ ] Hay un contrato de datos ejecutable
- [ ] Al corromper un `fixture`, los tests **fallan**
- [ ] El `split` es temporal, o hay una justificación escrita de por qué no
- [ ] `docs/dataset-card.md` nombra la licencia con su URL

**Comentarios:**

>

**Puntuación (1-5):**

---

## 3. `Tracking` y `registry`

**Qué mirar:** la UI de MLflow del proyecto (si el README dice cómo levantarla), el
código de entrenamiento, `docs/model-card.md`.

**Anclas**

| Nivel | Qué observaste |
|---|---|
| **1** | Métricas en `print`. El modelo es un `.pkl` en el repositorio. No hay forma de saber qué produjo el artefacto |
| **3** | `Runs` con `params` y métricas; el mejor modelo está registrado; hay una `model card` |
| **5** | ≥20 `runs` comparables y anidados; alias (`@champion`) y `tags`, no `stages`; `signature` e `input_example`; el preprocesamiento va dentro del artefacto; `model card` generada por script |

- [ ] Registra `params` y métricas
- [ ] Hay `signature` e `input_example`
- [ ] Usa **alias**, no `stages`. Busca `transition_model_version_stage`: si
      aparece, está usando la API deprecada
- [ ] La `model card` se genera con un comando, no está escrita a mano

**Comentarios:**

>

**Puntuación (1-5):**

---

## 4. `Pipeline`

**Qué mirar:** el código del `flow`. Si puedes, córrelo **dos veces** y cronometra:
la segunda debería ser más rápida por `caching`.

**Anclas**

| Nivel | Qué observaste |
|---|---|
| **1** | Script manual o celdas de notebook en orden. Si falla en el paso 3, hay que empezar de cero |
| **3** | `Flow` con `tasks` separadas que corre de punta a punta con un comando |
| **5** | ≥4 `tasks`, `retries` con `backoff` en las de I/O, `caching` cuya mejora se mide, `artifacts` con las métricas, `deployment` con `schedule`, y el `flow` **no promueve** el modelo |

- [ ] Los pasos están separados en `tasks`, no en un solo bloque
- [ ] Hay `retries` en las `tasks` que hablan con la red
- [ ] La segunda ejecución es más rápida (si la corriste, anota los dos tiempos)
- [ ] El `pipeline` registra el candidato pero **no** mueve `@champion`

**Comentarios:**

>

**Puntuación (1-5):**

---

## 5. `Deployment`

**Qué mirar:**

```bash
docker compose up -d
curl -s http://127.0.0.1:8000/health
docker run --rm --entrypoint sh <imagen> -c 'id -u'   # debe ser distinto de 0
```

**Anclas**

| Nivel | Qué observaste |
|---|---|
| **1** | Solo local, o el contenedor no arranca. La API devuelve la excepción interna al cliente |
| **3** | Contenedor que arranca y responde, con instrucciones claras |
| **5** | Imagen que instala desde el `lockfile`, multi-stage, no-root, `healthcheck` que funciona; carga el modelo desde el `registry` por alias; `/health` reporta la versión; ≥4 tests de API en CI |

- [ ] El servicio (o el `batch`) se puede consumir siguiendo el README
- [ ] `/health` responde y dice qué versión de modelo está sirviendo
- [ ] La imagen **no** corre como root
- [ ] El `Dockerfile` instala desde el `lockfile`, sin pines escritos a mano
- [ ] Hay tests de la API corriendo en CI

**Comentarios:**

>

**Puntuación (1-5):**

---

## 6. Monitoreo

Sección nueva, y la que más se olvida. Pesa lo mismo que las otras.

**Qué mirar:** el comando que genera el reporte de `drift`, el HTML resultante, el
`exit code` del check, `/metrics`, `docs/politica-de-reentrenamiento.md`.

**Prueba concreta:** corre el check de `drift` y mira el `exit code` (`echo $?`).
Debería ser distinto de 0 cuando hay `drift` y 0 cuando no.

**Anclas**

| Nivel | Qué observaste |
|---|---|
| **1** | Solo ideas. Un párrafo diciendo "se podría monitorear con Evidently". Nada ejecutable |
| **3** | Un reporte de `drift` generado a mano, con el HTML en el repositorio y un umbral sin justificar |
| **5** | Reporte generado desde el `pipeline` y subido como `artifact`; check con `exit code` demostrado en los dos casos; umbral justificado con tamaño de efecto y no solo p-valor; ≥3 métricas Prometheus y `dashboard` versionado; política de reentrenamiento con `trigger`, aprobador y `rollback` |

- [ ] El reporte de `drift` se genera con un comando, no a mano en un notebook
- [ ] El check de `drift` sale con `exit code` distinto de 0 cuando detecta `drift`
- [ ] El umbral está **justificado por escrito**, no solo declarado
- [ ] Hay métricas del servicio (`/metrics`) además del `drift` de los datos
- [ ] `docs/politica-de-reentrenamiento.md` dice quién aprueba y cómo se hace
      `rollback`

**Comentarios:**

>

**Puntuación (1-5):**

---

## 7. Calidad de código y documentación

**Qué mirar:** `make check` (o `ruff check` + `mypy` + `pytest`),
`git log --oneline | head -20`, `docs/`, el README.

**Anclas**

| Nivel | Qué observaste |
|---|---|
| **1** | Sin `linter`, sin tests, sin CI (o con CI que no puede fallar). Commits tipo "cambios", "fix", "asdf". Notebooks con `outputs` y artefactos binarios en el repositorio |
| **3** | `Linter` aplicado, `pre-commit` instalado, CI que corre `lint` y tests, README que explica el proyecto, estructura con sentido |
| **5** | `make check` limpio; CI verde y sin escapatorias (`grep -rn "\|\| true" .github/`); docstrings que explican **por qué**; ADRs con contexto/decisión/alternativas/consecuencias; documentación completa y coherente; commits atómicos con mensajes que dicen el motivo |

- [ ] `make check` (o el equivalente) pasa
- [ ] El CI está verde y ningún paso puede pasar por accidente
- [ ] Los notebooks no tienen `outputs` commiteados
- [ ] No hay artefactos binarios grandes ni `.env` en el repositorio
- [ ] Hay ADRs y no son plantillas con los `TODO` puestos

**Comentarios:**

>

**Puntuación (1-5):**

---

## 8. Lo mejor del proyecto

Nombra **una cosa concreta** que le vas a copiar. No "buen trabajo": algo que se
pueda señalar con un archivo y una línea.

>

## 9. Lo que mejoraría

Máximo tres cosas, ordenadas por impacto. Para cada una: qué archivo, qué cambio y
por qué.

1.
2.
3.

## 10. Puntuación general (1-5)

No es el promedio de las secciones: es tu juicio sobre el sistema como conjunto.

>

---

## Cómo dar retroalimentación que sirva

Cuatro reglas. Las cuatro se aprenden aplicándolas y se notan de inmediato cuando
faltan.

**1. Específico, con ubicación.** Un comentario sin coordenadas no se puede actuar.

- Inútil: "el manejo de errores es flojo".
- Útil: "`api/main.py:87` devuelve `str(e)` al cliente; eso filtra rutas internas.
  Manda el detalle al log con un id de correlación y devuelve un mensaje estable."

**2. Sobre el código, no sobre la persona.** El código es lo que se puede cambiar.

- No: "no entendiste el `gate` de promoción".
- Sí: "el `flow` mueve `@champion` en cada corrida (`flows/training.py:112`). Con
  eso, un modelo llega a producción por el hecho de que el entrenamiento no falló;
  la decisión debería estar en el `gate`."

**3. Distingue el error del gusto.** Un `bug` y una preferencia de estilo no pesan
igual, y mezclarlos hace que el autor ignore los dos.

- `Bug`: "`train_test_split(shuffle=True)` sobre datos con eje temporal mezcla el
  futuro en el entrenamiento; la métrica reportada es optimista."
- Gusto: "yo habría separado esto en dos funciones, pero como está funciona."

**4. Reporta también lo que funcionó, y por qué.** Sirve al autor —sabe qué
conservar— y te sirve a ti: identificar por qué algo está bien es más difícil que
detectar que algo está mal, y es la habilidad que se transfiere a tu propio código.

Y una regla de proporción: **tres comentarios buenos valen más que quince
superficiales.** Nadie actúa sobre quince.

---

## Cómo enviar la revisión

1. Completa esta plantilla, una copia por proyecto revisado.
2. Envía tus respuestas y puntuaciones en el formulario:

   <!-- INSTRUCTOR: reemplazar antes de publicar -->
   **Formulario de peer review:** `[PENDIENTE — el instructor publica aquí y en el
   aula virtual el enlace del Google Form antes de que abra la ventana de revisión]`

3. Opcional y muy valorado: deja los comentarios específicos **también como
   comentarios en el PR** del proyecto revisado. Ahí es donde el autor puede actuar
   sobre ellos línea por línea.

**Recuerda:** son **2 proyectos**. El componente de participación es binario —las
dos revisiones completas valen 5 %, una o ninguna vale 0 %— y no se compensa con la
nota del proyecto propio.
