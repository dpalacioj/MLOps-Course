# Taller S06 — El gate de promoción y el pipeline que despliega

Se puede terminar en la misma clase. Es opcional y suma al bonus del curso.
**Sobre:** tu propio repositorio de proyecto (no el del curso).
**Entregable:** un PR con los workflows, el gate, los logs y el ADR.

> **Nada de este taller requiere una cuenta de AWS.** Los criterios 1 a 7 se cumplen
> con MLflow, Docker y GitHub Actions. El criterio 8 es **opcional** y solo aplica si
> hiciste la demo de la nube con una cuenta propia.

---

## Contexto

Tu servicio ya está contenedorizado (S05) y tu entrenamiento ya corre orquestado (S04).
Hoy conectas las dos cosas y agregas la pieza que falta: **un punto donde el pipeline
pueda decir "no"**.

El objetivo no es "tener CI/CD". Es que un modelo peor **no** pueda llegar a producción
por el solo hecho de que el pipeline terminó sin errores.

---

## 1. El gate de promoción (el núcleo del taller)

Un script en tu repositorio que decide si un candidato reemplaza al `@champion`, con
**exit codes** y estas cinco piezas:

1. **Validación de datos**: el holdout pasa tu contrato de S02. Si falla, no se miran
   métricas, y los criterios siguientes se reportan como *no evaluados*, no como
   *fallidos*.
2. **Métrica global**: el candidato supera al champion en tu holdout fijo **por un
   margen declarado**, no por un simple "menor que". Declara el margen y justifícalo.
3. **Por subgrupo**: define al menos **dos** cortes de negocio de tu dominio y verifica
   que ninguno se degrada más de un umbral. Declara también el tamaño mínimo de
   subgrupo por debajo del cual no decides.
4. **Tag de validación**: escribe `validation_status` (`passed`/`failed`) en la versión
   del candidato, **antes** de tocar el alias.
5. **Mover el alias**: y solo entonces.

Requisitos de implementación:

- **La política es una función pura** que recibe métricas y devuelve un veredicto, y
  vive separada del script que habla con MLflow. Es lo que permite testearla sin
  levantar nada.
- **El champion se reevalúa sobre el holdout actual**, no se leen sus métricas
  guardadas. Si tu holdout o tu código de métricas cambiaron, los números viejos no son
  comparables.
- **Tres exit codes**: `0` promovido, `1` rechazado, `2` no pudo medir. La distinción
  entre 1 y 2 se evalúa: con MLflow apagado, el mensaje tiene que decir que el problema
  es de infraestructura, no mandar a reentrenar.
- Un `--dry-run` que evalúe e informe **sin escribir nada**.

Referencia: [`scripts/promote.py`](../../scripts/promote.py) y
[`src/taxi/models/evaluate.py`](../../src/taxi/models/evaluate.py). La explicación
completa está en [`01-el-gate-de-promocion.md`](01-el-gate-de-promocion.md).

## 2. Tests de la política del gate (≥3)

Sin MLflow y sin red, porque son funciones puras:

1. el champion es mejor → **no** promueve;
2. el candidato mejora globalmente pero **degrada un subgrupo** → no promueve;
3. no hay champion (primer modelo) → promueve, y el veredicto dice que es el primero.

Bonus que se valora: el caso "mejora, pero por menos del margen exigido" → no promueve.

## 3. El workflow de CI

Como mínimo: lint, tipos, tests, escaneo de secretos y build de la imagen. El job de la
imagen tiene que **verificar** que no corre como root (cópialo del job `imagen` de
[`ci.yml`](../../.github/workflows/ci.yml)).

Prohibido: cualquier paso que termine en `|| true` o `|| echo "..."`. Un pipeline que no
puede fallar es peor que no tener pipeline.

