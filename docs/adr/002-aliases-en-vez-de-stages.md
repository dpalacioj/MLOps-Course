# ADR 002 — Aliases y tags del Model Registry, no stages

- **Estado:** aceptada
- **Fecha:** 2026-04
- **Alcance:** sesiones 3 a 7, `src/taxi/models/registry.py`, `scripts/promote.py`
- **Decisores:** equipo docente del curso de MLOps

## Contexto

El repositorio anterior **se contradecía a sí mismo**. El módulo de experiment
tracking enseñaba aliases como la práctica correcta, y los módulos de
orquestación y deployment promovían modelos con la API de stages:

```python
client.transition_model_version_stage(name, version, stage="Production")   # módulo 03
model = mlflow.pyfunc.load_model(f"models:/{name}/Production")             # módulo 04
```

Un estudiante que leyera los dos módulos no podía saber cuál era la práctica
vigente, y el estudiante que leyera solo el segundo aprendería una API deprecada
como si fuera la actual.

Verificación empírica (mlflow 3.15.1, agosto 2026):

- El método `transition_model_version_stage` del cliente **existe todavía**, pero
  está marcado como **deprecado desde MLflow 2.9.0** y la documentación oficial
  anuncia su eliminación en una versión mayor futura.
- `MlflowClient.get_latest_versions` está deprecado por la misma razón: su
  semántica era "la última versión *de cada stage*", un concepto que ya no
  existe.
- Los aliases y los tags de versión son la API de reemplazo y están plenamente
  soportados.

Había además un problema peor que la deprecación. El módulo de orquestación
**copiaba directorios de modelo con `shutil.copytree`** desde el módulo de
tracking, en lugar de resolverlos desde el registry. Eso destruye exactamente la
trazabilidad que el módulo anterior acababa de enseñar a construir: el artefacto
que se sirve deja de tener versión, run de origen y hash.

## Decisión

**El ciclo de vida del modelo se gestiona con aliases (routing) y tags de versión
(estado), y el modelo se referencia siempre por alias.**

Convenciones del curso, declaradas en `src/taxi/config.py`:

| Concepto | Valor | Significado |
|---|---|---|
| Alias de producción | `champion` | la versión que atiende tráfico |
| Alias de candidato | `candidate` | la versión recién registrada, sin validar |
| Tag de validación | `validation_status` | `pending` / `passed` / `failed` |
| Referencia canónica | `models:/nyc-taxi-duration@champion` | única forma de cargar el modelo |

El código prohibido y su reemplazo:

```python
# PROHIBIDO — API de stages
client.transition_model_version_stage(nombre, version, stage="Production")
mlflow.pyfunc.load_model(f"models:/{nombre}/Production")
client.get_latest_versions(nombre, stages=["Production"])

# CORRECTO — aliases + tags
client.set_model_version_tag(nombre, version, "validation_status", "passed")
client.set_registered_model_alias(nombre, "champion", version)
mlflow.pyfunc.load_model(f"models:/{nombre}@champion")
client.get_model_version_by_alias(nombre, "champion")
```

**El orden de escritura importa y es parte de la decisión:** primero el tag,
después el alias. Si el proceso muere entre las dos operaciones, el estado
resultante es "validada pero no promovida", que es seguro. El orden inverso
dejaría un modelo atendiendo tráfico sin registro de haber sido validado, que es
precisamente el incidente que el gate existe para evitar.

La coherencia se hace **ejecutable** en tres capas, porque una convención que solo
vive en un documento se rompe:

1. `scripts/hooks/mlflow_sin_stages.py` — hook de pre-commit que bloquea las APIs
   prohibidas, también en celdas de código de notebooks.
2. `tests/unit/test_config_y_convenciones.py` — el mismo chequeo como test, porque
   un hook se puede saltar con `--no-verify` y un test de CI no.
3. `registry.explicar_por_que_no_stages()` — el texto didáctico vive en el código,
   y el notebook y la model card lo imprimen desde ahí. Si estuviera duplicado en
   Markdown, en seis meses habría dos versiones que se contradicen: es
   literalmente lo que pasó en el repo anterior.

## Alternativas consideradas

**A. Seguir usando stages (statu quo).**
Ventaja: la mayoría de los tutoriales y cursos en la web todavía los usan, así
que el estudiante encontraría material coincidente.
Descartada: enseñar una API deprecada es enseñar deuda técnica. Y el argumento
"así aparece en los tutoriales" es justamente el problema a corregir: buena parte
del material de MLflow en la web está desactualizado respecto a la 2.9 y a la 3.x.

