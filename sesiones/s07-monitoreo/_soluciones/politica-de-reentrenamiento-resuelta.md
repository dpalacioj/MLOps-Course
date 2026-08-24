# Política de reentrenamiento — `nyc-taxi-duration`

> Solución de referencia de `../plantillas/politica-de-reentrenamiento.md`, aplicada al
> caso guía. Los nombres de personas son roles del curso; en un sistema real son
> personas con nombre.

- **Sistema / modelo registrado:** `models:/nyc-taxi-duration@champion`
- **Responsable de esta política:** instructor del curso (rol: *ML platform owner*)
- **Última revisión:** 2026-08 · **Próxima revisión:** 2026-11
- **Clasificación AI Act:** riesgo mínimo (ver `riesgos-resuelto.md` sección 1)

---

## 1. Trigger — qué dispara un reentrenamiento

| Tipo | Condición exacta | Fuente de la señal | Frecuencia |
|---|---|---|---|
| Drift de datos | fracción de columnas con drift **> 0.30** (`UMBRAL_DRIFT_COLUMNAS`) | `python -m taxi.monitoring.check_drift`, exit code 1 | semanal |
| Degradación de performance | RMSE de la última partición mensual **> 1.10 ×** RMSE del holdout `2023-05` | job de evaluación con etiquetas | mensual |
| Calendario | el día 5 de cada mes, si no se disparó ninguno de los anteriores en 90 días | schedule del deployment de Prefect (S04) | mensual |
| Evento de negocio | cambio de tarifa de la TLC, o cambio de esquema del parquet publicado | aviso del equipo de datos, o fallo del contrato de S02 | — |
| Volumen | el lote mensual cae por debajo de **30.000 filas** (la mitad de lo habitual) | mismo check, señal de volumen | mensual |

**Label lag de este sistema:** minutos. La duración real del viaje se conoce al
terminarlo, así que el trigger por performance **sí** es utilizable como señal primaria
y el de drift es una señal temprana complementaria. Es un caso afortunado y hay que
decirlo: en la mayoría de los sistemas reales el orden se invierte.

**Lo que NO dispara un reentrenamiento:**

- drift en una sola columna, por encima de su umbral pero con el dataset por debajo del
  30%. Es el caso medido en julio de 2023 (1/7 columnas): se registra y se vigila;
- un fallo del contrato de datos. Eso se arregla en el pipeline; reentrenar sobre datos
  malos los incorpora al modelo;
- **el patrón estacional de verano**, ya identificado como recurrente con evidencia (el
  efecto contra julio es mayor que contra enero del año siguiente en las 7 columnas).
  Se modela como feature. La entrada correspondiente está en el registro de decisiones.

## 2. Datos — con qué se reentrena

- **Ventana:** los 3 meses inmediatamente anteriores al periodo que disparó la alerta.
  Justificación: es la ventana con la que se entrenó el champion, así que el
  reentrenamiento es comparable; ampliarla es una decisión de modelado que requiere su
  propio experimento.
  *Excepción declarada:* si el diagnóstico es estacionalidad, la ventana pasa a **12
  meses** y se añade el mes como feature. Eso no es un reentrenamiento: es un cambio de
  modelo y va por el ciclo completo de S03.
- **Se incluyen los datos que dispararon la alerta:** sí, si pasaron el contrato.
- **Validación:** split **temporal** — train hasta el mes `M`, validación en `M+1`.
  Nunca aleatorio: con datos temporales produce leakage y una métrica optimista.
- **Holdout de decisión:** `PARTICION_TEST = 2023-05`, fijo. No se toca para tunear.
  *Riesgo aceptado:* el holdout envejece; su vigencia se revisa cada 6 meses.
- **Contrato aplicado antes de entrenar:** sí — `taxi.data.contract.validar_crudos` y
  `validar_procesados`, dentro de `preparar_particion`.

## 3. Aprobación — quién decide

| Paso | Quién | Qué mira | Puede vetar |
|---|---|---|---|
| Reentrenamiento lanzado | automático (deployment de Prefect) | — | — |
| Gate técnico | automático (`taxi promote`) | mejora global ≥ 1% (`MEJORA_MINIMA_RELATIVA`) y ningún subgrupo degradado > 5% (`UMBRAL_DEGRADACION_SUBGRUPO`) | sí: exit code 1 bloquea el merge |
| Aprobación de promoción | **instructor del curso** (rol *ML platform owner*) | métricas globales y por subgrupo, model card regenerada, reporte de drift que motivó el ciclo | sí |
| Notificación | PR en el repositorio + canal del curso | — | — |

