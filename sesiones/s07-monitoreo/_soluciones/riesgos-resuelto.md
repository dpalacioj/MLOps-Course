# Registro de riesgos — `nyc-taxi-duration`

> Solución de referencia de `../plantillas/riesgos.md`, aplicada al caso guía.

- **Sistema:** predicción de la duración de un viaje de taxi verde en NYC
- **Modelo:** `models:/nyc-taxi-duration@champion`
- **Responsable del registro:** instructor del curso (rol *ML platform owner*)
- **Fecha:** 2026-08-19 · **Próxima revisión:** 2026-11

---

## 1. Clasificación regulatoria (AI Act)

| Campo | Valor |
|---|---|
| Rol en la cadena de valor | proveedor (se desarrolla y se pone a disposición el sistema) |
| Clasificación tentativa | **riesgo mínimo** |
| Base de la clasificación | predecir la duración de un viaje no está en el anexo III: no decide sobre acceso al empleo, al crédito, a la educación ni a servicios esenciales; no hace inferencia biométrica ni categorización de personas. Tampoco genera contenido sintético ni simula interacción humana, así que **no** activa el art. 50 |
| Fecha de aplicación que le corresponde | ninguna obligación específica. Aplican las transversales ya en vigor: prohibiciones y **alfabetización en IA** (art. 4) desde el **2-feb-2025** |
| Qué tendría que cambiar para subir de categoría | **(a)** si el modelo pasara a decidir qué conductores reciben viajes o a evaluar su desempeño → **anexo III (empleo)**, aplicable desde el **2-dic-2027**; **(b)** si puntuara la solvencia de clientes para pago diferido → **anexo III (crédito)**; **(c)** si identificara pasajeros por reconocimiento facial → alto riesgo, y según el uso podría caer en las **prohibiciones del art. 5** |

Nota sobre la obligación que sí aplica y suele pasarse por alto: el art. 4
(alfabetización en IA) obliga a proveedores y responsables del despliegue a asegurar un
nivel suficiente de competencia en IA en su personal, y está en vigor desde febrero de
2025 **independientemente del nivel de riesgo**. Para un curso es una obligación fácil
de cumplir; para una empresa, no es trivial.

*Fechas y fuentes primarias en [`../gobernanza.md`](../gobernanza.md) sección 2, verificadas el
19 de agosto de 2026. El Digital Omnibus entró en vigor el 27-jul-2026 y aplazó el alto
riesgo del anexo III de agosto de 2026 a diciembre de 2027.*

---

## 2. Riesgos

### R1 — Umbral de drift por debajo del ruido del estimador

| Campo | Contenido |
|---|---|
| Descripción | el umbral de `PU_DO` (V de Cramér 0.10) quedaba **por debajo** de su ruido medido bajo la hipótesis nula (0.119): el detector alertaba comparando dos mitades del mismo mes. Consecuencia: alerta permanente, el equipo la silencia y pierde la señal real |
| Probabilidad / Impacto | alta (ya ocurrió) / medio |
| Detección | `estadistico.linea_base_nula` en cada recalibración; el test `test_control_negativo_sin_drift_en_ninguna_columna` lo bloquea en CI |
| Mitigación | umbral subido a 0.15 con la medición documentada en `docs/adr/003-umbrales-de-drift.md`; recalibración trimestral |
| Responsable | ML platform owner |
| Riesgo residual | el ruido depende del `n` del lote; si el volumen mensual cambia mucho, la calibración caduca. Se revisa junto con la alerta de volumen |

### R2 — Estacionalidad interpretada como drift, y reentrenamiento innecesario

| Campo | Contenido |
|---|---|
| Descripción | el verano cambia las distribuciones todos los años. Reentrenar en respuesta convierte un patrón conocido en un ciclo de cambios en producción, cada uno con su riesgo de regresión, sin ganancia de calidad |
| Probabilidad / Impacto | alta / medio |
| Detección | comparar el efecto contra el mismo mes del año anterior frente a otro mes del mismo año. Medido: en las 7 columnas el efecto contra julio supera el efecto contra enero+1año |
| Mitigación | añadir el mes o un indicador de temporada como feature y entrenar con ≥ 12 meses; la política declara explícitamente que el patrón estacional identificado **no** es trigger |
| Responsable | ML platform owner |
| Riesgo residual | si un año el cambio de verano es de naturaleza distinta (una obra, un evento), se confundirá con el patrón conocido. Mitigación parcial: vigilar `PU_DO`, que es la columna con más señal |

