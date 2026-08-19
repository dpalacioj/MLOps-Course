# ADR 007 — Gate de promoción: tres criterios, dos escrituras y tres exit codes

- **Estado:** aceptada
- **Fecha:** 2026-08
- **Alcance:** sesión 6, `scripts/promote.py`, `src/taxi/models/evaluate.py`, `src/taxi/models/registry.py`, `.github/workflows/cd.yml`
- **Decisores:** equipo docente del curso de MLOps

## Contexto

El repositorio anterior promovía modelos a producción **al final de cada corrida del
entrenamiento**:

```python
client.transition_model_version_stage(
    name=model_name,
    version=version,
    stage="Production",
    archive_existing_versions=True,
)
```

Un modelo llegaba a producción por el solo hecho de que el entrenamiento no lanzó
excepciones. Sin holdout, sin comparación con el modelo que estaba sirviendo, sin
posibilidad de rechazo, y **archivando al anterior** —lo que destruía el camino de vuelta.
Con una API deprecada desde MLflow 2.9.0, además.

Y el `cron` del deployment era `*/2 * * * *`: 720 corridas al día, cada una promoviendo.
El registry acumulaba 720 versiones "de producción" diarias y el linaje dejaba de poder
reconstruirse.

El diagnóstico estructural, que es lo que esta decisión ataca: **el pipeline automatizaba
la ejecución de una decisión que no estaba codificada en ninguna parte.** Lo que se
automatizaba era no decidir.

Tres preguntas que faltaban antes de mover tráfico:

1. Los datos con los que se midió, ¿son válidos? Si no, la métrica no significa nada.
2. ¿La mejora es real, o cabe dentro del ruido de muestreo?
3. ¿Mejoró en promedio a costa de empeorar en algún segmento?

## Decisión

**La promoción es una decisión explícita, evaluada por un gate que corre en CD, cuyo
resultado puede ser "no", y que solo entonces mueve el alias `@champion`.**

Cinco pasos: **tres criterios que se evalúan y dos escrituras en un orden que importa.**

### Paso 1 — Contrato de datos (`criterio_contrato_datos`)

El holdout se valida contra el esquema de Pandera `ViajesProcesados`, **el mismo** que usa
la ingesta, no una copia. Si falla, el gate **corta** y los criterios 2 y 3 se marcan
`NO EVALUADO` en lugar de `FALLA`.

Por qué primero: un RMSE calculado sobre datos que violan el contrato no significa nada, y
reportar esa comparación invita a discutir el número equivocado. Promover en base a él es
peor que no promover, porque el gate habría dado una **garantía falsa**.

Por qué `NO EVALUADO` y no `FALLA`: *"no lo revisé"* y *"lo revisé y falló"* son
diagnósticos distintos para quien lee el log del CI durante un incidente.

### Paso 2 — Mejora global con margen (`criterio_mejora_global`)

```
rmse_candidato <= rmse_champion * (1 - MEJORA_MINIMA_RELATIVA)
```

con `MEJORA_MINIMA_RELATIVA = 0.01` en `src/taxi/config.py`.

**Se exige un margen y no un simple `<`.** Con ruido de muestreo, dos modelos equivalentes
se alternan indefinidamente en producción: cada rotación cuesta un despliegue, rompe la
comparabilidad de las métricas de negocio y llena el registry. Es el *churn de modelos*.

Y el **champion se reevalúa sobre el holdout actual** en lugar de leerse sus métricas
guardadas. Si el holdout o el código de la métrica cambiaron desde que se entrenó, los
números viejos no son comparables — y un gate que compara números incomparables es peor
que no tener gate.

Caso especial: si no hay champion, el criterio aprueba y el veredicto marca
`es_primer_modelo`. "Todavía no hay champion" es un estado **normal** del sistema (es el
del primer día), no un error, y hay que distinguirlo de un fallo de conexión.

### Paso 3 — Sin regresión por subgrupo (`criterio_subgrupos`)

Para cada subgrupo comparable: `(rmse_cand - rmse_champ) / rmse_champ <= 0.05`.

Subgrupos del caso guía, definidos en un solo lugar para que entrenamiento y gate midan lo
mismo: franjas horarias (madrugada, mañana, tarde, noche) y rangos de distancia en millas
(corta, media, larga, muy larga). Son cortes **de negocio, no estadísticos**: responden a
"en qué situaciones distintas se usa este modelo".

Tres parámetros con su justificación:

| Parámetro | Valor | Por qué |
|---|---|---|
| `UMBRAL_DEGRADACION_SUBGRUPO` | 0.05 | más laxo que el 1% global **a propósito**: un subgrupo tiene menos datos y más varianza; pedir lo mismo bloquearía promociones legítimas por ruido |
| `MIN_FILAS_SUBGRUPO` | 50 | por debajo, el RMSE está dominado por el ruido de muestreo. Se reporta pero no decide: un gate con falsos positivos entrena al equipo a ignorarlo |
| sin subgrupos comparables | **FALLA** | el gate no aprueba lo que no puede verificar |

