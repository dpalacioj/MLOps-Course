# Clase Magistral: Servir Modelos en Tiempo Real y Subirlos a la Nube

> Módulo 04 — Deployment · Pasos 3 y 4
> Folders cubiertos: `web-service/` y `web-service-aws/`
> Este material **amplía** la `GUIA_VISUAL.md` del módulo. No la sustituye: la guía visual
> explica los conceptos macro; esta clase entra al código, a los patrones y a la realidad
> de producción detrás de cada archivo.
>
> **Sobre la parte AWS**: el Bloque 10 se dicta como walkthrough teórico, no como despliegue
> en vivo. El archivo `web-service-aws/GUIA_AWS_EC2.md` es la receta completa para quien
> quiera reproducir el despliegue por su cuenta después de clase.

---

## Mapa de la clase

| Bloque | De qué va |
|--------|-----------|
| 1 | Por qué este módulo existe y a dónde vamos |
| 2 | Anatomía de una API de ML con FastAPI |
| 3 | Pydantic: el contrato que protege a tu modelo |
| 4 | Cargar el modelo una sola vez (patrón singleton + lifespan) |
| 5 | Los 4 endpoints en acción |
| 6 | Docker a fondo: capas, caché y tamaño de imagen |
| 7 | Docker Compose: orquestar, reiniciar y monitorear |
| 8 | Frontend integrado + Postman |
| 9 | AWS EC2: el primer servidor de tu vida |
| 10 | Desplegar el contenedor paso a paso |
| 11 | ¿Por qué el folder de AWS usa Flask y no FastAPI? |
| 12 | Seguridad, costos y lo que falta para producción real |

---

## Bloque 1 · De qué estamos hablando

### Recap rápido

Ya vimos:

- **Docker** (paso 1): empaqueta cualquier app en una imagen reproducible.
- **Batch** (paso 2): corre el modelo por lotes cada X tiempo, guarda en BD, deja artefactos.

Hoy cerramos el módulo con los dos patrones que faltan:

- **Paso 3 — `web-service/`**: servir el modelo **en tiempo real** detrás de una API.
- **Paso 4 — `web-service-aws/`**: llevar ese servicio a **la nube** para que lo usen otros.

### La pregunta que guía todo el día

> *"Tengo un modelo entrenado. ¿Cómo hago que alguien, desde cualquier parte del mundo, me mande un dato y yo le devuelva la predicción en menos de un segundo?"*

Esa es la pregunta de ingeniería. La respuesta son dos capas:

| Capa | Herramienta en el folder |
|------|--------------------------|
| Código que recibe datos, valida, invoca al modelo y responde | **FastAPI + Uvicorn** |
| Empaque reproducible de ese código | **Docker + docker-compose** |
| Computadora pública donde vive ese contenedor | **AWS EC2** |

---

## Bloque 2 · Anatomía de una API de ML

### Las 5 cosas que hace toda API de ML

Todo servicio de predicción en tiempo real, **sin importar el framework o la nube**, hace exactamente estas cinco cosas:

1. **Escuchar** peticiones HTTP en un puerto.
2. **Validar** que los datos entren con el formato correcto.
3. **Transformar** los datos crudos en features (igual que en entrenamiento).
4. **Invocar** el modelo para obtener la predicción.
5. **Responder** un JSON con la predicción y metadatos.

Cualquier API que veas en producción (Databricks Model Serving, SageMaker Endpoints, Google Vertex AI, Azure ML) hace exactamente estas 5 cosas por dentro. Lo único que cambia es **quién** las implementa.

### Árbol del folder `web-service/`

```
web-service/
├── app.py                   ← Orquesta los endpoints
├── src/
│   ├── schemas.py           ← Contratos de entrada/salida (Pydantic)
│   └── model_loader.py      ← Carga y expone el modelo
├── templates/
│   └── index.html           ← UI web para probar sin código
├── model/                   ← Artefactos del modelo entrenado
│   ├── models_mlflow/
│   └── preprocessor/
├── copy_model.py            ← Trae el modelo desde batch-deploy/
├── Dockerfile               ← Empaqueta todo
├── docker-compose.yml       ← Arranca todo con un comando
└── README.md, GUIA_USO.md   ← Documentación
```

### Separación de responsabilidades

Fíjate en algo importante: el código está partido en **tres roles**, uno por archivo:

| Archivo | Rol | Analogía |
|---------|-----|----------|
| `app.py` | **Recepcionista**: recibe la petición, devuelve la respuesta | El cajero de un banco |
| `src/schemas.py` | **Guardia de seguridad**: valida que los datos sean legítimos | El portero de la discoteca |
| `src/model_loader.py` | **Especialista**: carga el modelo y ejecuta la predicción | El analista de riesgos del banco |

