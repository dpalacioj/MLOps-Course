# Solución de referencia — Taller S05

Recorrido del taller aplicado al caso guía. Cada sección apunta al archivo del
repositorio que satisface el criterio y dice **qué se acepta como alternativa
válida**, porque el taller se hace sobre el proyecto de cada estudiante.

---

## 1. La decisión de forma de servicio

Párrafo de referencia para el caso guía:

> El consumidor principal del modelo de duración es la aplicación que le muestra al
> pasajero el tiempo estimado **antes** de aceptar el viaje. Latencia tolerada:
> cientos de milisegundos, porque hay una persona esperando en una pantalla. Volumen:
> un viaje por request, con picos en hora punta. Frescura de features: la del momento
> del request (la hora del pickup **es** una feature). Costo: hay que sostener un
> servicio disponible. Complejidad operativa: media — vigilar p95 y disponibilidad.
> Con esos cinco criterios, **online**.
>
> El batch se mantiene además, para un caso distinto y real: el reporte de planeación
> de flota, que se lee cada mañana sobre la partición del mes. No es el mismo modelo
> sirviendo dos veces por comodidad: son dos consumidores con requisitos de latencia
> incompatibles.
>
> Streaming se descarta: no hay consumidor que necesite reaccionar a un flujo de
> eventos, y el costo operativo (broker, estado en ventana, reprocesamiento) no se
> paga con nada.

**Qué se acepta:** cualquiera de las tres, con los cinco criterios instanciados en
números o rangos concretos del proyecto. **Qué no:** "elegí online porque es lo que
vimos", o una tabla copiada del README sin instanciar.

---

## 2. Criterio 1 — `docker compose up` y `/health` con la versión

```bash
make up
curl -s http://127.0.0.1:8000/health | jq
```

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_name": "nyc-taxi-duration",
  "model_version": "7",
  "model_uri": "models:/nyc-taxi-duration@champion",
  "version_api": "1.0.0"
}
```

Dónde está: el servicio `api` de [`docker-compose.yml`](../../../docker-compose.yml)
con `TAXI_MODELO_URI` por **alias** y `depends_on: mlflow: condition:
service_healthy`; el endpoint en
[`main.py`](../../../src/taxi/api/main.py) (`@app.get("/health")`).

Punto de discusión frecuente: si `model_version` sale `"desconocida"`, el modelo
cargó pero **no se pudo resolver el alias** contra el registry. Es un estado válido
(el servicio predice) pero degradado en auditabilidad: en los logs quedaría
`champion` y no el número. Se acepta con la advertencia explicada; no se acepta si el
estudiante no sabe distinguirlo de "todo bien".

## 3. Criterio 2 — No corre como root

```bash
docker run --rm --entrypoint sh mlops-curso/api:ci -c 'id -u'   # -> 1001
```

Dónde está: el `groupadd`/`useradd` + `USER taxi` de la etapa `runtime` del
[`Dockerfile`](../../../Dockerfile), y el paso *"La imagen NO debe correr como root"*
del job `imagen` en [`ci.yml`](../../../.github/workflows/ci.yml).

Detalle que vale nombrar en la revisión: el usuario se crea **antes** del `COPY`, y
el `COPY --chown` asigna la propiedad en la misma capa. Un `chown -R` posterior
duplicaría el tamaño del venv en una capa extra.

## 4. Criterio 3 — El `HEALTHCHECK` funciona

```bash
docker compose ps          # STATUS: Up 2 minutes (healthy)
docker inspect --format='{{json .State.Health}}' <contenedor> | jq
```

Dónde está: el `HEALTHCHECK` del `Dockerfile`, con `python -c "... urllib.request
..."` en lugar de `curl`. El `docker-compose.yml` **no** redefine el healthcheck a
propósito: pertenece a la imagen, porque depende de qué binarios tiene la imagen.
Dos definiciones se desincronizan.

Si un estudiante entrega un healthcheck con `curl` sobre una base slim, el
diagnóstico es inmediato:

```bash
docker run --rm --entrypoint sh su-imagen -c 'command -v curl || echo "no hay curl"'
```

## 5. Criterio 4 — ≥4 tests de API, sin registry ni red

```bash
uv run pytest tests/api -q          # con MLflow apagado
```

Dónde está: [`tests/api/`](../../../tests/api/). Los cuatro que el taller pide se
corresponden con:

| Pedido en el taller | Test del repositorio |
|---|---|
| 200 con `model_version` | `test_predict_devuelve_el_esquema_completo_con_model_version` |
| 422 con entrada inválida | `test_zona_fuera_de_rango_se_rechaza`, `test_campo_desconocido_se_rechaza` |
| 503 sin modelo, `/health` en 200 | `test_predict_sin_modelo_devuelve_503`, `test_health_sin_modelo_responde_200_y_model_loaded_false` |
| 500 sin filtrar internals | `test_error_interno_no_filtra_el_mensaje_de_la_excepcion` |

