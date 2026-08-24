# Taller S07 — Poner el monitoreo a fallar

**Duración:** 55 min en clase. Se entrega en clase.
**Sobre:** tu propio repositorio de proyecto (no el del curso).
**Entregable:** un PR con el check de drift, la instrumentación, los dos documentos de
gobernanza y la evidencia de las mediciones.

---

## Contexto

Tu modelo ya está entrenado con tracking (S03), orquestado (S04), servido tras una API
(S05) y desplegado con un gate de promoción (S06).

Hoy el objetivo **no** es "usar Evidently". Es que tu sistema pueda **avisar** de que
dejó de ser válido, que ese aviso **falle** en un pipeline en lugar de dormir en una
carpeta, y que exista escrito quién decide qué hacer cuando suena.

Un monitoreo que nadie mira y que nunca bloquea nada es monitoreo de mentira.

---

## 1. El check de drift, con datos reales y exit code

Requisitos, todos verificables:

- una **referencia** que sean tus datos de entrenamiento reales y un **actual** que sea
  un periodo posterior real. Nada de `np.random`;
- veredicto por columna con **tamaño de efecto**, no solo p-valor;
- agregación a nivel de dataset con un umbral declarado en tu módulo de configuración,
  no incrustado en el código;
- **exit code distinto de cero** cuando se supera el umbral;
- artefactos con nombre que diga qué se comparó (HTML si usas Evidently, y un JSON
  siempre).

Puedes copiar la estructura de `src/taxi/monitoring/` o escribir la tuya. Si usas
Evidently, usa la API 0.7 (`from evidently import Report, Dataset, DataDefinition`);
si encuentras un tutorial con `from evidently.report import Report`, es de 0.6 y no
ejecuta.

## 2. Calibra tus umbrales contra el ruido

**No copies los umbrales del curso.** Son de este dataset y de este `n`.

```python
from taxi.monitoring.estadistico import linea_base_nula
# o tu propia version: partir la referencia en dos mitades aleatorias
```

Entrega una tabla con tres columnas por feature: **ruido bajo el nulo**, **umbral que
fijaste**, **señal observada en el periodo actual**. Toda fila donde el umbral sea menor
que el ruido es un falso positivo garantizado y hay que corregirla.

## 3. Instrumenta tu servicio

Mínimo tres métricas de Prometheus, con los tres tipos representados y una justificación
de una línea por métrica:

- un `Counter` (predicciones o errores),
- un `Histogram` (latencia de inferencia, con buckets **elegidos para tu latencia**, no
  los de por defecto),
- un `Gauge` (versión del modelo cargada, o trabajo en vuelo).

Y un `label` que permita distinguir versiones del modelo. Sin él, un despliegue es
invisible en el dashboard.

## 4. Un dashboard versionado

El JSON del dashboard va en el repositorio y se provisiona. Mínimo tres paneles: p95 de
latencia, throughput y una señal del modelo (distribución de predicciones por clase, o
similar). Si tu dashboard solo existe en la UI de Grafana, no cuenta.

## 5. La política de reentrenamiento

Rellena [`plantillas/politica-de-reentrenamiento.md`](plantillas/politica-de-reentrenamiento.md).
Una página. Tiene que nombrar **trigger, aprobador y mecanismo de rollback**, con
nombres de comandos reales de tu repositorio.

## 6. El registro de riesgos y la clasificación regulatoria

Rellena [`plantillas/riesgos.md`](plantillas/riesgos.md): cinco riesgos, mitigación,
responsable, y la clasificación tentativa de tu sistema bajo el AI Act con **la fecha
de aplicación que te corresponde** (ver [`gobernanza.md`](gobernanza.md) sección 2).

---

## Criterios de aceptación

Se revisan en el PR, en este orden. Cada uno es una comprobación, no una opinión.

| # | Criterio | Cómo se verifica |
|---|---|---|
| 1 | El reporte se genera **desde el pipeline**, no desde un notebook | existe un comando (`make drift`, `taxi drift`, o un step del flow) que produce el artefacto; el notebook, si existe, solo explora |
| 2 | El check **falla** con datos con drift | se corre contra un periodo con drift (o con un umbral bajo) y `echo $?` devuelve distinto de 0. Pégalo en el PR |
| 3 | El check **pasa** sin drift | se corre contra dos mitades de la referencia y `echo $?` devuelve 0. Es el control negativo: sin él, el criterio 2 no demuestra nada |
| 4 | El veredicto usa tamaño de efecto | el JSON de salida contiene, por columna, estadístico, p-valor, tamaño de efecto y umbral |
| 5 | Los umbrales están **calibrados** | la tabla del punto 2, con el ruido medido, en el PR o en un ADR |
| 6 | `/metrics` expone **≥ 3 métricas** propias | `curl -s localhost:8000/metrics \| grep -c '^tu_prefijo_'` devuelve 3 o más |
| 7 | Grafana **grafica** esas métricas | JSON del dashboard versionado en el repo, con ≥ 3 paneles, y una captura o un enlace al panel |
| 8 | La política nombra **trigger, aprobador y rollback** | los tres campos rellenos con comandos reales; "el equipo revisa" no es un aprobador |
| 9 | El reentrenamiento **no** promueve solo | ninguna ruta del código toca el alias de producción sin pasar por el gate |
| 10 | Hay un ADR de umbrales | `docs/adr/00X-*.md` con contexto, decisión, consecuencias y alternativas descartadas |

**Criterios de calidad (no bloquean, suben la nota):**

- el check degrada con elegancia si falta la librería de monitoreo, y lo dice;
- el resultado se loguea en tracking, de forma tolerante a fallo;
- hay un test que verifica el control negativo (cero falsos positivos);
- el análisis distingue **drift** de **estacionalidad** con evidencia, no con opinión.

---

## Entrega

Un PR contra tu rama principal con:

```
src/<tu_paquete>/monitoring/     el check y sus utilidades
tests/                           al menos 3 tests, uno de ellos el control negativo
observabilidad/                  JSON del dashboard y config de Prometheus
docs/adr/00X-umbrales-de-drift.md
docs/politica-de-reentrenamiento.md
docs/riesgos.md
```

En la descripción del PR, pegado y visible:

1. la salida del check con drift, con su exit code;
2. la salida del check sin drift, con su exit code;
3. la tabla de calibración (ruido / umbral / señal);
4. `curl -s .../metrics | grep '^tu_prefijo_' | head`.

**Lo que hace que un PR se devuelva:** umbrales sin calibrar copiados del curso, un
check que nunca falla, un dashboard que solo existe en la UI, o una política de
reentrenamiento en la que el aprobador es "el equipo".
