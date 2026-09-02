-- =============================================================================
-- Consultas de analisis sobre la tabla `predicciones`
-- =============================================================================
-- La tabla la escribe el pipeline batch (`src/taxi/flows/batch.py`). Cada fila
-- lleva la version del modelo que la produjo y el instante en que se produjo:
-- eso es lo que permite auditar el sistema en lugar de solo mirarlo.
--
-- Uso:
--   sqlite3 data/predicciones.db < sesiones/s04-orquestacion/01-pipeline-ml/consultas-predicciones.sql
--   sqlite3 -header -column data/predicciones.db   # modo interactivo
--
-- Nota sobre comentarios: en SQL el comentario de linea es `--`. La version
-- anterior de este archivo (`queries_batch_predictions`, sin extension) usaba
-- `#`, que **no es valido en SQLite**: el archivo entero fallaba al ejecutarse.
-- Y sin extension `.sql` ningun editor lo resaltaba ni ninguna herramienta lo
-- reconocia como consultas.
-- =============================================================================


-- 1. Volumen por corrida ------------------------------------------------------
-- Lo primero que se revisa cuando algo se ve raro: cuantas filas produjo cada
-- batch y con que version. Un batch con la mitad de filas de lo normal es un
-- incidente de datos, no una curiosidad.
SELECT
    batch_id,
    particion,
    model_version,
    COUNT(*)                                  AS predicciones,
    MIN(prediction_timestamp)                 AS inicio,
    ROUND(AVG(prediccion_minutos), 2)         AS media_min
FROM predicciones
GROUP BY batch_id, particion, model_version
ORDER BY inicio DESC;


-- 2. Comparacion entre versiones de modelo -----------------------------------
-- La pregunta que responde: cambio la distribucion de las predicciones al
-- cambiar de version? Un salto grande en la media sin cambio de datos es senal
-- de que la version nueva se comporta distinto, y conviene saberlo antes de que
-- lo note el negocio.
SELECT
    model_version,
    COUNT(*)                                  AS predicciones,
    ROUND(AVG(prediccion_minutos), 2)         AS media_min,
    ROUND(MIN(prediccion_minutos), 2)         AS min_min,
    ROUND(MAX(prediccion_minutos), 2)         AS max_min
FROM predicciones
GROUP BY model_version
ORDER BY CAST(model_version AS INTEGER);


-- 3. Distribucion por rango de duracion --------------------------------------
-- Prediction drift observable sin labels: si la proporcion de viajes "largos"
-- se mueve entre particiones, algo cambio en los datos o en el modelo.
SELECT
    particion,
    CASE
        WHEN prediccion_minutos < 10 THEN '1. menos de 10 min'
        WHEN prediccion_minutos < 20 THEN '2. de 10 a 20 min'
        WHEN prediccion_minutos < 30 THEN '3. de 20 a 30 min'
        ELSE                              '4. 30 min o mas'
    END                                       AS rango,
    COUNT(*)                                  AS cantidad,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY particion), 2) AS porcentaje
FROM predicciones
GROUP BY particion, rango
ORDER BY particion, rango;


-- 4. Trazabilidad de una prediccion concreta ---------------------------------
-- El caso real: alguien pregunta por que se le dijo que su viaje duraria 40
-- minutos. Esta consulta devuelve la respuesta completa: el modelo, su version,
-- el alias vigente en ese momento y las features exactas que se usaron.
SELECT
    id,
    prediction_timestamp,
    model_name,
    model_version,
    model_alias,
    model_uri,
    ROUND(prediccion_minutos, 2)              AS prediccion_min,
    PU_DO,
    trip_distance                             AS distancia_millas,
    hora_pickup,
    dia_semana_pickup
FROM predicciones
ORDER BY prediccion_minutos DESC
LIMIT 10;


-- 5. Predicciones atipicas ----------------------------------------------------
-- Desviacion respecto a la media de la misma particion. No es un test
-- estadistico: es un filtro para revisar a mano lo que mas se sale.
WITH estadisticas AS (
    SELECT
        particion,
        AVG(prediccion_minutos) AS media
    FROM predicciones
    GROUP BY particion
)
SELECT
    p.batch_id,
    p.model_version,
    p.PU_DO,
    ROUND(p.prediccion_minutos, 2)                          AS prediccion_min,
    ROUND(e.media, 2)                                       AS media_particion,
    ROUND(100.0 * (p.prediccion_minutos - e.media) / e.media, 1) AS desvio_pct
FROM predicciones AS p
JOIN estadisticas AS e ON e.particion = p.particion
WHERE p.prediccion_minutos > 2 * e.media
ORDER BY desvio_pct DESC
LIMIT 20;


-- 6. Verificacion de integridad ----------------------------------------------
-- Debe devolver cero filas. Si devuelve alguna, hay predicciones sin
-- trazabilidad y la tabla dejo de servir para auditar.
SELECT COUNT(*) AS filas_sin_trazabilidad
FROM predicciones
WHERE model_version IS NULL
   OR model_version = ''
   OR prediction_timestamp IS NULL;
