# Guía Completa - API de Predicción de Duración de Viajes

## 📋 Tabla de Contenidos
1. [Levantar la API](#levantar-la-api)
2. [Endpoints Disponibles](#endpoints-disponibles)
3. [¿Qué son cURL y Postman?](#-qué-son-curl-y-postman)
4. [Ejemplos con cURL](#ejemplos-con-curl)
5. [Ejemplos con Postman](#ejemplos-con-postman)
6. [cURL vs. Postman: ¿Cuándo usar cada uno?](#-curl-vs-postman-cuándo-usar-cada-uno)
7. [Códigos de Respuesta](#códigos-de-respuesta)

---

## Levantar la API

### **Paso 1: Copiar el Modelo**

```bash
cd /MLOps_UdM/04-Deployment/deploy/web-service

# Copiar modelo desde batch-deploy
uv run python copy_model.py
```

**Salida esperada:**
```
INFO: Copiando modelo de batch-deploy a web-service...
INFO: Modelo: nyc-taxi-duration-predictor v1
INFO: RMSE: 7.3977
INFO: Modelo copiado exitosamente
```

### **Paso 2: Iniciar el Servidor**

```bash
# Iniciar API en modo desarrollo (con auto-reload)
uv run uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Salida esperada:**
```
INFO: Uvicorn running on http://0.0.0.0:8000
INFO: Iniciando API...
INFO: Modelo: nyc-taxi-duration-predictor v1
INFO: API lista para recibir requests
INFO: Application startup complete.
```

### **Paso 3: Verificar que Funciona**

Abre tu navegador en: **http://localhost:8000**

Deberías ver:
```json
{
  "message": "NYC Taxi Duration Prediction API",
  "version": "1.0.0",
  "endpoints": {
    "health": "/health",
    "predict": "/predict",
    "predict_batch": "/predict/batch",
    "docs": "/docs"
  }
}
```

---

## Endpoints Disponibles

### **1. GET /** - Información de la API
**Propósito:** Verificar que la API está corriendo y ver endpoints disponibles

**URL:** `http://localhost:8000/`

**Respuesta:**
```json
{
  "message": "NYC Taxi Duration Prediction API",
  "version": "1.0.0",
  "endpoints": {
    "health": "/health",
    "predict": "/predict",
    "predict_batch": "/predict/batch",
    "docs": "/docs"
  }
}
```

---

### **2. GET /health** - Health Check
**Propósito:** Verificar que el modelo está cargado y la API está saludable

**URL:** `http://localhost:8000/health`

**Respuesta:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_name": "nyc-taxi-duration-predictor",
  "model_version": "1",
  "model_rmse": 7.3977
}
```

**Códigos de respuesta:**
- `200 OK` - API saludable
- `503 Service Unavailable` - Modelo no cargado o error

---

### **3. POST /predict** - Predicción Individual
**Propósito:** Predecir la duración de UN viaje de taxi

**URL:** `http://localhost:8000/predict`

**Request Body:**
```json
{
  "PULocationID": 161,
  "DOLocationID": 236,
  "trip_distance": 5.2
}
```

**Parámetros:**
- `PULocationID` (int): Zona de recogida (1-265)
- `DOLocationID` (int): Zona de destino (1-265)
- `trip_distance` (float): Distancia en millas (0-100)

**Respuesta:**
```json
{
  "PULocationID": 161,
  "DOLocationID": 236,
  "trip_distance": 5.2,
  "predicted_duration_minutes": 18.45,
  "model_name": "nyc-taxi-duration-predictor",
  "model_version": "1"
}
```

**Códigos de respuesta:**
- `200 OK` - Predicción exitosa
- `422 Unprocessable Entity` - Error de validación
- `500 Internal Server Error` - Error en predicción

---

### **4. POST /predict/batch** - Predicción Batch
**Propósito:** Predecir la duración de MÚLTIPLES viajes (hasta 1000)

**URL:** `http://localhost:8000/predict/batch`

**Request Body:**
```json
{
  "trips": [
    {
      "PULocationID": 161,
      "DOLocationID": 236,
      "trip_distance": 5.2
    },
    {
      "PULocationID": 237,
      "DOLocationID": 238,
      "trip_distance": 3.8
    },
    {
      "PULocationID": 239,
      "DOLocationID": 161,
      "trip_distance": 7.1
    }
  ]
}
```

**Respuesta:**
```json
{
  "predictions": [
    {
      "PULocationID": 161,
      "DOLocationID": 236,
      "trip_distance": 5.2,
      "predicted_duration_minutes": 18.45,
      "model_name": "nyc-taxi-duration-predictor",
      "model_version": "1"
    },
    {
      "PULocationID": 237,
      "DOLocationID": 238,
      "trip_distance": 3.8,
      "predicted_duration_minutes": 14.23,
      "model_name": "nyc-taxi-duration-predictor",
      "model_version": "1"
    },
    {
      "PULocationID": 239,
      "DOLocationID": 161,
      "trip_distance": 7.1,
      "predicted_duration_minutes": 22.67,
      "model_name": "nyc-taxi-duration-predictor",
      "model_version": "1"
    }
  ],
  "total": 3,
  "model_name": "nyc-taxi-duration-predictor",
  "model_version": "1"
}
```

---

### **5. GET /docs** - Documentación Swagger UI
**Propósito:** Interfaz interactiva para probar la API

**URL:** `http://localhost:8000/docs`

Permite:
- Ver todos los endpoints
- Probar requests directamente desde el navegador
- Ver esquemas de datos
- Descargar especificación OpenAPI

---

### **6. GET /redoc** - Documentación ReDoc
**Propósito:** Documentación alternativa más limpia

**URL:** `http://localhost:8000/redoc`

---

## 🧠 ¿Qué son cURL y Postman?

Antes de ver los ejemplos, entendamos las dos herramientas que usaremos para "hablar" con la API.

### 📞 La analogía del teléfono

Imagina que tu **API** es una **pizzería** que recibe pedidos por teléfono. Para hacer un pedido necesitas:

1. Marcar el número correcto → **URL** (`http://localhost:8000/predict`)
2. Decir qué quieres → **Body** del request (los datos)
3. Hablar el mismo idioma → **Headers** (`Content-Type: application/json`)
4. Usar el tipo de llamada correcto → **Método** (GET para consultar, POST para pedir)

**cURL y Postman son dos formas distintas de hacer esa llamada telefónica. Hacen lo MISMO, pero con interfaces diferentes.**

---

### 🔧 ¿Qué es cURL?

**cURL** (Client URL) es una herramienta de línea de comandos que existe desde 1997. Viene **preinstalada** en Mac, Linux y Windows (10+). No necesitas descargarla.

**Analogía**: cURL es como un **teléfono fijo viejo**. Funciona perfecto, es confiable, pero tienes que marcar número por número manualmente.

```bash
curl http://localhost:8000/health
```

Ese es el comando más simple que puedes hacer con curl. Le dice: "tráeme lo que hay en esa URL".

### Anatomía de un comando cURL

Veamos un comando más complejo y entendamos cada parte:

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"PULocationID": 161, "DOLocationID": 236, "trip_distance": 5.2}'
```

| Parte | Qué significa | Analogía |
|-------|--------------|----------|
| `curl` | El programa | "Hacer una llamada" |
| `-X POST` | Método HTTP (GET, POST, PUT, DELETE) | "Tipo de operación" |
| `http://...` | URL del endpoint | "Número de teléfono" |
| `-H "..."` | Header (formato del mensaje) | "Hablamos en JSON" |
| `-d '{...}'` | Body (los datos que envías) | "Mi pedido" |
| `\` | Continuar en la siguiente línea | Solo para legibilidad |

### Flags comunes de cURL

| Flag | Para qué sirve | Ejemplo |
|------|----------------|---------|
| `-X` | Método HTTP | `-X POST` |
| `-H` | Agregar header | `-H "Content-Type: application/json"` |
| `-d` | Enviar datos (body) | `-d '{"key": "value"}'` |
| `-o` | Guardar respuesta en archivo | `-o result.json` |
| `-s` | Modo silencioso (sin barra de progreso) | `curl -s ...` |
| `-v` | Modo verbose (ver todo el detalle) | Útil para debugging |
| `-w` | Formato de salida personalizado | `-w "%{http_code}"` |
| `@archivo` | Leer body desde archivo | `-d @datos.json` |

---

### 📮 ¿Qué es Postman?

**Postman** es una aplicación gráfica (GUI) para hacer requests HTTP. Se descarga de [postman.com](https://www.postman.com/downloads/).

**Analogía**: Postman es como un **smartphone moderno**. Tienes agenda de contactos, historial de llamadas, puedes guardar conversaciones, y compartirlas con tu equipo.

### Qué ofrece Postman que cURL no (fácilmente)

| Feature | cURL | Postman |
|---------|------|---------|
| **Historial** de requests | ❌ (hay que guardar manualmente) | ✅ Automático |
| **Colecciones** (agrupar requests) | ❌ | ✅ |
| **Variables de entorno** (dev/prod) | ⚠️ Con scripts | ✅ Nativo |
| **Compartir con el equipo** | ❌ | ✅ Workspaces |
| **Tests automatizados** | ⚠️ Con bash | ✅ Con JavaScript |
| **Visualización de respuestas** | Texto plano | ✅ JSON formateado, tablas, gráficos |
| **Autocompletado** | ❌ | ✅ |
| **Curva de aprendizaje** | Media-alta | Baja |

---

### 🤝 La Relación entre cURL y Postman

**Son equivalentes**. De hecho:

- En **Postman** puedes hacer click derecho → "Copy as cURL" y obtienes el comando cURL listo.
- En cualquier **documentación de API** (Stripe, Twilio, OpenAI, etc.) verás ejemplos en cURL porque es el **lenguaje universal**.
- Postman **internamente** hace lo mismo que cURL: manda un request HTTP.

```
                    ┌─────────────────┐
                    │   Tu API        │
                    │ localhost:8000  │
                    └────────▲────────┘
                             │ HTTP
              ┌──────────────┼──────────────┐
              │              │              │
         ┌────┴────┐   ┌─────┴─────┐   ┌────┴─────┐
         │  cURL   │   │  Postman  │   │ Python   │
         │  (CLI)  │   │   (GUI)   │   │ requests │
         └─────────┘   └───────────┘   └──────────┘
              
         ← Diferentes herramientas, mismo protocolo HTTP →
```

---



```bash
curl http://localhost:8000/health
```

**Respuesta:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_name": "nyc-taxi-duration-predictor",
  "model_version": "1",
  "model_rmse": 7.3977
}
```

---

### **2. Predicción Individual**

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "PULocationID": 161,
    "DOLocationID": 236,
    "trip_distance": 5.2
  }'
```

**Respuesta:**
```json
{
  "PULocationID": 161,
  "DOLocationID": 236,
  "trip_distance": 5.2,
  "predicted_duration_minutes": 18.45,
  "model_name": "nyc-taxi-duration-predictor",
  "model_version": "1"
}
```

---

### **3. Predicción Batch (3 viajes)**

```bash
curl -X POST http://localhost:8000/predict/batch \
  -H "Content-Type: application/json" \
  -d '{
    "trips": [
      {
        "PULocationID": 161,
        "DOLocationID": 236,
        "trip_distance": 5.2
      },
      {
        "PULocationID": 237,
        "DOLocationID": 238,
        "trip_distance": 3.8
      },
      {
        "PULocationID": 239,
        "DOLocationID": 161,
        "trip_distance": 7.1
      }
    ]
  }'
```

---

### **4. Guardar Respuesta en Archivo**

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "PULocationID": 161,
    "DOLocationID": 236,
    "trip_distance": 5.2
  }' \
  -o prediction_result.json
```

---

### **5. Ver Solo el Código de Estado**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
```

**Respuesta:** `200`

---

## 📮 Ejemplos con Postman

### **Configuración Inicial**

1. **Abrir Postman**
2. **Crear nueva Collection**: "NYC Taxi API"
3. **Configurar Base URL**: `http://localhost:8000`

---

### **Request 1: Health Check**

**Método:** `GET`  
**URL:** `http://localhost:8000/health`  
**Headers:** Ninguno necesario

**Steps en Postman:**
1. Click en "New Request"
2. Nombre: "Health Check"
3. Método: GET
4. URL: `http://localhost:8000/health`
5. Click "Send"

**Respuesta esperada:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_name": "nyc-taxi-duration-predictor",
  "model_version": "1",
  "model_rmse": 7.3977
}
```

---

### **Request 2: Predicción Individual**

**Método:** `POST`  
**URL:** `http://localhost:8000/predict`  
**Headers:**
- `Content-Type: application/json`

**Body (raw JSON):**
```json
{
  "PULocationID": 161,
  "DOLocationID": 236,
  "trip_distance": 5.2
}
```

**Steps en Postman:**
1. Click en "New Request"
2. Nombre: "Predict Single Trip"
3. Método: POST
4. URL: `http://localhost:8000/predict`
5. Tab "Headers":
   - Key: `Content-Type`
   - Value: `application/json`
6. Tab "Body":
   - Seleccionar "raw"
   - Seleccionar "JSON" del dropdown
   - Pegar el JSON
7. Click "Send"

**Respuesta esperada:**
```json
{
  "PULocationID": 161,
  "DOLocationID": 236,
  "trip_distance": 5.2,
  "predicted_duration_minutes": 18.45,
  "model_name": "nyc-taxi-duration-predictor",
  "model_version": "1"
}
```

---

### **Request 3: Predicción Batch**

**Método:** `POST`  
**URL:** `http://localhost:8000/predict/batch`  
**Headers:**
- `Content-Type: application/json`

**Body (raw JSON):**
```json
{
  "trips": [
    {
      "PULocationID": 161,
      "DOLocationID": 236,
      "trip_distance": 5.2
    },
    {
      "PULocationID": 237,
      "DOLocationID": 238,
      "trip_distance": 3.8
    },
    {
      "PULocationID": 239,
      "DOLocationID": 161,
      "trip_distance": 7.1
    }
  ]
}
```

**Steps en Postman:**
1. Click en "New Request"
2. Nombre: "Predict Batch Trips"
3. Método: POST
4. URL: `http://localhost:8000/predict/batch`
5. Tab "Headers":
   - Key: `Content-Type`
   - Value: `application/json`
6. Tab "Body":
   - Seleccionar "raw"
   - Seleccionar "JSON"
   - Pegar el JSON
7. Click "Send"

---

### **Postman Collection (Importar)**

Puedes crear un archivo `NYC_Taxi_API.postman_collection.json`:

```json
{
  "info": {
    "name": "NYC Taxi Duration API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Health Check",
      "request": {
        "method": "GET",
        "header": [],
        "url": {
          "raw": "http://localhost:8000/health",
          "protocol": "http",
          "host": ["localhost"],
          "port": "8000",
          "path": ["health"]
        }
      }
    },
    {
      "name": "Predict Single Trip",
      "request": {
        "method": "POST",
        "header": [
          {
            "key": "Content-Type",
            "value": "application/json"
          }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"PULocationID\": 161,\n  \"DOLocationID\": 236,\n  \"trip_distance\": 5.2\n}"
        },
        "url": {
          "raw": "http://localhost:8000/predict",
          "protocol": "http",
          "host": ["localhost"],
          "port": "8000",
          "path": ["predict"]
        }
      }
    },
    {
      "name": "Predict Batch Trips",
      "request": {
        "method": "POST",
        "header": [
          {
            "key": "Content-Type",
            "value": "application/json"
          }
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"trips\": [\n    {\n      \"PULocationID\": 161,\n      \"DOLocationID\": 236,\n      \"trip_distance\": 5.2\n    },\n    {\n      \"PULocationID\": 237,\n      \"DOLocationID\": 238,\n      \"trip_distance\": 3.8\n    }\n  ]\n}"
        },
        "url": {
          "raw": "http://localhost:8000/predict/batch",
          "protocol": "http",
          "host": ["localhost"],
          "port": "8000",
          "path": ["predict", "batch"]
        }
      }
    }
  ]
}
```

**Para importar en Postman:**
1. Click "Import" en Postman
2. Seleccionar el archivo JSON
3. Click "Import"

---

## 🎯 cURL vs. Postman: ¿Cuándo usar cada uno?

Ya viste que ambos hacen lo mismo. La pregunta real es: **¿cuál usar para qué situación?**

### ✅ Usa **cURL** cuando...

| Situación | Por qué |
|-----------|---------|
| Estás en un servidor remoto (SSH) | No hay interfaz gráfica |
| Quieres **automatizar** con scripts bash | cURL se integra nativamente con shell |
| Necesitas hacer un **smoke test rápido** | Un solo comando y listo |
| Estás debuggeando **CI/CD** | GitHub Actions, Jenkins, etc. usan cURL |
| Quieres copiar/pegar un ejemplo de la documentación | Casi toda doc usa cURL |
| Estás mostrando código en un tutorial/blog | Es texto plano, fácil de compartir |
| Necesitas hacer **monitoreo** con `watch` o cron | Ej: health checks cada minuto |

**Ejemplo típico en MLOps**: En el pipeline de despliegue, después de levantar el servicio, corres un `curl` para verificar que el `/health` responde antes de marcar el deploy como exitoso.

```bash
# En un script de CI/CD
if curl -s -f http://api:8000/health > /dev/null; then
  echo "API lista"
else
  echo "API falló - rollback"
  exit 1
fi
```

### ✅ Usa **Postman** cuando...

| Situación | Por qué |
|-----------|---------|
| Estás **explorando una API nueva** | Mejor visualización |
| Estás **desarrollando** la API y pruebas mucho | Historial + colecciones |
| Trabajas en **equipo** y quieren compartir tests | Workspaces colaborativos |
| Necesitas probar con **diferentes ambientes** (dev/staging/prod) | Variables de entorno nativas |
| Quieres **documentar** ejemplos para otros | Colecciones exportables |
| Necesitas **ver** las respuestas JSON de forma legible | Auto-formato + syntax highlighting |
| Quieres **tests automatizados** con assertions | Postman tiene runner integrado |

**Ejemplo típico en MLOps**: El data scientist que no es ingeniero backend prueba los endpoints del modelo desde Postman, guarda la colección, y se la pasa al equipo de QA.

### 🎓 Recomendación para tu flujo como estudiante

1. **Aprende cURL primero** (aunque sea lo básico: `-X`, `-H`, `-d`). Es el "lenguaje común" de todas las APIs.
2. **Usa Postman para explorar** APIs nuevas y guardar colecciones útiles.
3. **Usa cURL en automatización** (scripts, CI/CD, docker-compose health checks).
4. **En el mundo real**, un ingeniero MLOps usa **ambos** todos los días.

### 🚀 Truco: Convertir entre cURL y Postman

- **Postman → cURL**: Click en "Code" (botón `</>` a la derecha) → seleccionar "cURL"
- **cURL → Postman**: "Import" → pegar el comando cURL → Postman lo convierte automáticamente

```
┌──────────┐   Import cURL    ┌──────────┐
│   cURL   │ ───────────────→ │ Postman  │
│ comando  │                  │ request  │
│          │ ←─────────────── │          │
└──────────┘   Copy as cURL   └──────────┘
```

### 🛠️ Otras herramientas que hacen lo mismo

Para que tengas contexto completo, estas son alternativas comunes:

| Herramienta | Tipo | Cuándo se usa |
|-------------|------|---------------|
| **cURL** | CLI | Universal, scripts |
| **Postman** | GUI | Exploración, equipos |
| **Insomnia** | GUI | Alternativa a Postman (más liviana) |
| **HTTPie** | CLI | cURL "moderno", más legible |
| **Thunder Client** | VS Code ext | Dentro del editor |
| **Python `requests`** | Código | Integración en apps |
| **Bruno** | GUI | Open source, archivos planos |

**Ejemplo HTTPie** (por si lo ves en algún tutorial):
```bash
http POST localhost:8000/predict PULocationID:=161 DOLocationID:=236 trip_distance:=5.2
```
Mismo resultado que el cURL equivalente, pero más corto.

---

## Códigos de Respuesta HTTP

| Código | Significado | Cuándo ocurre |
|--------|-------------|---------------|
| **200** | OK | Request exitoso |
| **422** | Unprocessable Entity | Error de validación (datos inválidos) |
| **500** | Internal Server Error | Error en el servidor/modelo |
| **503** | Service Unavailable | Modelo no cargado |

---

## Errores Comunes

### **Error 422: Validation Error**

**Causa:** Datos inválidos en el request

**Ejemplo:**
```json
{
  "detail": [
    {
      "loc": ["body", "trip_distance"],
      "msg": "ensure this value is greater than 0",
      "type": "value_error"
    }
  ]
}
```

**Solución:** Verificar que:
- `PULocationID` y `DOLocationID` estén entre 1 y 265
- `trip_distance` sea mayor a 0 y menor o igual a 100

---

### **Error 503: Service Unavailable**

**Causa:** Modelo no cargado

**Solución:**
```bash
# Copiar modelo primero
uv run python copy_model.py

# Reiniciar API
uv run uvicorn app:app --reload
```

---

## Casos de Uso

### **1. Predicción en Tiempo Real**
```bash
# Un usuario solicita estimación de duración
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"PULocationID": 161, "DOLocationID": 236, "trip_distance": 5.2}'
```

### **2. Procesamiento Batch**
```bash
# Procesar múltiples viajes de un archivo
curl -X POST http://localhost:8000/predict/batch \
  -H "Content-Type: application/json" \
  -d @trips.json
```

### **3. Monitoreo de Salud**
```bash
# Verificar cada 30 segundos
watch -n 30 curl -s http://localhost:8000/health
```

---

##  Resumen Rápido

```bash
# 1. Copiar modelo
uv run python copy_model.py

# 2. Iniciar API
uv run uvicorn app:app --reload

# 3. Verificar salud
curl http://localhost:8000/health

# 4. Hacer predicción
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"PULocationID": 161, "DOLocationID": 236, "trip_distance": 5.2}'

# 5. Ver documentación
open http://localhost:8000/docs
```

---

¡API lista para usar! 🎉