Este patrón es oro: cuando tu proyecto crezca, cada rol crece por separado.

### FastAPI + Uvicorn: revisita rápida

Ya lo introdujimos en la guía visual. Refresco rápido antes de ir al código:

- **Uvicorn** = el mesero (ASGI server). Escucha en el puerto, recibe HTTP, pasa la petición.
- **FastAPI** = el chef (framework). Decide qué hacer con cada petición.

Se lanzan juntos así:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
#        └─┬─┘
#    archivo.py : variable
```

### El código mínimo de `app.py`

```python
from fastapi import FastAPI, HTTPException
from src.schemas import TripRequest, PredictionResponse
from src.model_loader import model_loader

app = FastAPI(title="NYC Taxi Duration API", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    model_loader.load()              # ← carga el modelo UNA sola vez

@app.post("/predict", response_model=PredictionResponse)
async def predict(trip: TripRequest):
    feature = {
        "PU_DO": f"{trip.PULocationID}_{trip.DOLocationID}",
        "trip_distance": trip.trip_distance,
    }
    prediction = model_loader.predict([feature])[0]
    return PredictionResponse(
        PULocationID=trip.PULocationID,
        DOLocationID=trip.DOLocationID,
        trip_distance=trip.trip_distance,
        predicted_duration_minutes=round(prediction, 2),
        model_name=model_loader.metadata["model_name"],
        model_version=model_loader.metadata["version"],
    )
```

Aquí se ven los 4 ingredientes clave:

1. **Decoradores** (`@app.post`) → mapean URL a función.
2. **Tipado** (`trip: TripRequest`) → FastAPI valida automáticamente.
3. **`response_model`** → garantiza la forma de la salida.
4. **`@app.on_event("startup")`** → ciclo de vida de la app.

---

## Bloque 3 · Pydantic: el contrato de tu API

### ¿Qué problema resuelve?

Sin Pydantic, tu endpoint recibe un diccionario crudo:

```python
ride = request.get_json()       # puede ser cualquier cosa
pu_id = ride["PULocationID"]    # ¿qué pasa si no existe? 💥
```

Los bugs más caros en ML no son del modelo, son de **datos mal formateados** que llegan al modelo y rompen silenciosamente. Pydantic cierra esa puerta.

### El esquema de entrada

```python
from pydantic import BaseModel, Field, field_validator

class TripRequest(BaseModel):
    PULocationID: int = Field(..., ge=1, le=265)
    DOLocationID: int = Field(..., ge=1, le=265)
    trip_distance: float = Field(..., gt=0, le=100)

    @field_validator("trip_distance")
    @classmethod
    def validate_distance(cls, v):
        if v <= 0:
            raise ValueError("trip_distance debe ser mayor a 0")
        if v > 100:
            raise ValueError("trip_distance no puede exceder 100 millas")
        return v
```

### Anatomía línea a línea

| Elemento | Qué hace |
|----------|----------|
| `BaseModel` | Clase base que convierte la clase en un validador |
| `...` (Ellipsis) | "Este campo es obligatorio" |
| `ge=1, le=265` | Mayor o igual 1, menor o igual 265 (locaciones válidas de NYC) |
| `gt=0, le=100` | Mayor a 0, menor o igual 100 millas |
| `@field_validator` | Lógica custom además de los rangos |

### Qué pasa si el cliente manda algo inválido

Si un cliente envía `trip_distance: 150`, FastAPI devuelve automáticamente:

```json
HTTP 422 Unprocessable Entity
{
  "detail": [{
    "loc": ["body", "trip_distance"],
    "msg": "trip_distance no puede exceder 100 millas",
    "type": "value_error"
  }]
}
```

**Nunca llega al modelo.** Esto es lo que hace Pydantic oro puro para ML:

- Protege al modelo de inputs fuera de distribución.
- Devuelve errores entendibles al cliente.
- Documenta la API automáticamente.

### Los 5 esquemas del proyecto

| Esquema | Para qué |
|---------|----------|
| `TripRequest` | Un viaje individual en `/predict` |
| `BatchTripRequest` | Lista de viajes para `/predict/batch` (máx 1000) |
| `PredictionResponse` | Respuesta de un viaje |
| `BatchPredictionResponse` | Respuesta de un lote |
| `HealthResponse` | Estado del servicio y del modelo |

### El patrón clave: validar UNA SOLA VEZ

Pydantic valida en el **borde** de la API. Dentro del código, ya puedes trabajar con datos de confianza. Esto es análogo al principio de *"parse, don't validate"*: conviertes input crudo en un tipo rico, y de ahí en adelante el compilador (o tipador) te respalda.

---

## Bloque 4 · Cargar el modelo UNA sola vez

### El error del principiante

```python
@app.post("/predict")
async def predict(trip: TripRequest):
    model = mlflow.xgboost.load_model("model/models_mlflow")   # 💥
    prediction = model.predict(...)
```

¿Qué está mal? Estás cargando el modelo **en cada petición**. Con un modelo de 100 MB y 100 peticiones por segundo, acabas de quemar el servidor.

### El patrón correcto: singleton + lifespan

Dos ideas combinadas:

1. **Singleton**: una única instancia del cargador de modelo en memoria.
2. **Lifespan event**: aprovecha el arranque de la app para cargarlo una vez.

```python
# src/model_loader.py
class ModelLoader:
    def __init__(self):
        self.model = None
        self.preprocessor = None
        self.metadata = None

    def load(self):
        # Carga el MLmodel de XGBoost
        self.model = mlflow.xgboost.load_model("model/models_mlflow")
        # Carga el DictVectorizer entrenado
        with open("model/preprocessor/preprocessor.b", "rb") as f:
            self.preprocessor = pickle.load(f)
        # Carga metadata (versión, RMSE)
        with open("model/metadata.json") as f:
            self.metadata = json.load(f)

    def predict(self, features: list) -> list:
        X = self.preprocessor.transform(features)
        dmatrix = xgb.DMatrix(X)
        return self.model.predict(dmatrix).tolist()

    def is_loaded(self) -> bool:
        return self.model is not None and self.preprocessor is not None

model_loader = ModelLoader()     # ← instancia global
```

```python
# app.py
@app.on_event("startup")
async def startup_event():
    model_loader.load()          # ← una sola vez, al arrancar
```

### ¿Por qué tres artefactos y no uno solo?

| Artefacto | Qué es | Por qué separado |
|-----------|--------|------------------|
| `models_mlflow/` | El modelo XGBoost en formato MLflow | El *cerebro* que predice |
| `preprocessor.b` | El `DictVectorizer` de sklearn, pickle binario | Convierte `{"PU_DO": "161_236", ...}` en la matriz numérica que espera el modelo |
| `metadata.json` | JSON con `{model_name, version, rmse}` | Sirve health checks sin cargar el modelo |

**Consistencia train/serve**: el `DictVectorizer` que usas al servir **tiene que ser el mismo** que se usó en el entrenamiento. Si entrenaste con otro, la matriz de features tendrá columnas diferentes y el modelo fallará en silencio (o peor: predecirá mal sin error).

### Feature engineering al servir

El modelo no se entrenó con `PULocationID` y `DOLocationID` por separado. Se entrenó con `PU_DO` (un string combinado). Por eso, antes de llamar al modelo:

```python
feature = {"PU_DO": f"{trip.PULocationID}_{trip.DOLocationID}",
           "trip_distance": trip.trip_distance}
```

Regla de oro: **lo que transformaste en entrenamiento, lo tienes que transformar igual al servir**. Esta es la principal causa de bugs de ML en producción (*training-serving skew*).

---

## Bloque 5 · Los 4 endpoints en acción

### Tabla completa

| Endpoint | Método | Propósito | Error típico |
|----------|--------|-----------|--------------|
| `/` | GET | Servir la UI web (formulario) | - |
| `/health` | GET | ¿El servicio está vivo? ¿El modelo cargado? | `503` si el modelo no cargó |
| `/predict` | POST | Predecir un viaje | `422` si los datos son inválidos |
| `/predict/batch` | POST | Predecir hasta 1000 viajes | `422` si lista vacía o > 1000 |
| `/docs` | GET | Swagger UI (autogenerado) | - |
| `/redoc` | GET | Documentación alternativa | - |

### `/health` — el endpoint que nunca debe faltar

```python
@app.get("/health", response_model=HealthResponse)
async def health_check():
    if not model_loader.is_loaded():
        raise HTTPException(status_code=503, detail="Modelo no cargado")
    return HealthResponse(
        status="ok",
        model_loaded=True,
        model_name=model_loader.metadata["model_name"],
        model_version=model_loader.metadata["version"],
        model_rmse=model_loader.metadata["rmse"],
    )
```

**Por qué es crítico**: los orquestadores (Docker, Kubernetes, ECS) llaman a este endpoint cada X segundos. Si devuelve `503`, reinician el contenedor automáticamente. Sin health check, un contenedor con el modelo roto parece sano y sirve basura.

### `/predict` — una predicción

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"PULocationID": 161, "DOLocationID": 236, "trip_distance": 5.2}'
```

Respuesta:

```json
{
  "PULocationID": 161,
  "DOLocationID": 236,
  "trip_distance": 5.2,
  "predicted_duration_minutes": 18.45,
  "model_name": "xgboost-duration-predictor",
  "model_version": "1.0.0"
}
```

**Nota sobre `model_version`**: devolver esto en cada respuesta hace que los consumidores puedan loguear qué versión del modelo generó qué predicción. Esto es esencial para auditoría y para debugging cuando algo se rompe.

### `/predict/batch` — el endpoint eficiente

Llamar 100 veces a `/predict` = 100 viajes de ida y vuelta al servidor + 100 transformaciones + 100 invocaciones al modelo.

Llamar 1 vez a `/predict/batch` con 100 viajes = 1 viaje + 1 transformación + 1 invocación.

```python
@app.post("/predict/batch", response_model=BatchPredictionResponse)
async def predict_batch(batch: BatchTripRequest):
    features = [
        {"PU_DO": f"{t.PULocationID}_{t.DOLocationID}",
         "trip_distance": t.trip_distance}
        for t in batch.trips
    ]
    predictions = model_loader.predict(features)
    return BatchPredictionResponse(
        predictions=[
            PredictionResponse(..., predicted_duration_minutes=round(p, 2), ...)
            for t, p in zip(batch.trips, predictions)
        ],
        total=len(predictions),
        model_name=model_loader.metadata["model_name"],
        model_version=model_loader.metadata["version"],
    )
```

### `/docs` — la joya escondida de FastAPI

FastAPI genera automáticamente un Swagger UI en `http://localhost:8000/docs`:

- Lista todos los endpoints.
- Muestra el esquema de request y response.
- **Permite ejecutar la API desde el navegador**, sin Postman ni curl.

Esto es gratis. No hay que escribir nada para tenerlo. Es una de las razones por las que FastAPI ganó sobre Flask para APIs de ML.

---

## Bloque 6 · Docker a fondo

### El Dockerfile completo

```dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn[standard]==0.32.0 \
    pydantic==2.9.2 \
    mlflow==2.17.2 \
    xgboost==2.1.2 \
    scikit-learn==1.5.2

COPY app.py ./
COPY src/ ./src/
COPY templates/ ./templates/
COPY model/ ./model/

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### El principio #1: una capa por cada **frecuencia de cambio**

Docker cachea cada `COPY` y cada `RUN` como una capa. Si una capa cambia, **todas las capas siguientes se reconstruyen**. Por eso el orden importa:

```
Capa 1: FROM python:3.11-slim               ← casi nunca cambia
Capa 2: COPY pyproject.toml                 ← cambia cuando cambias deps
Capa 3: RUN pip install ...                 ← cambia con la anterior
Capa 4: COPY app.py src/ templates/         ← cambia con cada commit
Capa 5: COPY model/                         ← cambia cada retraining
```

Si mañana cambias una línea en `app.py`, Docker **solo reconstruye desde la capa 4**. Las 3 primeras (que incluyen instalar dependencias, que toma minutos) vienen del caché.

### Versiones pinneadas: reproducibilidad pura

```
fastapi==0.115.0    ✅
fastapi             ❌  ← instala lo más nuevo, que podría romper tu código
fastapi>=0.110      ⚠️  ← aceptable, pero futuros breaking changes posibles
```

Regla: en producción **siempre pinnea**. Lo que aprendiste hoy funciona mañana.

### Por qué `python:3.11-slim` y no `python:3.11`

| Imagen | Tamaño aproximado |
|--------|-------------------|
| `python:3.11` | ~1 GB |
| `python:3.11-slim` | ~150 MB |
| `python:3.11-alpine` | ~50 MB (pero rompe muchas libs de ML) |

Para ML, `slim` es el sweet spot: chica, pero compatible con XGBoost, scikit-learn, numpy.

### `.dockerignore`: qué NO meter en la imagen

```
__pycache__/
*.pyc
.venv/
.git/
.vscode/
README.md
tests/
```

Todo lo que no sea necesario en runtime se queda fuera. Imagen más pequeña = despliegue más rápido + menor superficie de ataque.

### El comando que ejecuta todo

```dockerfile
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`0.0.0.0` es obligatorio en contenedores.** Si pones `127.0.0.1`, la app solo escucha dentro del contenedor y desde fuera no se puede conectar. Es el error #1 de principiantes con Docker.

---

## Bloque 7 · Docker Compose y healthchecks

### El archivo completo

```yaml
version: '3.8'
services:
  taxi-api:
    build: .
    container_name: nyc-taxi-api
    ports:
      - "8000:8000"
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Por qué Compose y no `docker run`

| `docker run` | `docker-compose up` |
|---|---|
| Un comando largo con banderas | Archivo versionado en git |
| Cada vez lo escribes/recuerdas | Un comando: `docker-compose up` |
| Difícil agregar más servicios (DB, Redis...) | Agregas otra sección y listo |
| No hay policy de reinicio explícita | `restart: unless-stopped` built-in |

### `PYTHONUNBUFFERED=1`: un clásico de Docker + Python

Python bufferiza stdout por defecto. Dentro de un contenedor, eso significa que los `print()` y los `logging` no aparecen hasta que el buffer se llena o la app muere. En producción eso es una pesadilla (debugging a ciegas).

`PYTHONUNBUFFERED=1` apaga el buffer: los logs aparecen **al instante**.

### Restart policies

| Policy | Cuándo reinicia |
|--------|-----------------|
| `no` | Nunca (default) |
| `always` | Siempre, incluso si lo detienes a mano |
| `on-failure` | Solo si crashea con exit code != 0 |
| `unless-stopped` | Siempre, excepto si lo detienes explícitamente |

Para un servicio 24/7 la mejor es `unless-stopped`: resiliente pero respeta tu decisión manual.

### Healthcheck: el sistema nervioso del contenedor

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s          # frecuencia de chequeo
  timeout: 10s           # cuánto esperar la respuesta
  retries: 3             # cuántos fallos seguidos = unhealthy
  start_period: 40s      # "luna de miel" antes del primer check
```

Cuando corres `docker ps`, ves el estado:

```
CONTAINER ID   IMAGE         STATUS                      PORTS
abc123         taxi-api      Up 2 minutes (healthy)      0.0.0.0:8000->8000/tcp
```

En Kubernetes esto se transforma en `livenessProbe` y `readinessProbe`, con la misma idea.

---

## Bloque 8 · Frontend y Postman

### El `/` sirve un HTML

```python
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
```

FastAPI + Jinja2 = puedes servir páginas HTML sin Node, sin React, sin build step. Para demos o MVPs es perfecto.

El `templates/index.html` es un formulario que, al enviar, llama a `/predict` vía `fetch()` y muestra el resultado. 273 líneas de HTML+CSS+JS vanilla, sin framework.

### ¿Por qué importa tener UI?

- Te permite hacer demos sin abrir Postman.
- Los stakeholders no técnicos pueden probar el modelo.
- Es una prueba end-to-end visible.

### Postman: cURL con esteroides

El folder incluye dos archivos `.json` de Postman:

| Archivo | Qué contiene |
|---------|--------------|
| `NYC_Taxi_API.postman_collection.json` | 8 requests preconfigurados |
| `NYC_Taxi_API.postman_environment.json` | Variables como `{{base_url}}` |

Con las **environments**, un mismo set de requests apunta a local, staging o producción cambiando un menú:

```
Development:  base_url = http://localhost:8000
Staging:      base_url = http://staging.api.mycompany.com
Production:   base_url = https://api.mycompany.com
```

### cURL vs Postman: cuándo cada uno

| Usa cURL cuando... | Usa Postman cuando... |
|---|---|
| Estás dentro de un servidor por SSH | Exploras una API nueva |
| Automatizas en un script | Compartes requests con tu equipo |
| Documentas algo en un README | Pruebas distintos ambientes |
| Estás en un CI/CD pipeline | Guardas histórico visual |

---

## Bloque 9 · AWS EC2 — el primer servidor de tu vida

### Qué es EC2 en una frase

> **Una laptop rentada, prendida 24/7, con una IP pública, donde tú decides qué instalar.**

### Vocabulario de AWS que vas a oír hoy

| Término | Significado |
|---------|-------------|
| **Instancia** | La máquina virtual en sí |
| **AMI** (Amazon Machine Image) | La "plantilla" del sistema operativo (Ubuntu, Amazon Linux, etc.) |
| **Tipo de instancia** | El tamaño (t2.micro, t3.medium, m5.large...) → RAM, CPU, red |
| **Región** | Dónde está físicamente la máquina (us-east-1, eu-west-1...) |
| **Key pair** | Archivo `.pem` con tu llave privada SSH |
| **Security Group** | Firewall virtual: qué puertos están abiertos y desde dónde |
| **Public DNS** | Dirección pública tipo `ec2-12-34-56-78.compute-1.amazonaws.com` |
| **Elastic IP** | IP pública fija (si la instancia se apaga, la mantienes) |
| **IAM Role** | Permisos que la instancia tiene sobre otros servicios de AWS |

### La analogía: el apartamento rentado

Imagina que rentaste un estudio vacío:

| En el apartamento | En EC2 |
|-------------------|--------|
| La llave del apartamento | El archivo `.pem` |
| El número de la puerta | El Public DNS |
| El portero que decide quién entra | El Security Group |
| Cambiar la chapa por una más segura | `chmod 400 tu-clave.pem` |
| Amueblar el estudio | Instalar Docker y correr el contenedor |

### Los 6 pasos de despliegue (vista aérea)

```
1. Conectarte por SSH             →   ssh -i key.pem ec2-user@<dns>
2. Instalar Docker                 →   sudo yum install -y docker
3. Clonar el repo                  →   git clone <url>
4. Construir la imagen             →   docker build -t taxi-prediction .
5. Correr el contenedor            →   docker run -d -p 9696:9696 ...
6. Abrir el puerto en Security Group  (consola AWS)
```

Si te fijas: los pasos 4 y 5 son **idénticos** a lo que hacías en tu laptop. EC2 no cambia cómo funciona Docker. Solo cambia **dónde** corre.

---

## Bloque 10 · Desplegar paso a paso

### Paso 1 · Conectarte por SSH

```bash
chmod 400 tu-clave.pem                                         # ① permisos estrictos
ssh -i tu-clave.pem ec2-user@ec2-12-34-56-78.compute-1.amazonaws.com
```

**Por qué `chmod 400`**: SSH **rechaza** claves que cualquier otro usuario pueda leer. `400` = lectura solo para el dueño. Si pones `644`, SSH te dice "WARNING: UNPROTECTED PRIVATE KEY FILE!" y no conecta.

### Paso 2 · Instalar Docker

```bash
sudo yum update -y
sudo yum install -y docker git
sudo service docker start
sudo usermod -a -G docker ec2-user     # ← evita tener que escribir sudo cada vez
exit                                    # ← y reconectarte para que tome efecto
```

**Por qué `exit` y reconectar**: los grupos de Linux solo se actualizan al loguearse. Si no sales y vuelves a entrar, `docker ps` te pide sudo.

### Paso 3 · Clonar y construir

```bash
git clone https://github.com/tu-usuario/tu-repositorio.git
cd tu-repositorio/04-Deployment/deploy/web-service-aws
docker build -t taxi-prediction .
```

En una instancia `t2.micro` (1 GB RAM), el build puede tardar 3-5 minutos. Es normal.

### Paso 4 · Correr el contenedor

```bash
docker run -d -p 9696:9696 --name taxi-service taxi-prediction
docker ps                              # verificar que esté "Up"
docker logs -f taxi-service            # ver logs (Ctrl+C para salir)
```

| Flag | Qué hace |
|------|----------|
| `-d` | Detached: corre en background |
| `-p 9696:9696` | Puerto del host : puerto del contenedor |
| `--name taxi-service` | Nombre amigable para referenciarlo |

### Paso 5 · Abrir el puerto en el Security Group

Aquí está la trampa. Puedes tener el contenedor perfecto corriendo, pero si el Security Group no deja pasar tráfico al puerto 9696, **nadie llega**.

En la consola de AWS:

1. EC2 → tu instancia → pestaña **Security**
2. Clic en el Security Group
3. Edit inbound rules → Add rule:
   - Type: **Custom TCP**
   - Port range: **9696**
   - Source: **0.0.0.0/0** (cualquier IP) o **My IP** (solo tú)
   - Description: "Taxi Prediction API"
4. Save

### Paso 6 · Probar desde tu máquina

```bash
curl -X POST http://ec2-12-34-56-78.compute-1.amazonaws.com:9696/predict \
  -H "Content-Type: application/json" \
  -d '{"PULocationID": 161, "DOLocationID": 236, "trip_distance": 2.5}'
```

Respuesta esperada:

```json
{"duration": 12.34}
```

### Comandos de bolsillo

```bash
docker ps                           # ¿qué está corriendo?
docker logs -f taxi-service         # ver logs en vivo
docker stop taxi-service            # parar
docker start taxi-service           # prender
docker rm taxi-service              # eliminar (debe estar parado)
sudo netstat -tulpn | grep 9696     # ¿el puerto está escuchando?
df -h                               # ¿queda espacio en disco?
```

---

## Bloque 11 · ¿Por qué el folder AWS usa Flask y no FastAPI?

### La sorpresa

Si abres `web-service-aws/predict.py`, vas a encontrar **Flask**, no FastAPI:

```python
from flask import Flask, request, jsonify
import pickle

with open("lin_reg.bin", "rb") as f_in:
    (dv, model) = pickle.load(f_in)

app = Flask("duration-prediction")

@app.route("/predict", methods=["POST"])
def predict_endpoint():
    ride = request.get_json()
    features = {
        "PU_DO": f"{ride['PULocationID']}_{ride['DOLocationID']}",
        "trip_distance": ride["trip_distance"],
    }
    X = dv.transform(features)
    pred = float(model.predict(X)[0])
    return jsonify({"duration": pred})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=9696)
```

### La razón pedagógica

| `web-service/` (FastAPI) | `web-service-aws/` (Flask) |
|---|---|
| Patrón de producción | Patrón de estudiante |
| 200+ líneas en varios archivos | 15 líneas en un solo archivo |
| Pydantic, healthchecks, UI, Swagger | Solo `/predict` |
| Dependencies: 7 librerías | Dependencies: 3 librerías |
| Imagen Docker: ~800 MB | Imagen Docker: ~300 MB |
| MLflow para cargar el modelo | `pickle.load()` directo |
| Uvicorn (ASGI) | gunicorn (WSGI) |

**El punto:** al aprender a desplegar por primera vez en AWS, el cerebro no puede procesar EC2 + SSH + Security Groups + Docker + FastAPI todo a la vez. El folder AWS reduce el código a lo mínimo para que el foco sea la nube, no el framework.

### gunicorn vs uvicorn (rapidísimo)

| | gunicorn | uvicorn |
|---|---|---|
| Protocolo | WSGI (síncrono) | ASGI (asíncrono) |
| Va con | Flask, Django | FastAPI, Starlette |
| En `web-service-aws/` | Sí (en el Dockerfile) | No |
| En `web-service/` | No | Sí |

Detalle importante: en `predict.py` ves `app.run(debug=True, ...)`. **Eso solo corre si ejecutas `python predict.py` localmente**. En el contenedor, el `ENTRYPOINT` del Dockerfile usa `gunicorn`, que nunca activa `debug=True`. Esto es intencional: nunca corras Flask con `debug=True` en producción (expone un debugger accesible por web).

### El artefacto del modelo: `lin_reg.bin`

Un pickle con una **tupla de dos objetos**:

```python
(dv, model) = pickle.load(f_in)
#  ↑     ↑
#  |     └── sklearn.linear_model.LinearRegression
#  └─────── sklearn.feature_extraction.DictVectorizer
```

Es el patrón más simple posible: todo el pipeline de preprocesamiento + modelo empaquetado en un solo archivo. Funciona para MVPs pero no escala: si quieres actualizar solo el preprocesamiento, tienes que reempaquetar todo.

`web-service/` ya usa el patrón maduro: MLflow + artefactos separados.

---

## Bloque 12 · Seguridad, costos y lo que falta para producción

### Lo que el tutorial hace bien

- `chmod 400` en la llave SSH.
- Security Group cerrado por defecto (solo abres lo que necesitas).
- Usuario `ec2-user` (no root).
- Modelo pinneado dentro de la imagen Docker.

### Lo que **no** hace (y en producción sí debería)

| Riesgo | Qué pasa si lo ignoras | Cómo se mitiga en real |
|---|---|---|
| `Source: 0.0.0.0/0` en el SG | Cualquier persona en internet puede hamacartear tu API | Restringir a IPs específicas, o poner un API Gateway delante |
| Sin HTTPS | Las peticiones viajan en texto plano | Nginx + Let's Encrypt, o un ALB de AWS con certificado ACM |
| Sin autenticación | El endpoint es público | API key, JWT, o AWS Cognito |
| Sin rate limiting | Un cliente puede mandar 10,000 req/s | Nginx con `limit_req_zone`, o API Gateway |
| Sin monitoreo | No te enteras si el contenedor crashea a las 3 AM | CloudWatch Logs + Alarms |
| Sin backups de la llave `.pem` | Si la pierdes, no puedes entrar a la instancia | Guarda la clave cifrada en un gestor de contraseñas |
| Sin billing alerts | Puedes gastar cientos de dólares por error | Budget alerts en AWS Billing |

### Costos en el free tier (primer año)

| Recurso | Gratis | Excedente |
|---------|--------|-----------|
| EC2 `t2.micro` | 750 h/mes | ~$0.014/h |
| EBS (disco) | 30 GB | ~$0.10/GB/mes |
| Transferencia saliente | 100 GB/mes | ~$0.09/GB |

750 h/mes alcanza para **una instancia prendida 24/7** (24×30=720 h). Si prendes dos, ya te pasaste.

### El error más caro de principiantes

> Dejar una instancia prendida y olvidarse de ella.

Formas de evitarlo:

1. **Budget alert** en AWS Billing ($5/mes, por ejemplo).
2. Tarea en tu calendario: "¿Apagué mi instancia EC2?"
3. `t2.micro` stop cuando no la uses (no pagas cómputo, solo el disco).

### Mapeo a servicios reales de MLOps

Para que no se queden con la idea de "esto es solo un ejercicio":

| Lo que vieron hoy | En una empresa real |
|---|---|
| FastAPI + Docker + EC2 | **SageMaker Endpoints**, **Databricks Model Serving**, **Vertex AI Endpoints**, **Azure ML Online Endpoints** |
| `/health` endpoint | Liveness/readiness probes en Kubernetes |
| `docker build` manual en la instancia | **GitHub Actions** → **ECR** → **deploy automático** |
| Security Group 0.0.0.0/0 | **AWS WAF** + **API Gateway** + **Cognito** |
| Logs en stdout | **CloudWatch**, **Datadog**, **Grafana Loki** |
| Sin versionamiento de modelos | **MLflow Model Registry**, **SageMaker Model Registry** |
| Sin A/B testing | Shadow deployments, traffic splitting |
| Sin feature store | **Feast**, **Tecton**, **Databricks Feature Store** |

**El concepto que quiero que se lleven:** SageMaker Endpoints por dentro **hace exactamente lo mismo que hicimos hoy**. Tiene un Uvicorn/gunicorn escuchando, un health check, un `/invocations` equivalente a `/predict`, y un modelo cargado en memoria. Lo que cambia es quién mantiene la infraestructura.

---

## Cierre

### Los 5 conceptos no negociables

1. **Validar en el borde**: Pydantic protege al modelo de datos inválidos.
2. **Cargar una vez**: el modelo vive en memoria, no lo cargues por petición.
3. **Health check siempre**: sin él, tu orquestador no sabe si estás vivo.
4. **Docker = reproducibilidad**: lo que corre en tu laptop corre igual en EC2.
5. **Security Group es un firewall**: el contenedor puede estar perfecto y el mundo no lo ve.

### El hilo conductor del módulo completo

```
Paso 1: Docker → "Ya sé empaquetar una app"
Paso 2: Batch  → "Ya sé el ciclo de vida de un modelo en producción"
Paso 3: API    → "Ya sé servir predicciones en tiempo real"
Paso 4: AWS    → "Ya sé poner eso en internet"
```

De aquí salen a SageMaker, a Databricks, a Vertex AI: no como usuarios que rezan para que funcione, sino sabiendo **qué hay detrás** de cada botón.

---

## Glosario adicional (complemento al de GUIA_VISUAL)

| Término | Explicación |
|---------|-------------|
| **Pydantic** | Librería que valida datos usando anotaciones de tipo de Python |
| **Singleton** | Patrón donde existe una sola instancia de una clase en toda la app |
| **Lifespan event** | Hook que se ejecuta al arrancar/apagar una app FastAPI |
| **ASGI** | Estándar asíncrono para servidores web Python (usado por FastAPI) |
| **WSGI** | Estándar síncrono anterior (usado por Flask, Django) |
| **Uvicorn** | Servidor ASGI, equivalente moderno de gunicorn |
| **gunicorn** | Servidor WSGI tradicional, muy usado en Flask/Django |
| **DictVectorizer** | Preprocesador de sklearn que convierte dicts en matrices numéricas |
| **DMatrix** | Formato interno optimizado de XGBoost para datos de entrada |
| **Health check** | Endpoint o comando que reporta si el servicio está vivo y sano |
| **Security Group** | Firewall de AWS a nivel de instancia EC2 |
| **AMI** | Plantilla de sistema operativo para crear instancias EC2 |
| **Elastic IP** | IP pública fija que no cambia aunque la instancia se apague |
| **ECR** | Elastic Container Registry: el "Docker Hub" privado de AWS |
| **IAM Role** | Permisos que tiene una instancia EC2 sobre otros servicios de AWS |
| **CloudWatch** | Servicio de logs, métricas y alarmas de AWS |
| **training-serving skew** | Diferencia entre el preprocesamiento en entrenamiento y el de serving |