Las actions van en versiones mayores que corran sobre Node 24 (la tabla está en
[`02-los-tres-workflows.md`](02-los-tres-workflows.md#5-las-versiones-de-las-actions-envejecen)).
Un workflow con `actions/checkout@v4` no arranca en los runners de GitHub desde el
23 de septiembre de 2026.

## 4. El workflow de CD

- La imagen se referencia **por digest**, no por `latest`.
- El gate corre **antes** del deploy y **su exit code manda**: rechazado ⇒ el job falla
  y el pipeline no continúa.
- En un PR, el gate corre en `--dry-run` y comenta el resultado. Un PR no mueve
  `@champion`.
- El comentario del PR se hace con `actions/github-script`, **no** con CML, y los
  valores entran por `env:`, nunca interpolados dentro del script.
- El comentario se **actualiza** en cada push en lugar de acumularse.

## 5. Ambientes y aprobación

Configura en tu repositorio: `staging` (automático) y `production` (con **required
reviewer**). La protección va en *Settings → Environments*, **no** en un `if:` del
workflow. Explica en el PR por qué.

Si tu repositorio es **privado y estás en el plan gratuito de GitHub**, los
environments con reglas de protección no están disponibles (verificado el 3 de
septiembre de 2026). En ese caso, el criterio se cumple con el `environment:` declarado
en el YAML y un párrafo en el PR que diga qué configurarías y por qué la barrera no
puede vivir en el archivo que protege. Hazlo público si puedes: es la forma de tener la
protección de verdad.

## 6. Rollback documentado

Un párrafo en el README de tu proyecto con los **dos** rollbacks, que son
independientes:

- **del modelo**: mover el alias a la versión anterior, con el comando exacto;
- **de la imagen**: volver a desplegar el digest previo, y dónde encuentras ese digest.

## 7. ADR: `docs/adr/00X-gate-de-promocion.md`

1. **Contexto**: qué decidía hoy si un modelo llega a producción en tu proyecto.
2. **Decisión**: los cinco pasos, con **tus** umbrales y por qué esos números.
3. **Alternativas descartadas**: al menos dos (por ejemplo: promover siempre; aprobación
   puramente manual sin criterios; test estadístico formal).
4. **Consecuencias**: en los dos sentidos. Qué pasa si el gate es demasiado estricto
   (nada se promueve nunca, el equipo lo desactiva) y qué pasa si es demasiado laxo (un
   modelo peor llega a producción con el pipeline en verde).

---

## Criterios de aceptación

| # | Criterio | Cómo se verifica |
|---|---|---|
| 1 | El gate **rechaza** un candidato peor | correr el gate con un candidato deliberadamente malo: **exit code 1**, y `@champion` sin moverse |
| 2 | El gate **acepta** un candidato mejor | exit code 0 y el alias apuntando a la versión nueva |
| 3 | **Los dos casos quedan en el log de un workflow de Actions** | un enlace a una corrida de Actions donde se vea `PROMOVIDO` y otra (o la misma) donde se vea `RECHAZADO` con la tabla de criterios. Cómo lograrlo sin un MLflow público, abajo |
| 4 | El gate distingue "rechazado" de "no pudo medir" | apagar MLflow y correr el gate: **exit code 2**, con un mensaje que diga que es infraestructura |
| 5 | ≥3 tests de la política pasan sin infraestructura | `pytest` en verde con MLflow apagado |
| 6 | **Ningún secreto en el repositorio** | `gitleaks` en verde sobre **el historial completo** (`fetch-depth: 0`) |
| 7 | El CD referencia la imagen por digest | `grep -n "latest" .github/workflows/cd.yml` no devuelve una referencia de despliegue |
| 8 | *(Opcional, solo si hiciste la demo con tu cuenta)* la API respondió desde la nube y **el teardown se ejecutó** | la salida del `curl .../predict` contra la IP pública **más** la sección 8 de la salida del `teardown.sh`, con las seis listas vacías |

El criterio 3 es el que más se olvida y es el que demuestra el aprendizaje: **el log del
rechazo es la evidencia de que el gate existe.** Un gate que solo se ha visto aprobar es
indistinguible de un `echo "todo bien"`.

El criterio 8 no suma nota si se hizo el despliegue y **no** se hizo el teardown. Al
contrario: descuenta. Dejar recursos facturando es el error operativo de la sesión.

---

## Cómo generar la evidencia

### Criterios 1, 2 y 4, en local

```bash
# --- Criterio 2: acepta un candidato mejor -------------------------------
uv run taxi train --hpo --trials 10        # entrena y registra un candidato
uv run taxi promote
echo "exit code: $?"                        # 0 si mejora al menos el margen

# --- Criterio 1: rechaza un candidato peor ------------------------------
# El baseline de la media predice siempre el promedio: peor por construccion
# que cualquier modelo que haya llegado a @champion. Rechazo limpio y determinista.
uv run taxi train --modelo media --registrar
uv run taxi promote
echo "exit code: $?"                        # 1

# Y la comprobacion que cierra el criterio: el champion NO se movio
uv run python -c "
from taxi.models import registry
mv = registry.version_por_alias('nyc-taxi-duration', 'champion')
print('champion sigue en la version', mv.version if mv else 'ninguna')
"

# --- Criterio 4: no pudo medir -----------------------------------------
# Apaga MLflow (Ctrl-C en su terminal, o `docker compose stop mlflow`) y:
uv run taxi promote
echo "exit code: $?"                        # 2, y el mensaje habla de MLflow, no del modelo
```

### Criterio 3: el gate en un log de Actions, sin un MLflow público

Los runners de GitHub no pueden llegar al MLflow de tu computador, y montar uno en
internet cuesta dinero y tiempo que este taller no pide. La forma honesta de tener el
gate en un log de Actions es la que usa el `nightly-smoke.yml` del curso: **MLflow
dentro del runner**, con SQLite, y los dos candidatos registrados en el mismo job.

Un workflow `gate-demo.yml` con `workflow_dispatch` (se lanza a mano desde la pestaña
Actions), cuyo job hace, en orden:

```yaml
- name: MLflow dentro del runner
  run: |
    uv run mlflow server --backend-store-uri sqlite:///mlflow.db \
      --default-artifact-root ./mlartifacts --host 127.0.0.1 --port 5001 &
    for i in $(seq 1 60); do curl -sf http://127.0.0.1:5001/health && break; sleep 2; done

- name: Datos
  run: uv run taxi data

- name: Primer modelo -> se promueve (no hay champion)
  run: |
    uv run taxi train --modelo media --registrar
    uv run taxi promote                     # exit 0: es el primero

- name: Candidato mejor -> PROMOVIDO
  run: |
    uv run taxi train --registrar            # el lineal mejora a la media con holgura
    uv run taxi promote                      # exit 0

- name: Candidato peor -> RECHAZADO (y se afirma que lo fue)
  run: |
    uv run taxi train --modelo media --registrar
    set +e
    uv run taxi promote
    codigo=$?
    set -e
    test "$codigo" -eq 1 || { echo "::error::se esperaba exit 1 y salio $codigo"; exit 1; }
```

Fíjate en el último paso: **esperar un fallo también se afirma.** No es un `|| true`
que traga cualquier cosa: es "el exit code tiene que ser exactamente 1, y si no lo es,
este job falla". El log de esa corrida tiene el `PROMOVIDO` y el `RECHAZADO` con sus
tablas, y ese es el enlace que va al PR.

Adapta los nombres de modelo (`--modelo media`, el lineal) a los de tu proyecto: lo que
importa es tener un candidato peor por construcción.

### Criterios 6 y 7

```bash
# --- Criterio 6: sin secretos, sobre el historial completo ----------------
# La version es la misma que fija .pre-commit-config.yaml, para que local y CI coincidan.
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.23.1 detect \
  --source=/repo --no-banner --redact

# --- Criterio 7: nada de latest como referencia de despliegue -------------
grep -n "latest" .github/workflows/cd.yml || echo "sin 'latest'  OK"
```

Para el criterio 3, en el PR:

```markdown
- Gate ACEPTA y RECHAZA en un solo workflow: <enlace a la corrida de Actions>
```

---

## Errores frecuentes

| Síntoma | Causa habitual |
|---|---|
| El gate siempre aprueba | se compara con las métricas **guardadas** del champion en lugar de reevaluarlo sobre el holdout actual |
| El gate siempre rechaza | el margen exigido es absurdamente alto, o el holdout tiene fugas del set de entrenamiento |
| Exit code 1 cuando MLflow está caído | no se distingue "rechazado" de "no pudo medir": el `try/except` está capturando todo y devolviendo 1 |
| Exit code 2 con el mensaje "no hay ninguna versión registrada" cuando MLflow está caído | se consultó la última versión sin comprobar antes que el registry responde; los dos casos se ven iguales |
| El job del gate se cuelga varios minutos | mlflow reintenta 7 veces con backoff por defecto. Hay que reducir timeout y reintentos para las consultas de metadatos |
| `gitleaks` en verde en local y rojo en CI | en local se escaneó el working tree; en CI, **el historial**. Un secreto borrado sigue en el historial |
| El comentario del PR aparece quince veces | falta el marcador HTML para encontrar y actualizar el comentario anterior |
| El deploy a producción corre sin aprobación | el `environment:` está declarado pero **no** se configuró el *required reviewer* en Settings |
| El PR movió `@champion` | falta el `--dry-run` en el evento `pull_request` |
| El workflow no arranca: `Node.js 20 is deprecated` | actions en versiones mayores viejas; sube a las que corren sobre Node 24 |

---

## Rúbrica

| Peso | Aspecto |
|---|---|
| 30% | El gate: los cinco pasos, con los umbrales declarados y justificados |
| 20% | La evidencia: rechazo **y** aceptación, los dos en el log del workflow |
| 15% | Los tests de la política, sin infraestructura |
| 15% | El CD: digest, gate antes del deploy, `--dry-run` en PR, comentario con `github-script` |
| 10% | Ambientes y aprobación, con la explicación de por qué la barrera va en el Environment |
| 10% | El ADR y el rollback documentado (los dos rollbacks) |

Descuentos: auto-promoción al final del entrenamiento, `latest` como referencia de
despliegue, credenciales en el repositorio, un paso de CI que no puede fallar, o
recursos de nube dejados sin destruir.