Lo que este criterio atrapa: el RMSE global baja porque el modelo mejora en el segmento
mayoritario mientras se degrada en uno minoritario. El promedio dice "mejor"; el usuario
del segmento afectado dice "peor".

Y el argumento que se dice en voz alta en clase: **es la misma técnica que detecta
inequidad.** Cuando el segmento que se degrada corresponde a un grupo de personas en lugar
de a un rango de millas, el mecanismo de detección es idéntico; lo que cambia es la
consecuencia.

### Paso 4 — Escribir el tag `validation_status`

`passed` o `failed` en la versión del candidato, con
`registry.marcar_validacion(...)`. Es la **evidencia auditable** de que el gate corrió y
con qué resultado. Se escribe **siempre**, incluso cuando el gate rechaza: una versión
marcada `failed` es información, y así nunca hay una versión en el registry cuyo estado de
validación sea desconocido (al registrarse queda `pending`).

### Paso 5 — Y solo entonces, mover el alias

`registry.asignar_alias(nombre, 'champion', version)`.

**El orden de los pasos 4 y 5 es la decisión de diseño.** Si el proceso muere entre las dos
escrituras, el estado resultante es *"validada pero no promovida"*, que es seguro. El orden
inverso dejaría un modelo sirviendo tráfico **sin registro de haber sido validado**, que es
exactamente el incidente que se quiere evitar.

Regla transferible: cuando dos escrituras no son atómicas, se ordenan para que el estado
intermedio sea el seguro.

### Los tres exit codes

| Código | Significado | Efecto en el CD |
|---|---|---|
| `0` | promovido, o el candidato ya era el champion | continúa al deploy |
| `1` | **rechazado** por criterios | falla el job; `@champion` intacto |
| `2` | **no pudo medir** (MLflow caído, falta el holdout) | falla el job, con mensaje distinto |

La distinción entre 1 y 2 es deliberada: **"el modelo no es lo bastante bueno" es un
resultado exitoso del gate; "no pude medir" es una falla del gate.** Confundirlos hace que
un MLflow caído se lea como un modelo malo, y que alguien reentrene para arreglar un
problema de red.

Complemento necesario: `registry.fallar_rapido()` baja el timeout HTTP a 3 s y los
reintentos a 1 para las consultas de **metadatos**. Con los defaults de mlflow (7
reintentos con backoff, 120 s) el gate colgaría el job de CD durante minutos antes de
devolver el 2. **Un fallback que tarda cuatro minutos en activarse no es un fallback.**

### La política es una función pura

`decidir_promocion(...)` recibe métricas y devuelve un `DecisionGate`; no toca MLflow, no
escribe tags, no mueve aliases. `scripts/promote.py` es la capa de presentación: tablas,
banderas y exit code.

Eso es lo que permite testear **la política de promoción** en `tests/unit/test_gate.py`
sin levantar infraestructura. Si la política y la infraestructura estuvieran mezcladas, los
tests requerirían un registry, alguien los marcaría `skip` y el criterio de promoción
quedaría sin cobertura.

### En un PR, `--dry-run`

El gate evalúa, imprime las tablas, comenta el resultado en el PR y **no escribe el tag ni
mueve el alias**. Mover `@champion` desde un PR sin aprobación es el fallo que este diseño
evita.

### El rollback es mover el alias de vuelta

```bash
uv run python -c "from taxi.models import registry; registry.asignar_alias('nyc-taxi-duration', 'champion', '6')"
```

Una escritura de metadatos: sub-segundo, sin reentrenar, sin rebuild, sin redeploy.
Funciona porque **las versiones del registry son inmutables**: la versión anterior sigue
intacta y el artefacto es bit a bit el que estaba sirviendo.

Es la razón principal por la que el modelo se referencia por alias y no se copia a un
directorio, y es también por lo que **no se archiva** al champion anterior: archivar
destruye el camino de vuelta.

## Alternativas consideradas

### A. Promover siempre al final del entrenamiento (el statu quo anterior)

Descartada. Es el anti-patrón que motiva este ADR. Consecuencia observada en el
repositorio: 720 versiones "de producción" al día y ninguna forma de saber por qué una
estaba ahí.

### B. Aprobación puramente manual, sin criterios codificados

Descartada como *sustituto*, aceptada como *complemento*. Una persona mirando dos números
no detecta una regresión por subgrupo, y la revisión se degrada a un clic en la tercera
semana. Pero la aprobación humana **sí** se conserva para el despliegue a producción, por
una razón distinta: alguien asume la decisión y queda registrado.

### C. Un test estadístico formal de la diferencia de errores

Descartada para el curso, reconocida como más rigurosa. Un test de significancia sobre la
diferencia de errores con el tamaño del holdout es lo correcto, y es lo que se debería
hacer con datos y tiempo suficientes. Se descarta por dos razones: agrega un aparato
estadístico que desvía la clase del tema (el gate como mecanismo), y con el tamaño del
holdout del caso guía la conclusión sería la misma. **El 1% es un umbral elegido, no
derivado, y el material lo dice así.**