### R3 — Degradación en un subgrupo oculta por el promedio

| Campo | Contenido |
|---|---|
| Descripción | el RMSE global mejora mientras empeora en viajes muy largos o en madrugada. Medido en el caso guía: el RMSE de `dist_muy_larga` es el doble del global y crece en 2024-01 (12.15 → 13.31) mientras el RMSE global **baja**. El promedio dice "mejor"; el usuario de ese segmento dice "peor" |
| Probabilidad / Impacto | alta (ya observado) / alto |
| Detección | `taxi.models.evaluate.metricas_por_subgrupo` por franja horaria y rango de distancia, con `MIN_FILAS_SUBGRUPO=50` |
| Mitigación | el gate bloquea la promoción si un subgrupo se degrada > 5%; el reporte de monitoreo incluye los subgrupos, no solo el global |
| Responsable | ML platform owner + revisor del PR |
| Riesgo residual | solo se vigilan los subgrupos definidos (hora y distancia). Un subgrupo relevante no anticipado —p. ej. por zona de renta— no se vigila, y si la variable no está en los datos no se puede vigilar. Declarado explícitamente |

### R4 — Fallo silencioso del pipeline de datos

| Campo | Contenido |
|---|---|
| Descripción | la TLC republica un parquet, cambia una unidad (millas → km) o entrega un mes parcial. El modelo predice sobre datos con otro significado sin lanzar ningún error, y el dashboard del servicio sigue verde porque la latencia no cambia |
| Probabilidad / Impacto | media / alto |
| Detección | verificación de SHA-256 en `loaders.descargar_particion` (avisa si el proveedor republicó); contrato de datos con pandera; alerta de volumen del lote (< 30.000 filas); conteo de categorías nuevas |
| Mitigación | el contrato falla temprano y el batch no escribe resultados; el hash invalida explícitamente las métricas calculadas con la versión anterior del archivo |
| Responsable | equipo de datos |
| Riesgo residual | un cambio de **significado** con el mismo tipo y el mismo rango no lo detecta ningún contrato. Es el caso que solo aparece como drift, y con retraso |

### R5 — Reentrenamiento que degrada, promovido sin control humano

| Campo | Contenido |
|---|---|
| Descripción | un ciclo automático entrena con un lote contaminado y promueve el resultado; el rollback nunca se ensayó y tarda horas, o nadie sabe qué versión era la buena |
| Probabilidad / Impacto | baja / muy alto |
| Detección | gate con holdout fijo (`2023-05`) y comparación contra el champion; métricas del servicio y `taxi_modelo_info` tras el despliegue |
| Mitigación | el flow solo produce `@candidate` con `validation_status=pending`; la promoción requiere aprobación humana; el rollback es una reasignación de alias, ensayada y cronometrada (objetivo: 10 min) |
| Responsable | ML platform owner |
| Riesgo residual | **el holdout envejece.** Si el mundo cambió, el holdout aprueba modelos que ya no sirven, y el gate da una falsa garantía. Se revisa su vigencia cada 6 meses; no hay solución limpia, solo el compromiso de revisarlo |

---

## 3. Riesgos descartados y por qué

| Riesgo | Por qué no se gestiona ahora |
|---|---|
| Ataque adversario sobre las features de entrada | la API es interna y docente; nadie tiene incentivo para manipular una predicción de duración. Se revisará si se expone públicamente o si la predicción llega a afectar un precio |
| Fuga de datos personales por el endpoint de métricas | las métricas expuestas no contienen datos de viajes: los labels son `model_version`, `clase` y `tipo`, todos de cardinalidad acotada y sin información de la petición. Es además la razón por la que no se admite `PU_DO` como label |
| Reidentificación de personas a partir del dataset | los datos de la TLC son públicos y agregados por zona (265 zonas), no por coordenada. Con coordenadas exactas el análisis sería distinto y habría que rehacer esta fila |
| Coste de inferencia | el modelo es lineal o de árboles sobre CPU y sirve en milisegundos; el coste no es un riesgo material a esta escala. Se reevaluará si se cambia a un modelo con GPU |