**B. Enseñar los dos, marcando cuál está deprecado.**
Ventaja: prepara al estudiante para leer código heredado, que es la mayoría del
código real.
Descartada como práctica del repositorio, **adoptada parcialmente como
contenido**: el código del curso usa solo aliases, y la API de stages aparece
únicamente como contraejemplo explícito en material didáctico (celda de markdown
o archivo excluido del hook). La diferencia clave es que el código ejecutable
nunca la usa: es lo que evita que el estudiante copie y pegue lo incorrecto.

**C. No usar Model Registry: versionar artefactos en S3/MinIO con convención de
nombres.**
Ventaja: menos infraestructura, funciona con cualquier bucket.
Descartada: hay que reimplementar linaje, metadatos, "quién es el que sirve" y
control de concurrencia. Se acaba escribiendo un registry peor. Sigue siendo la
alternativa razonable cuando MLflow no está disponible, y se menciona en clase
como tal.

**D. Un registry alternativo (Weights & Biases, Neptune, SageMaker Model
Registry, Vertex AI Model Registry).**
Ventaja: en varios casos, mejor UI y gobernanza más rica.
Descartada para el curso por costo y por acoplamiento a un proveedor. El concepto
que se enseña —referencia mutable a versión inmutable, más metadatos de
validación— es portable: los cuatro implementan la misma idea con otros nombres
(*model stage*, *model alias*, *approval status*). Lo que se enseña es el
concepto; MLflow es el vehículo.

**E. Aliases sin tags (solo `@champion` y `@candidate`).**
Descartada: el alias dice *qué versión sirve*, pero no *por qué llegó ahí*. Sin
`validation_status` no hay evidencia auditable de que el gate corrió, y en una
revisión post-incidente esa evidencia es lo primero que se busca.

## Consecuencias

**Positivas**

- **Vocabulario abierto.** Los stages eran cuatro palabras fijas
  (None/Staging/Production/Archived). Un equipo real necesita `champion`,
  `challenger`, `shadow`, `canary`, `champion-eu`. Un alias es un nombre libre por
  rol de servicio, lo que habilita A/B testing y shadow deployment sin inventar
  convenciones sobre los stages.
- **Separación de responsabilidades.** Un stage mezclaba routing con estado de
  validación. Aliases y tags las separan: el alias enruta, el tag documenta.
- **Unicidad garantizada.** Un alias apunta a exactamente una versión. Con stages,
  dos versiones podían quedar en `Production` a la vez y nadie sabía cuál
  respondía.
- **Rollback de un segundo.** Volver atrás es mover `@champion` a la versión
  anterior: una escritura de metadatos, sin reentrenar, sin rebuild de imagen, sin
  redeploy. Las versiones son inmutables, así que el artefacto anterior es bit a
  bit el que estaba sirviendo. Esta propiedad es la razón principal por la que el
  modelo se referencia por alias y no se copia a un directorio.
- **La API deja de conocer números de versión.** El servicio carga
  `models:/nyc-taxi-duration@champion`; promover no requiere tocar ni redeployar
  la aplicación (a lo sumo, recargar el modelo).

**Negativas y su mitigación**

- *Requiere MLflow ≥ 2.9 con backend de base de datos.* Los aliases no están
  disponibles con el file store. Mitigación: el curso usa
  `sqlite:///mlflow.db` en local y Postgres en el stack de Docker. Nota
  verificada: en mlflow 3.15 el file store está en modo mantenimiento y exige
  `MLFLOW_ALLOW_FILE_STORE=true` para siquiera arrancar, así que la base de datos
  dejó de ser opcional de todos modos.
- *El material externo que el estudiante encuentre usará stages.* Mitigación: se
  aborda de frente en clase, con el hook como recordatorio mecánico y el ADR como
  explicación.
- *Los aliases son mutables: un alias mal movido cambia producción al instante.*
  Es el precio de un rollback instantáneo, y se acota con el gate
  (`scripts/promote.py`, exit code 1 detiene el CD) y con la aprobación manual del
  environment `production` en `.github/workflows/cd.yml`.
- *Hay que decidir qué hacer con `@candidate` tras el gate.* Convención adoptada:
  se conserva hasta el siguiente registro, para poder inspeccionar el rechazado.

## Referencias

- `src/taxi/models/registry.py` — la implementación y `explicar_por_que_no_stages()`
- `scripts/promote.py` — el gate: tag primero, alias después
- `scripts/hooks/mlflow_sin_stages.py` — la convención hecha ejecutable
- `docs/adr/001-caso-guia-y-particiones.md` — el holdout que juzga la promoción
- Documentación oficial de MLflow: Model Registry, sección de aliases y tags
