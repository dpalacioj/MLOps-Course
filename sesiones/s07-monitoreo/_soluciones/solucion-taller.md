# Solución de referencia — Taller S07

Aplicada al caso guía (`nyc-taxi-duration`). Los números son los **medidos** en agosto
de 2026 con `evidently 0.7.21` y `scipy 1.17.1`. Los del proyecto de cada estudiante
serán distintos, y eso es correcto.

Toda la evidencia de este documento se regenera con:

```bash
bash sesiones/s07-monitoreo/_soluciones/evidencia.sh
```

---

## Criterio 1 — el reporte se genera desde el pipeline

`src/taxi/monitoring/check_drift.py` expone:

- `ejecutar_check(...)` — función pura de orquestación: carga, mide, escribe artefactos
  y devuelve un `ResultadoCheck`. No llama a `sys.exit`, así que se puede usar desde un
  flow, un notebook o un test.
- `ejecutar` — comando de click, que es el que termina el proceso con exit code.

Se invoca por tres rutas, todas equivalentes en lo que miden:

```bash
uv run python -m taxi.monitoring.check_drift        # CI
uv run taxi drift --particion 2024-01               # CLI del curso
```

El notebook `01-drift-real.ipynb` **explora**; no es el que produce el artefacto de
producción. Esa separación es el criterio: si el único sitio donde existe el análisis es
un notebook, no hay monitoreo, hay un análisis.

## Criterio 2 — el check falla con drift

```
$ uv run python -m taxi.monitoring.check_drift --actual 2023-07 --umbral 0.10 --sin-mlflow
Columnas con drift: 1/7 = 14% (umbral 10%)
Por que:
  - PU_DO: test de Evidently: FAIL (metodo Jensen-Shannon distance)
VEREDICTO: ALERTA DE DRIFT
EXIT CODE: 1
```

Nota honesta sobre el caso guía: con el umbral de dataset del curso (30%) julio de 2023
**no** dispara la alerta, porque solo 1 de 7 columnas supera su umbral. Para demostrar
el criterio 2 de forma determinista en clase se baja el umbral a 0.10. Eso no es hacer
trampa: es la diferencia entre demostrar el **mecanismo** (el exit code funciona) y
demostrar el **veredicto** (este mes hay o no hay drift). Con drift sintético las dos
cosas se confunden, y por eso el material anterior no enseñaba ninguna.

## Criterio 3 — el check pasa sin drift (control negativo)

```
$ uv run python -m taxi.monitoring.check_drift \
    --referencia 2023-01,2023-02,2023-03 --actual 2023-01,2023-02,2023-03 --sin-mlflow
Columnas con drift: 0/7 = 0% (umbral 30%)
VEREDICTO: sin alerta
EXIT CODE: 0
```

Este es el criterio que valida el anterior. Un detector que devolviera `True` siempre
pasaría el criterio 2 y fallaría este.

## Criterio 4 — el veredicto usa tamaño de efecto

Del JSON generado (`reports/drift_*.json`), una entrada de `detalle`:

```json
{
  "columna": "trip_distance",
  "tipo": "numerica",
  "metodo": "ks_2samp",
  "estadistico": 0.0058,
  "p_valor": 0.09648,
  "tamano_efecto": 0.0058,
  "nombre_efecto": "ks_d",
  "umbral_efecto": 0.07,
  "psi": 0.0001114,
  "jensen_shannon": 0.004483,
  "drift": false,
  "motivo": "sin evidencia: efecto=0.0058, p=0.09648"
}
```

El campo `motivo` es el que se lee en la revisión. Los cuatro estados posibles están en
el README sección 3.2; el más informativo es "significativo pero no relevante", que es el que
el criterio por p-valor habría reportado como alerta.

## Criterio 5 — umbrales calibrados

Medición con `estadistico.linea_base_nula` sobre la referencia (180.000 filas):

| Feature | Ruido (nulo) | Umbral | Señal vs 2023-07 | Señal vs 2024-01 | Umbral > ruido |
|---|---|---|---|---|---|
| `trip_distance` | 0.0040 | 0.07 | 0.0418 | 0.0236 | sí |
| `hora_pickup` | 0.0055 | 0.15 | 0.0209 | 0.0092 | sí |
| `dia_semana_pickup` | 0.0034 | 0.15 | 0.0568 | 0.0537 | sí |
| `duration` | 0.0047 | 0.10 | 0.0228 | 0.0130 | sí |
| `PULocationID` | 0.0352 | 0.10 | 0.1340 | 0.0891 | sí |
| `DOLocationID` | 0.0345 | 0.10 | 0.0745 | 0.0675 | sí |
| `PU_DO` | **0.1192** | **0.15** | 0.1866 | 0.1604 | sí |

