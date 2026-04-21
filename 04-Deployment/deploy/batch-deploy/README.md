# **Batch** Deployment - Predicciones Automatizadas

Sistema de predicciones por lotes para duración de viajes de taxis NYC usando el modelo entrenado con Prefect + MLflow.

---

## ⚠️ Prerrequisito: Servidor de Prefect

Prefect 3.x necesita un **backend** para guardar el estado de los flows, logs y artefactos. Si intentas correr cualquier flow sin uno, verás este error:

```
ValueError: No Prefect API URL provided. Please set PREFECT_API_URL
to the address of a running Prefect server.
```

Tienes dos formas de solucionarlo. Elige **una**:

### **Opción A (recomendada): Servidor local con UI**

Abre **otra terminal** y déjala corriendo:

```bash
prefect server start
```

Esto levanta la UI de Prefect en [http://127.0.0.1:4200](http://127.0.0.1:4200) — ahí verás flows, tasks, logs y artefactos de cada corrida.

En **la terminal donde vas a correr los flows**, apunta Prefect al servidor:

```bash
prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
```

Solo necesitas hacerlo **una vez**: Prefect guarda la configuración en `~/.prefect/profiles.toml`.

### **Opción B (sin UI): Modo efímero**

Si no te interesa la UI y solo quieres que el flow corra:

```bash
prefect config set PREFECT_SERVER_ALLOW_EPHEMERAL_MODE=true
```

**Desventaja:** no hay UI, no hay historial visual, no puedes navegar artefactos después. Pero no necesitas mantener una terminal extra abierta.

### ¿Cuál elegir? Depende de qué comando vas a correr

| Comando | Qué hace | Opción A (servidor) | Opción B (efímero) |
|---------|----------|---------------------|--------------------|
| `uv run python src/prefect_flows.py` | Corre el flow **una sola vez** | ✅ Funciona | ✅ Funciona |
| `uv run python deploy_batch.py` (`.serve()`) | Deja un deployment **programado con cron** | ✅ **Única opción válida** | ❌ **NO funciona** |

**Razón técnica:** `.serve()` deja un proceso vivo que espera el schedule (cron). Para registrar el deployment y que alguien pueda dispararlo, **necesita un servidor real persistente**. El modo efímero solo crea un server en memoria para una sola corrida — no sirve para schedules.

**Si vas a usar `deploy_batch.py`, forzosamente usa Opción A.**

### Verificar que quedó bien

```bash
prefect config view
```

Debes ver ya sea `PREFECT_API_URL='http://127.0.0.1:4200/api'` (Opción A) o `PREFECT_SERVER_ALLOW_EPHEMERAL_MODE='true'` (Opción B).

### ⚠️ Error común: mezclar las dos opciones

Si probaste la Opción B primero y después arrancaste un servidor sin hacer `prefect config set PREFECT_API_URL=...`, te vas a topar con este error al correr `.serve()`:

```
WARNING | prefect.runner - Cannot schedule flows on an ephemeral server
[...]
ValueError: No Prefect API URL provided.
```

Traducción: tu servidor está corriendo pero tu script no sabe dónde está.

**Solución:**
```bash
prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
prefect config unset PREFECT_SERVER_ALLOW_EPHEMERAL_MODE
prefect config view   # verifica
```

---

## 📋 Paso a Paso

### **Paso 1: Copiar Modelo del Pipeline**

Después de entrenar el modelo con el pipeline, copia los archivos del modelo:

#### **Opción A: Script Python (Mac, Linux, Windows)**

```bash
cd 04-Deployment/deploy/batch-deploy

# Copiar modelo más reciente del pipeline
uv run python copy_model.py
```

### **Paso 2: Ejecutar Predicciones Batch**

#### **Opción A: Ejecución Manual (Pruebas)**

```bash
# Ejecutar flow completo de Prefect (100 viajes)
uv run python src/prefect_flows.py
```

#### **Opción B: Deployment Automático (Producción) - Cada Hora con 1000 Viajes**

```bash
# Ejecutar deployment automático (mantener corriendo)
uv run python deploy_batch.py
```

**El deployment automático:**
- **Frecuencia**: Cada hora (cron: `0 * * * *`)
- **Viajes por batch**: 1000 (configurado en `config/settings.py`)
- **Genera**: Nuevos datos aleatorios cada hora
- **Predice**: Duración de 1000 viajes
- **Guarda**: En SQL con batch_id único (timestamp)
- **Mantener corriendo**: El script debe permanecer activo para ejecutar el schedule

### **2. Ejecutar Manualmente (Pruebas)**

Para probar con 100 viajes:

```bash
uv run python src/prefect_flows.py
```

**Esto hará:**
- ✅ Generar 100 viajes sintéticos
- ✅ Hacer predicciones
- ✅ Guardar en base de datos
- ✅ Mostrar estadísticas

---

### **3. Deployment Automático (Producción)**

Para ejecutar automáticamente cada hora con 1000 viajes:

```bash
uv run python deploy_batch.py
```

**Importante:** El script quedará corriendo. **No lo cierres** si quieres que siga ejecutándose cada hora.

---

## 📊 Ver las Predicciones

### **Opción 1: Extensión SQLite en VS Code (Recomendado)**

1. **Instalar extensión** en VS Code:
   - Buscar "SQLite Viewer" o "SQLite" en extensiones
   - Instalar la extensión

2. **Abrir la base de datos:**
   - Navegar a: `data/database/predictions.db`
   - Click derecho → "Open Database"
   - O simplemente hacer click en el archivo

3. **Explorar los datos:**
   - Ver tabla `predictions`
   - Ejecutar queries SQL
   - Filtrar y ordenar datos

---

### **Opción 2: Terminal con SQLite**

```bash
# Abrir base de datos
sqlite3 data/database/predictions.db

# Ver todas las predicciones
SELECT * FROM predictions LIMIT 10;

# Ver estadísticas
SELECT COUNT(*) as total, 
       ROUND(AVG(predicted_duration_minutes), 2) as promedio
FROM predictions;

# Salir
.quit
```

---

### **Opción 3: Queries SQL Útiles**

Usa las queries del archivo `queries_batch_predictions` para:
- 📊 Total de predicciones por día
- 📈 Distribución de duraciones
- 🔍 Detección de anomalías
- 🗺️ Rutas más frecuentes

Copia y pega las queries en la extensión SQLite o en la terminal.

---

## 🔄 Actualizar el Modelo

Cuando entrenes un nuevo modelo:

```bash
# 1. Copiar nuevo modelo
uv run python copy_model.py

# 2. Si el deployment está corriendo, reinícialo:
#    - Presiona Ctrl+C para detener
#    - Ejecuta de nuevo:
uv run python deploy_batch.py
```

---

## ⚙️ Configuración

Editar `config/settings.py` para cambiar:

- **NUM_TRIPS**: Número de viajes por batch (default: 1000)
- **BATCH_SCHEDULE**: Frecuencia (default: `"0 * * * *"` = cada hora)

---

## 📁 Estructura de Archivos

```
batch-deploy/
├── config/settings.py          # Configuración
├── src/
│   ├── prefect_flows.py       # Orquestación con Prefect
│   ├── batch_predictor.py     # Lógica de predicción
│   ├── data_generator.py      # Generación de datos
│   └── database.py            # Manejo de BD
├── model/                     # Modelo copiado
├── data/
│   ├── input/                # Datos de entrada (.parquet)
│   └── database/             # SQLite DB (predictions.db)
├── copy_model.py             # Copiar modelo
├── deploy_batch.py           # Deployment automático
└── queries_batch_predictions # Queries SQL útiles
```

---

## ✅ Resumen Rápido

```bash
# 1. Copiar modelo
uv run python copy_model.py

# 2. Probar (100 viajes)
uv run python src/prefect_flows.py

# 3. Ver resultados (abrir data/database/predictions.db en VS Code)

# 4. Deployment automático (1000 viajes cada hora)
uv run python deploy_batch.py
```

¡Listo! That's all. 