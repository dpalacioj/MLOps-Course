# Solución de referencia — Taller S06

Recorrido del taller aplicado al caso guía. Cada sección apunta al código del
repositorio que satisface el criterio y dice **qué se acepta como alternativa válida**,
porque el taller se hace sobre el proyecto de cada estudiante.

---

## 1. El gate: los cinco pasos y dónde está cada uno

| Paso del taller | En el caso guía | Archivo |
|---|---|---|
| Validación de datos | `criterio_contrato_datos` valida el holdout con `ViajesProcesados` (Pandera), el **mismo** contrato de la ingesta | `src/taxi/models/evaluate.py` |
| Métrica global con margen | `criterio_mejora_global`: `rmse_cand <= rmse_champ * (1 - 0.01)` | idem |
| Por subgrupo | `criterio_subgrupos`: franjas horarias y rangos de distancia, umbral 5%, `MIN_FILAS_SUBGRUPO = 50` | idem |
| Tag `validation_status` | `registry.marcar_validacion(...)`, **antes** del alias | `src/taxi/models/registry.py` |
| Mover el alias | `registry.asignar_alias(...)`, solo si `decision.promover` | idem |

La orquestación de los cinco, con los exit codes y las dos tablas de salida, está en
[`scripts/promote.py`](../../../scripts/promote.py).

### Los umbrales, argumentados

Esto es lo que se evalúa, no el número:

- **`MEJORA_MINIMA_RELATIVA = 0.01`** (1% de RMSE global). Es un umbral **elegido, no
  derivado**. Lo riguroso sería un test estadístico sobre la diferencia de errores con
  el tamaño del holdout; el 1% es una aproximación defendible que evita el churn de
  modelos sin bloquear mejoras reales. Vive en
  [`config.py`](../../../src/taxi/config.py) para poder discutirlo en un solo lugar.
- **`UMBRAL_DEGRADACION_SUBGRUPO = 0.05`** (5%). **Más laxo que el global a propósito**:
  un subgrupo tiene menos datos y más varianza, y pedirle el mismo 1% bloquearía
  promociones legítimas por ruido.
- **`MIN_FILAS_SUBGRUPO = 50`**. Por debajo, el RMSE está dominado por el ruido de
  muestreo: el subgrupo se reporta pero no decide. Un gate con falsos positivos entrena
  al equipo a ignorarlo, y un gate ignorado es peor que ninguno.

**Qué se acepta:** cualquier trío de números con este tipo de justificación, incluida
"no tengo datos para calibrarlo, empiezo conservador y lo reviso en un mes". **Qué no:**
los mismos números sin explicación, o "0.01 porque es lo que vimos en clase".

### Dos decisiones de diseño que suelen faltar en las entregas

**Corto circuito con `NO EVALUADO`.** Si el contrato de datos falla, los criterios 2 y 3
se marcan `evaluado=False`, no `aprobado=False`. *"No lo revisé"* y *"lo revisé y
falló"* son diagnósticos distintos para quien lee el log a las tres de la mañana.

**El champion se reevalúa.** No se leen sus métricas guardadas:

```python
modelo_champion = _cargar_modelo(config.uri_modelo(nombre_modelo, config.ALIAS_PRODUCCION))
metricas_champion, subgrupos_champion = evaluate.evaluar_modelo(modelo_champion, holdout)
```

Si el holdout o el código de la métrica cambiaron desde que se entrenó, los números
guardados no son comparables. Es el error más común de las entregas y el que hace que
"el gate siempre aprueba".

---

## 2. Criterios 1, 2 y 3 — rechaza, acepta, y los dos en el log

Referencia esperada en el PR:

```text
Gate ACEPTA (exit 0): <enlace a la corrida>
  PROMOVIDO — todos los criterios pasan
  @champion de 'nyc-taxi-duration' -> version 8 (anterior: version 7)

Gate RECHAZA (exit 1): <enlace a la corrida>
  RECHAZADO — criterios no superados: mejora_global
  @champion sigue en version 8. El modelo que ya estaba sirviendo no se toco.
```

Cómo se generan los dos casos: ver `evidencia.sh` en esta carpeta. El rechazo se produce
con `taxi train --modelo media --registrar`, que registra el baseline de la media — peor
por construcción que cualquier modelo que haya llegado a `@champion`.

**El criterio 3 es el que demuestra el aprendizaje.** Un gate que solo se ha visto
aprobar es indistinguible de un `echo "todo bien"`. Si en el PR solo hay el enlace verde,
el criterio no está cumplido aunque el código sea correcto.

## 3. Criterio 4 — rechazado vs no pudo medir

```bash
docker compose stop mlflow
uv run taxi promote; echo "exit: $?"     # 2
```

Salida esperada: un mensaje de infraestructura, **no** una tabla de criterios. En
[`cd.yml`](../../../.github/workflows/cd.yml):

```bash
case "$codigo" in
  0) echo "promovido=true"  >> "$GITHUB_OUTPUT" ;;
  1) echo "promovido=false" >> "$GITHUB_OUTPUT" ;;
  *) echo "::error::el gate no pudo medir (exit $codigo): revisa la conexion con MLflow"
     echo "promovido=error" >> "$GITHUB_OUTPUT" ;;
esac
```

Y la pieza que hace esto usable: `registry.fallar_rapido()` baja el timeout a 3 s y los
reintentos a 1 para las consultas de **metadatos**. Con los defaults de mlflow (7
reintentos con backoff, 120 s de timeout) el job se colgaría minutos antes de devolver
el 2. **Un fallback que tarda cuatro minutos en activarse no es un fallback.**