`PU_DO` es el hallazgo del ejercicio: con el default razonable para una categórica
(0.10) el umbral queda **por debajo de su propio ruido** y el detector alerta comparando
dos mitades del mismo mes. Documentado en `docs/adr/003-umbrales-de-drift.md`.

## Criterio 6 — `/metrics` expone tres o más métricas

`src/taxi/api/metricas.py` expone cuatro métricas propias (nueve familias de series
contando `_bucket`, `_sum`, `_count`):

| Métrica | Tipo | Por qué ese tipo |
|---|---|---|
| `taxi_predicciones_total` | Counter | evento acumulativo; se consulta con `rate()` |
| `taxi_inferencia_duracion_segundos` | Histogram | hay que agregar el p95 entre réplicas, y un Summary no se puede agregar |
| `taxi_errores_total` | Counter | ídem predicciones, con `tipo` como conjunto cerrado |
| `taxi_modelo_info` | Gauge | info metric; se limpia con `.clear()` al promover para no dejar dos versiones activas |

## Criterio 7 — Grafana grafica esas métricas

`observabilidad/grafana/dashboards/api-modelo.json`, provisionado por
`observabilidad/grafana/provisioning/`, 8 paneles. El panel "Distribución de
predicciones por clase" es el que hace de puente entre las dos mitades de la sesión: es
prediction drift observable en tiempo real, con una métrica de Prometheus.

## Criterio 8 — la política nombra trigger, aprobador y rollback

Ver `politica-de-reentrenamiento-resuelta.md`. Los tres campos, resumidos:

- **trigger:** fracción de columnas con drift > 0.30 en la evaluación semanal, **o**
  RMSE de 7 días > 1.10 × RMSE del holdout;
- **aprobador:** una persona identificable con nombre y rol, no "el equipo";
- **rollback:** reasignar el alias `champion` a la versión anterior con
  `taxi promote`/`registry.asignar_alias`, con objetivo de 10 minutos y un ensayo
  fechado.

## Criterio 9 — el reentrenamiento no promueve solo

El flow de S04 registra con alias `candidate` y `validation_status=pending`. Ninguna
ruta del código de monitoreo toca `champion`. El hook `scripts/hooks/mlflow_sin_stages.py`
y el gate de S06 son los que sostienen la regla.

## Criterio 10 — ADR de umbrales

`docs/adr/003-umbrales-de-drift.md`, con las seis alternativas descartadas y sus
motivos, incluidas las tres que suenan mejor de lo que son (alfa más estricto,
Bonferroni, delegar el umbral a `drift_share` de Evidently).

---

## La parte que no tiene checklist: ¿drift o estacionalidad?

Evidencia medida sobre el caso guía:

| Feature | Efecto vs 2023-07 (otro mes) | Efecto vs 2024-01 (mismo mes, +1 año) |
|---|---|---|
| `trip_distance` | 0.0418 | 0.0236 |
| `hora_pickup` | 0.0209 | 0.0092 |
| `dia_semana_pickup` | 0.0568 | 0.0537 |
| `duration` | 0.0228 | 0.0130 |
| `PU_DO` | 0.1866 | 0.1604 |
| `PULocationID` | 0.1340 | 0.0891 |
| `DOLocationID` | 0.0745 | 0.0675 |

**En las siete columnas** el efecto contra julio es mayor que contra enero del año
siguiente. La posición en el año explica más que el paso del tiempo: es evidencia de
**estacionalidad**, no de una deriva permanente.

Y la prueba que zanja la discusión, con el modelo lineal del curso entrenado en
2023-01..03:

| Periodo | RMSE | vs validación |
|---|---|---|
| valid 2023-04 | 5.9254 | — |
| prod 2023-07 | 6.1216 | **+3.3%** |
| prod 2024-01 | 5.7683 | **−2.7%** |

**Hay drift de datos medible y no hay degradación relevante de performance.** En julio
el modelo pierde 3,3% de RMSE; un año después es incluso mejor que en validación.

**Decisión defendida:** no reentrenar por esta alerta. Acciones concretas:

1. registrar el hallazgo y la evidencia (este documento y el JSON archivado);
2. añadir el mes o un indicador de temporada como feature y entrenar con al menos un
   ciclo anual completo, para que el modelo aprenda el patrón en lugar de perseguirlo;
3. recalibrar el umbral de `PU_DO` con la línea base nula, que es lo único que estaba
   mal calibrado;
4. seguir vigilando `PU_DO`: es la única columna cuya señal supera con margen su ruido,
   y la mezcla de rutas es lo que más afecta a un modelo que usa el par origen-destino
   como feature.

Un estudiante que llegue a la conclusión contraria (reentrenar) **no está
equivocado por definición**: lo que se evalúa es si la decisión está sostenida por la
evidencia que él mismo midió y si declaró el coste de equivocarse en cada dirección.
Lo que no se acepta es "el detector se puso rojo, así que reentreno".