### D. Solo métrica global, sin subgrupos

Descartada. Es el filtro que la mayoría de los equipos implementa y es el que deja pasar
las regresiones silenciosas. Sin el criterio 3, el gate aprueba modelos que empeoran para
un segmento entero de usuarios, y ese es el fallo más difícil de detectar después: nadie
mira el promedio de un segmento que no sabía que existía.

### E. Gate como parte del CI, no del CD

Descartada. El CI responde "¿el código está bien?" y su resultado depende solo del código.
El gate depende de **datos**: su resultado cambia sin que el código cambie, y su salida
correcta puede ser "no" sin que nada esté roto. Meterlos en el mismo workflow haría que un
rechazo de modelo se lea como un fallo de código, y que un fallo de lint bloquee un
despliegue urgente.

### F. Rollback automático por métricas de producción

Descartada **para esta versión**, deseable a futuro. Requiere el monitoreo de la sesión 7
conectado a un disparador, y un rollback automático mal calibrado revierte despliegues
buenos —lo que es peor que el manual. El orden correcto de implementación es: primero el
smoke test real contra staging, después el despliegue progresivo, y el rollback automático
al final.

## Consecuencias

### Positivas

- **Un modelo peor no puede llegar a producción por inercia.** El pipeline tiene un punto
  donde la respuesta puede ser "no", y ese "no" hace fallar el job.
- **El criterio está escrito, versionado y en un solo lugar.** Cambiarlo es un PR con
  discusión, no una decisión de pasillo.
- **La política es testeable sin infraestructura**, así que está cubierta y se mantiene
  cubierta.
- **El rollback es trivial** y no requiere reentrenar: mover el alias.
- **Cada versión del registry tiene un estado de validación explícito** (`pending`,
  `passed`, `failed`). No hay versiones de estado desconocido.
- **Reentrenar puede ser automático sin que desplegar lo sea.** Es lo que permite que la
  sesión 4 programe entrenamientos sin miedo.

### Negativas, y asumidas

- **Los tres umbrales son elegidos, no derivados.** 1%, 5% y 50 filas son defendibles y no
  son óptimos. El material lo dice explícitamente, y el taller pide que cada estudiante
  justifique los suyos en lugar de copiarlos.
- **El gate cuesta tiempo en el CD**: hay que cargar dos modelos y evaluarlos sobre el
  holdout completo en cada corrida. Se mitiga con el cache de las particiones fijas
  (`actions/cache` con `key: particiones-fijas-v1`), pero sigue siendo el job más largo.
- **Un gate demasiado estricto se desactiva.** Es el riesgo real: si nada se promueve
  nunca, alguien agrega un `--force`. Por eso el umbral por subgrupo es más laxo que el
  global y por eso existe `MIN_FILAS_SUBGRUPO`.
- **El holdout fijo envejece.** Es una partición del pasado (`PARTICION_TEST`, 2023-05) y
  con el tiempo deja de representar la producción. La consecuencia es un gate que aprueba
  modelos buenos en 2023 y no necesariamente hoy. Rotar el holdout requiere reevaluar al
  champion en el holdout nuevo antes de comparar, y eso hay que hacerlo explícitamente.
- **El gate no mide latencia ni tamaño del modelo.** Un candidato con mejor RMSE y tres
  veces más lento pasa. Es un criterio que un sistema real necesita y que aquí se nombra
  como hueco declarado.
- **Depende de que el holdout no se haya usado para tunear.** Es una disciplina, no una
  garantía técnica. El CLI ayuda (`taxi train --holdout` tiene un aviso explícito en su
  ayuda), pero nada impide violarla.

## Verificación

- `tests/unit/test_gate.py` — la política, sin infraestructura.
- Job `gate` de `.github/workflows/cd.yml` — corre en cada push a `main` y en cada PR
  (`--dry-run`), y su exit code detiene el pipeline.
- `nightly-smoke.yml` — el gate corre sobre datos reales cada noche; si rechaza por una
  regresión real, se abre un issue.
- `sesiones/s06-cloud-cicd/_soluciones/evidencia.sh` — genera la evidencia de rechazo y de
  aceptación.

## Referencias

- Material de la sesión: [`sesiones/s06-cloud-cicd/cicd.md`](../../sesiones/s06-cloud-cicd/cicd.md)
- [ADR 002 — aliases y tags en vez de stages](002-aliases-en-vez-de-stages.md)
- [ADR 006 — servir online y en batch](006-serving-online-vs-batch.md)
- [ADR 003 — umbrales de drift](003-umbrales-de-drift.md) (mismo problema de calibración,
  en el monitoreo)
- MLflow — [Model Registry: aliases y tags](https://mlflow.org/docs/latest/ml/model-registry/)
- GitHub Actions — [environments y protection rules](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