Error frecuente en las entregas: un `try/except Exception` que envuelve todo y devuelve
1. Eso hace que un MLflow caído se lea como un modelo malo, y alguien acabe reentrenando
para arreglar un problema de red.

## 4. Criterio 5 — tests de la política sin infraestructura

En [`tests/unit/test_gate.py`](../../../tests/unit/test_gate.py). Son posibles porque la
política son **funciones puras** que reciben métricas y devuelven un veredicto: no tocan
MLflow, no escriben tags, no mueven aliases.

Los tres casos que el taller pide:

| Caso | Qué se verifica |
|---|---|
| el champion es mejor | `decidir_promocion(...).promover is False` y el motivo nombra `mejora_global` |
| mejora global, degrada un subgrupo | `promover is False` y el motivo nombra `sin_regresion_por_subgrupo` |
| no hay champion | `promover is True` y `es_primer_modelo is True` |

El cuarto, que se valora: mejora **por menos** del margen exigido → no promueve. Es el
que distingue un gate con margen de un `<`.

Si un estudiante no puede escribir estos tests sin levantar MLflow, el hallazgo no es
"faltan tests": es que la política y la infraestructura están mezcladas. Ese es el
comentario de la revisión.

## 5. Criterio 6 — sin secretos, sobre el historial

El job `secretos` de [`ci.yml`](../../../.github/workflows/ci.yml) usa
`fetch-depth: 0`. Por qué importa: un secreto comiteado y borrado en el commit siguiente
**sigue en el historial**, y un `git push --force` no lo saca de los forks ni de los
clones que ya existen.

La regla operativa que hay que decir: **un secreto que llegó a un repositorio remoto
está comprometido y hay que rotarlo.** Borrar el commit es cosmética.

En la revisión, además de `gitleaks`:

```bash
grep -rnE "AWS_SECRET|AWS_ACCESS_KEY_ID *=|password *=|api[_-]?key *=" --include='*.yml' --include='*.py' --include='Dockerfile' .
git log -p --all | grep -cE "BEGIN (RSA|OPENSSH) PRIVATE KEY" || true
```

## 6. Criterio 7 — digest, no `latest`

En [`cd.yml`](../../../.github/workflows/cd.yml):

```yaml
tags: |
  type=sha,format=long
  type=ref,event=pr
  type=ref,event=branch
```

`latest` no aparece. Y la referencia que viaja a los jobs de deploy es
`${REGISTRY}/${IMAGEN}@${digest}`.

Detalle que se valora si el estudiante lo replica: en un build de PR no hay push, así que
no hay digest; el workflow lo detecta y cae al tag del sha con un `::warning::` en lugar
de propagar una cadena vacía al deploy.

## 7. Criterio 8 (opcional) — la URL respondió y el teardown se ejecutó

Evidencia esperada, las **dos** partes:

```text
$ curl -fsS https://xxxxxxxx.us-east-1.awsapprunner.com/health
{"status":"degradado","model_loaded":false,...,"version_api":"1.0.0"}

$ EQUIPO=equipo01 bash sesiones/s06-cloud-cicd/scripts/teardown.sh
...
7. Verificación: qué queda en la cuenta
-- App Runner ---  (vacío)
-- ECR ---------   (vacío)
-- RDS ---------   (vacío)
-- S3 ----------   (vacío)
```

Que `/health` responda `"degradado"` **es un resultado correcto** para el laboratorio: la
API se despliega con `TAXI_MODELO_URI=ninguno` a propósito, para verificar la plataforma
antes de meter el registry en la ecuación. Lo que se evalúa es que la URL responda con
HTTPS y que el JSON tenga la forma del contrato.

**Sin la salida del teardown, este criterio descuenta en lugar de sumar.**

## 8. El ADR y los dos rollbacks

Referencia: [`docs/adr/007-gate-de-promocion.md`](../../../docs/adr/007-gate-de-promocion.md).

Los dos rollbacks, que son independientes porque son dos artefactos:

```bash
# Modelo: una escritura de metadatos. Sub-segundo, sin reentrenar, sin rebuild.
uv run python -c "from taxi.models import registry; registry.asignar_alias('nyc-taxi-duration', 'champion', '7')"

# Imagen: volver a desplegar el digest previo, que está en el step summary de la
# corrida anterior del CD.
```

Un estudiante que escriba "el rollback es volver a entrenar el modelo anterior" no
entendió por qué las versiones del registry son inmutables. Es el punto que hay que
corregir en la revisión, porque invalida la mitad de la sesión 3.

---

## Guion de revisión en 5 minutos por PR

En este orden, de lo más barato a lo más caro:

1. ¿Están los **dos** enlaces de Actions (rojo y verde)? Si no, para aquí: el criterio 3
   es el núcleo.
2. Abrir el log del rechazo: ¿la tabla de criterios dice **cuál** falló y con qué
   números?
3. `grep -n "latest" .github/workflows/cd.yml`
4. `grep -rn "|| true\|no tests" .github/workflows/`
5. ¿El gate está separado en política pura + script? Mirar los imports del test.
6. Correr los tests de la política con MLflow apagado.
7. Leer el ADR: ¿los umbrales tienen una razón y las consecuencias están en los dos
   sentidos?
8. Si hay laboratorio de nube: ¿está la salida del teardown con las listas vacías?

Los pasos 1 a 5 detectan la mayoría de los problemas y no requieren levantar nada.
