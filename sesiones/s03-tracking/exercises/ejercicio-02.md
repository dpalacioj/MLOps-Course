# Ejercicio 02 — Model Registry: versiones, tags y aliases

**Notebook:** [`ejercicio-02-model-registry.ipynb`](ejercicio-02-model-registry.ipynb)
**Duración estimada:** 30 min
**Dataset:** Iris (clasificación)

---

## Contexto

El ejercicio 01 dejó un run con métricas y artefactos. Eso responde "¿qué probé y
con qué resultado?", pero no responde la pregunta operativa:

> ¿Qué modelo está sirviendo tráfico ahora mismo, y cómo lo cambio sin tocar el
> código de la aplicación?

Para eso existe el **Model Registry**: nombres estables, versiones inmutables,
aliases que se mueven y tags que documentan.

**Por qué Iris y no el caso guía:** el tema es el ciclo de vida en el registry.
Con Iris cada entrenamiento tarda menos de un segundo, así que caben dos versiones
y varios movimientos de alias en el tiempo de la clase. El dataset es lo menos
importante de este ejercicio.

## Objetivo

1. Loguear un modelo dentro de un run (*tracking*).
2. **Registrarlo** con nombre y versión (*registry*).
3. Marcarlo como validado con un **tag** y asignarle el **alias `champion`**.
4. Cargarlo **por versión** y **por alias**, y predecir con él.
5. Entrenar un segundo modelo, registrarlo como **v2** y dejarlo como
   `candidate` — **sin promoverlo**.

## Prerrequisitos

```bash
make mlflow    # tracking server con backend SQLite, en http://127.0.0.1:5001
```

> **Importante:** el Model Registry **necesita** un backend de base de datos. Con
> `mlflow ui` a secas o con un file store (`file://mlruns`), no existe, y los TODO
> 3 en adelante fallan. Es exactamente la diferencia entre el escenario 1 y el
> escenario 2 de [`../scenarios/`](../scenarios/).

---

## Los nueve TODO

| # | Qué haces | API vigente |
|---|---|---|
| 1 | Conectar y crear el experimento | `set_tracking_uri`, `set_experiment` |
| 2 | Loguear params, métrica y modelo en un run | `log_param`, `log_metric`, `log_model(sk_model=…, name=…)` |
| 3 | Registrar el modelo del run | `mlflow.register_model("runs:/<run_id>/modelo_rf", nombre)` |
| 4 | Marcar validación **y** asignar `champion` | `set_model_version_tag`, luego `set_registered_model_alias` |
| 5 | Cargar por número de versión | `models:/<nombre>/1` |
| 6 | Cargar por alias | `models:/<nombre>@champion` |
| 7 | Predecir y comparar con la métrica original | `modelo.predict(...)` |
| 8 | Entrenar y registrar la v2 en un paso | `log_model(..., registered_model_name=…)` |
| 9 | Dejar la v2 como `candidate` + `pending` | `set_registered_model_alias`, `set_model_version_tag` |

### Los tres detalles donde se equivoca todo el mundo

1. **`name=`, no `artifact_path=`.** Casi todos los tutoriales pasan el segundo
   argumento de `log_model` como `artifact_path` o de forma posicional.
   `artifact_path` está **deprecado** en los flavors de MLflow 3. El `pre-commit`
   del curso bloquea la forma vieja.
2. **El tag antes del alias.** Si el proceso muere entre las dos operaciones, el
   estado seguro es "validada pero no promovida". Al revés queda un modelo
   sirviendo tráfico sin registro de haber sido validado.
3. **Cargar por alias significa usar `@alias` en la URI.** Resolver el alias a un
   número de versión y construir `models:/nombre/<numero>` funciona, pero devuelve
   al código la dependencia de la versión que el alias venía a quitar.

---

## Criterios de completitud

Al terminar, la celda de verificación final debe mostrar:

| Elemento | Cantidad esperada | Valor |
|---|---|---|
| Versiones registradas | 2 | v1 y v2 de `iris-clasificacion` |
| Aliases | 2 | `champion` → v1, `candidate` → v2 |
| Tags de versión | 2 | `validation_status=passed` en v1, `pending` en v2 |
| Runs con modelo logueado | 2 | uno por versión, cada uno con su `accuracy` |
| Cargas del modelo | 2 | una por versión (`models:/…/1`) y una por alias (`models:/…@champion`) |

Y estos criterios cualitativos:

| # | Criterio | Cómo lo verificas |
|---|---|---|
| 6 | La `accuracy` del modelo cargado desde el registry es **idéntica** a la del modelo en memoria | la comparación del TODO 7 imprime `True` |
| 7 | Cada versión apunta al run que la generó | UI → Models → versión → *Source Run* |
| 8 | Ninguna celda usa la API de stages | busca `transition_model_version_stage` en el notebook: no debe aparecer en código |
| 9 | La v2 **no** es `champion` aunque tenga mejor `accuracy` | el alias `champion` sigue en v1 |

El criterio 9 es el conceptual: **registrar no es promover**. Decidir si la v2
merece ser champion exige un holdout, una comparación contra el champion actual y
la posibilidad de rechazar. Eso es el gate de S06 (`scripts/promote.py`), no un
`set_alias` porque la accuracy subió.

---

## Bonus (opcional)

1. **Promover.** Mueve `champion` a la v2 y comprueba que la v1 dejó de serlo
   automáticamente. Luego haz **rollback** a la v1. Cronometra las dos
   operaciones: es una escritura de metadatos.
2. **Descripción de versión.** `client.update_model_version(..., description=...)`
   con una frase que explique por qué existe esa versión.
3. **Buscar por tag.** Lista las versiones con `validation_status=passed` usando
   `client.search_model_versions`.
4. **Rómpelo a propósito.** Apunta `mlflow.set_tracking_uri("file://…/mlruns")` y
   vuelve a intentar el TODO 3. Lee el error: es la definición del escenario 1.

---

## Qué NO usar

| No usar | Usar | Motivo |
|---|---|---|
| `client.transition_model_version_stage(...)` | `client.set_registered_model_alias(...)` | deprecado desde MLflow 2.9.0 |
| `client.get_latest_versions(...)` | `client.get_model_version_by_alias(...)` | deprecado: su semántica dependía de los stages |
| `models:/<nombre>/Production` | `models:/<nombre>@champion` | referencia por stage |
| `log_model(modelo, "modelo_rf")` | `log_model(sk_model=modelo, name="modelo_rf")` | `artifact_path` está deprecado |
| `archive_existing_versions=True` | nada: el alias apunta a una sola versión | es propio de la API de stages |