La costura que lo hace posible está en
[`tests/api/conftest.py`](../../../tests/api/conftest.py): `CargadorModelo` recibe
`cargar_pyfunc` por constructor y el cargador se inyecta con
`app.dependency_overrides`. Es el mecanismo idiomático de FastAPI y no requiere
`monkeypatch` de módulos.

Lo que se rechaza: tests marcados `@pytest.mark.skip` "porque necesitan MLflow". Un
test que depende de un servicio externo no es un test unitario; si no se puede
inyectar el doble, el acoplamiento con MLflow está mal contenido y **eso** es el
hallazgo.

## 6. Criterio 5 — SQL con la versión del modelo

```bash
make batch
sqlite3 -header -column data/predicciones.db \
  "SELECT model_version, model_alias, COUNT(*) AS n, ROUND(AVG(prediccion_minutos),2) AS media_min
     FROM predicciones GROUP BY 1, 2 ORDER BY 1;"
```

```text
model_version  model_alias  n      media_min
-------------  -----------  -----  ---------
7              champion     58412  13.91
```

Dónde está: `COLUMNAS_FILA` y `construir_filas` en
[`flows/batch.py`](../../../src/taxi/flows/batch.py). Consultas de análisis en
[`consultas-predicciones.sql`](../../s04-orquestacion/01-pipeline-ml/consultas-predicciones.sql).

Las cifras de arriba son **ilustrativas del formato**, no un valor esperado: dependen
de la partición, del muestreo y del modelo. Lo que se evalúa es que la columna exista
y esté poblada con la versión real que resolvió el alias, no con un literal.

## 7. Criterio 6 — Los errores no filtran internals

El test lo demuestra: se inyecta un modelo que lanza una excepción con un texto
reconocible y se verifica que ese texto **no** aparece en el cuerpo de la respuesta.

```python
cargador, _ = cargador_con_modelo(excepcion=RuntimeError("detalle-secreto-del-servidor"))
respuesta = crear_cliente(cargador).post("/predict", json=VIAJE_VALIDO)
assert respuesta.status_code == 500
assert "detalle-secreto-del-servidor" not in respuesta.text
assert respuesta.json()["id_correlacion"]  # con esto se encuentra la traza
```

Dónde está: `_predecir_lote` en `main.py` (captura, `logger.exception`, `_error(500,
MSG_ERROR_INFERENCIA, id_correlacion=cid)`) y el handler global de `Exception`.

## 8. Criterio 7 — Cero pines a mano en el `Dockerfile`

```bash
grep -nE "pip install .*==" Dockerfile || echo "sin pines a mano  OK"
```

Salvedad honesta que hay que saber defender: el `Dockerfile` del repositorio **sí**
tiene dos `pip install` en la etapa `mlflow-server`, y no es una contradicción. Ahí se
instalan el driver de Postgres y el cliente S3 de un servicio de **infraestructura**,
que no toca el pickle del modelo; el anti-patrón era pinnear a mano las librerías que
**deserializan el artefacto**. La diferencia está escrita en el propio archivo, y se
usan *floor pins* (`>=`) en lugar de versiones exactas. La deuda se documenta en lugar
de esconderse: lo limpio a futuro es declararlos en un extra de `pyproject.toml`.

Si un estudiante encuentra esa aparente contradicción y la argumenta, súmale puntos:
es exactamente la lectura crítica que la sesión busca.

## 9. El ADR

Referencia: [`docs/adr/006-serving-online-vs-batch.md`](../../../docs/adr/006-serving-online-vs-batch.md).
Se evalúa que tenga las cuatro secciones y, sobre todo, que las **consecuencias**
estén en los dos sentidos. Un ADR que solo lista las ventajas de lo elegido no es un
ADR, es una justificación.

---

## Guion de revisión en 5 minutos por PR

En este orden, porque va de lo más barato de comprobar a lo más caro:

1. `grep -nE "pip install .*==" Dockerfile` y `grep -n "on_event\|@validator\|class Config" -r .`
2. `grep -rn "debug=True\|str(e)\|f\"{e}\"" .` (los tres anti-patrones que se penalizan)
3. `docker compose up -d --build` y `docker compose ps` → `(healthy)`
4. `docker compose exec api id -u` → distinto de 0
5. `curl -s .../health | jq .model_version` → no `null`
6. `uv run pytest -k api -q` con el registry apagado
7. La consulta SQL de trazabilidad
8. Leer el ADR: ¿las consecuencias están en los dos sentidos?

Los pasos 1, 2 y 6 detectan la mayoría de los problemas y no requieren levantar nada.