**El reentrenamiento produce un `@candidate`, nunca un `@champion`.** El flow de
entrenamiento registra con `validation_status=pending`; solo `scripts/promote.py` mueve
el alias, y solo después de la aprobación.

## 4. Rollback — cómo se vuelve atrás

- **Síntomas que disparan el rollback:** p95 de inferencia > 100 ms durante 5 min, o
  tasa de error > 1%, o RMSE del batch diario > 1.20 × el del holdout.
- **Quién puede ejecutarlo sin pedir permiso:** cualquiera del equipo de plataforma.
  *Un rollback que requiere autorización no se ejecuta a las 3 de la mañana.*
- **Cómo:**

  ```bash
  # 1. Ver que version esta sirviendo ahora
  uv run python -c "from taxi.models import registry; print(registry.version_por_alias('nyc-taxi-duration', 'champion'))"

  # 2. Reasignar el alias a la version anterior (N es la version buena conocida)
  uv run python -c "from taxi.models import registry; registry.asignar_alias('nyc-taxi-duration', 'champion', 'N')"

  # 3. Forzar que el servicio recargue el modelo. La API resuelve el alias al
  #    arrancar, asi que el reinicio del contenedor es lo que aplica el cambio.
  docker compose restart api

  # 4. Verificar QUE version esta respondiendo de verdad (no lo que deberia)
  curl -s localhost:8000/modelo | python -m json.tool
  curl -s localhost:8000/metrics | grep taxi_modelo_info
  ```

  *Detalle que hay que decir en clase:* el paso 3 existe porque el proceso resuelve
  `models:/...@champion` una sola vez, al arrancar. Mover el alias **no** cambia lo que
  sirve un proceso ya en marcha. Es el tipo de suposición que se descubre a mitad de un
  incidente, y la razón por la que el paso 4 comprueba la versión en `/metrics` en lugar
  de confiar en el paso 2.

- **Tiempo objetivo de vuelta atrás:** 10 minutos desde la decisión.
- **La versión anterior se conserva:** sí. El registry no borra versiones; el rollback es
  reasignar un alias, no re-desplegar un artefacto. Esa es la razón técnica por la que
  el curso usa aliases y no stages (ADR 002).
- **Se ha probado el rollback:** ensayo en clase, sesión 6. Se repite cada semestre.
  *Un rollback no ensayado no es un rollback: es una esperanza.*

## 5. Registro — qué queda escrito

Cada ciclo de reentrenamiento deja, sin excepción:

- [x] run de MLflow con params, métricas, artefactos y el hash de los datos
      (`data/raw/metadata.json`);
- [x] el reporte de drift que lo motivó, archivado con su nombre de particiones
      (`reports/drift_<ref>__vs__<actual>.{html,json}`), no sobrescrito;
- [x] la decisión del gate (`validation_status=passed|failed`) y quién la aprobó (autor
      del merge);
- [x] la model card regenerada: `uv run taxi model-card`;
- [x] entrada en el CHANGELOG con el motivo en una frase;
- [x] si se rechazó el candidato: el motivo del gate y qué se hizo en su lugar.

## 6. Casos que esta política no cubre

- **Cambio de esquema en el parquet de la TLC** (una columna se renombra o cambia de
  unidad): requiere revisar el contrato de datos y las features antes de reentrenar.
  Reentrenar sin eso produce un modelo que aprende el error.
- **Aparición de zonas nuevas** (`PULocationID` inexistente en entrenamiento): requiere
  revisar la evaluación por subgrupo antes de promover, porque el modelo no tiene
  información sobre ellas y el promedio global no lo mostrará.
- **Caída total de la fuente de datos:** es un plan de degradación del servicio (servir
  el último modelo con un aviso, o devolver 503), no un plan de reentrenamiento.
- **Cambio del target o de la definición de negocio:** no es reentrenamiento, es un
  modelo nuevo, con su propio experimento y su propia model card.
