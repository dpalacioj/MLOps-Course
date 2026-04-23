# Notas del Profesor — Clase Magistral Web Service + AWS

> Material de apoyo para dictar `CLASE_MAGISTRAL_WEB_SERVICE.md` a estudiantes de posgrado en IA con poca experiencia en industria.
> Duración total: **2 h 30 min (150 minutos)**.
> Audiencia: no son ingenieros de software, aunque tienen fundamentos sólidos de ML y Python.
>
> **Formato de la parte AWS**: puramente **teórica**. No hay despliegue en vivo en EC2. El Bloque 10 se dicta como walkthrough comentado del archivo `web-service-aws/GUIA_AWS_EC2.md`, apoyado en screenshots y en un simulacro de terminal. La única demo en vivo de la clase es el Bloque 5 (servicio FastAPI corriendo con Docker en la laptop del profesor).

---

## Plan general por bloques

| Bloque | Contenido | Tiempo | Interactivo | Acumulado |
|--------|-----------|--------|-------------|-----------|
| 1 | De qué estamos hablando | 5 min | — | 0:05 |
| 2 | Anatomía de una API de ML | 20 min | ✔ | 0:25 |
| 3 | Pydantic: contrato de tu API | 15 min | ✔ | 0:40 |
| 4 | Cargar el modelo una sola vez | 10 min | — | 0:50 |
| 5 | Los 4 endpoints en acción | **20 min — DEMO en vivo** | ✔✔ | 1:10 |
| 6 | Docker a fondo | 15 min | ✔ | 1:25 |
| 7 | Docker Compose y healthchecks | 10 min | — | 1:35 |
| 8 | Frontend + Postman | 10 min | ✔ | 1:45 |
| 9 | AWS EC2: fundamentos | 18 min | ✔ | 2:03 |
| 10 | Walkthrough comentado del despliegue (teórico) | 15 min | ✔ | 2:18 |
| 11 | Flask vs FastAPI en el folder AWS | 5 min | — | 2:23 |
| 12 | Seguridad, costos, producción real | 7 min | ✔ | 2:30 |

**Regla de oro**: si vas atrasado, recorta del Bloque 11 y 12, **nunca** del Bloque 5 (única demo en vivo de la clase) ni del Bloque 10 (es el cierre conceptual del módulo).

---

## Antes de empezar (prep de 15 min)

### Checklist técnica

- [ ] Docker Desktop corriendo y con al menos 4 GB de RAM asignada.
- [ ] Haber ejecutado `docker-compose up` una vez la noche anterior (imagen ya cacheada).
- [ ] Modelo ya copiado (`python copy_model.py`).
- [ ] Postman instalado con la colección importada.
- [ ] Terminal con fuente grande (16pt mínimo).
- [ ] Navegador con pestañas listas: `localhost:8000`, `localhost:8000/docs`, `localhost:8000/health`.
- [ ] Tener abierto `web-service-aws/GUIA_AWS_EC2.md` para el walkthrough teórico del Bloque 10.
- [ ] (Opcional) Screenshots previos de: la consola de EC2, el panel de Security Groups, un SSH funcionando, un `docker ps` con el contenedor `taxi-service`. Estos reemplazan la demo en vivo.
- [ ] (Opcional) Si tienes acceso read-only a una cuenta AWS personal, abre la consola de EC2 en una pestaña para hacer el "tour" visual del Bloque 9 sin desplegar nada.

### Proyección

- Mueve la terminal y el editor a **monitor externo**, deja la UI del Swagger visible.
- Ten abierto el `CLASE_MAGISTRAL_WEB_SERVICE.md` renderizado en VS Code (Ctrl+Shift+V) para usar de guía.

### Energía

Es una clase de 2h30. A los 80 minutos habrá una caída de atención natural. El Bloque 8 (demo corta) y el Bloque 9 (cambio de tema hacia la nube) funcionan como reenganche.

---

## Bloque 1 · De qué estamos hablando (0:00 → 0:05)

### Objetivo

Reencuadrar el módulo completo. Que entiendan que hoy cierran el círculo.

### Cómo abrir

> *"La semana pasada aprendieron a empaquetar con Docker y a correr un pipeline por lotes. Hoy vamos a hacer dos cosas: meter el modelo detrás de una API que responda al instante, y luego subir esa API a un servidor en AWS para que la pueda usar cualquier persona en el mundo."*

### Interacción sugerida

Pregunta rápida (máximo 2 min):

> *"Díganme una app que ustedes usan a diario y que probablemente tenga un modelo de ML atrás respondiendo en tiempo real."*

Respuestas típicas: Google Maps (ETA), Spotify (recomendaciones), Uber (precio), Instagram (feed). Todo eso es el patrón del Bloque 3 del folder `web-service/`.

### Qué NO hacer

No entrar a hablar de microservicios, gRPC, event-driven. Se vuelven dispersos rápido.

---

## Bloque 2 · Anatomía de una API de ML (0:05 → 0:25)

### Objetivo

Que puedan dibujar en una servilleta qué hace cualquier API de predicción, sin mirar el código.

### Cómo estructurarlo

1. **Las 5 cosas que hace toda API** (3 min) — escríbelo en el pizarrón.
2. **Tour del árbol del folder** (5 min) — muéstralo con `tree web-service/` en terminal.
3. **Separación de responsabilidades** (5 min) — usa la analogía del banco: `app.py` es el cajero, `schemas.py` es el portero, `model_loader.py` es el analista.
4. **Código mínimo de `app.py`** (7 min) — lee línea a línea el ejemplo del bloque.

### Momento de interacción (3 min)

Proyecta el código de `app.py` y pregunta:

> *"Si yo borro la línea `@app.on_event("startup")`, ¿qué creen que pasa?"*

Deja que piensen. La respuesta es: el modelo no carga, y en la primera petición a `/predict` el servidor crashea con un `AttributeError`. Esto conecta con el Bloque 4.

### Tip pedagógico

Estos estudiantes han visto muchos notebooks. Es la primera vez que ven un proyecto **partido en archivos por responsabilidad**. Enfatiza que eso **no** es overengineering: es la diferencia entre un script de tesis y un servicio que mantienes tú y tu equipo durante 2 años.

### Ejemplo concreto para mostrar

Abre el VSCode al lado y haz esta comparación en vivo:

```
¿Dónde cambias la validación del rango de location ID?  → src/schemas.py
¿Dónde cambias la URL del endpoint?                     → app.py
¿Dónde cambias cómo se carga el modelo?                 → src/model_loader.py
```

Esta pregunta las vas a rehacer en el Bloque 6 y 9. Se vuelve un motivo recurrente.

### Preguntas que van a salir

| Pregunta | Respuesta rápida |
|----------|------------------|
| "¿Por qué no uso Flask como todos los tutoriales?" | Pospón hasta el Bloque 11. |
| "¿Esto es como Django?" | Django es más grande, pensado para web apps completas con ORM. FastAPI es específico para APIs. |
| "¿Se puede usar esto con modelos de deep learning?" | Sí, exactamente igual. Cambias `model_loader.py` para que cargue un PyTorch/Keras model. El patrón es idéntico. |

---

## Bloque 3 · Pydantic — el contrato de tu API (0:25 → 0:40)

### Objetivo

Convencerlos de que Pydantic **no es opcional** en APIs de ML.

### Cómo engancharlos

Empieza con un *horror story*:

> *"Imagínense que su modelo está en producción en un banco. Alguien llama al endpoint con `trip_distance: -5`. Sin validación, el modelo te devuelve una duración negativa, y tu app le dice al usuario: 'Este viaje dura -3 minutos'. Ya tienes un ticket de soporte, un PR de hotfix, y tu tech lead te está buscando en Slack."*

### Estructura

1. **Problema sin Pydantic** (3 min) — muestra el bloque `ride = request.get_json()` y pregunta qué puede romper.
2. **`TripRequest` línea a línea** (5 min) — explica `...`, `Field`, `@field_validator`.
3. **Demo del 422** (4 min, **EN VIVO**) — manda un request con `trip_distance: 150` desde Postman. Muestra el JSON de error.
4. **Los 5 esquemas del proyecto** (3 min) — lista rápida.

### Demo clave (haz esto en vivo)

Con el contenedor ya corriendo, abre Postman y prepara 3 requests:

**Request 1: válido**
```json
{"PULocationID": 161, "DOLocationID": 236, "trip_distance": 5.2}
```
→ `200 OK`, predicción.

**Request 2: fuera de rango**
```json
{"PULocationID": 500, "DOLocationID": 236, "trip_distance": 5.2}
```
→ `422`, mensaje de error **automático**.

**Request 3: tipo incorrecto**
```json
{"PULocationID": "hola", "DOLocationID": 236, "trip_distance": 5.2}
```
→ `422`, "value is not a valid integer".

El momento "aja" es cuando ven que **nunca escribieron** código para validar eso. Lo hizo Pydantic gratis.

### Analogía para estudiantes no-ingenieros

> *"Pydantic es como el control de pasaportes. No importa qué traigas, si no cumple los requisitos, ni siquiera entras al país. El modelo solo habla con datos que ya pasaron el control."*

### Ejercicio guiado (opcional, si sobra tiempo)

> *"Abran `src/schemas.py` y cambien `le=265` a `le=5`. Reinicien el contenedor. Manden el mismo request de antes con `PULocationID: 161`. ¿Qué pasa?"*

Spoiler: ahora 161 también es inválido. Esto les muestra que **cambiar una línea de Pydantic cambia el comportamiento de toda la API sin tocar nada más**.

### Producción real (conecta con memoria de alumnos)

Esta es una buena oportunidad para conectar con **lo que pasa en producción**:

> *"En Databricks Model Serving y SageMaker Endpoints, el input schema se define también con algo equivalente. Databricks usa MLflow signatures, SageMaker usa un `InputHandler`. El concepto es idéntico: validar antes de que los datos lleguen al modelo."*

---

## Bloque 4 · Cargar el modelo UNA sola vez (0:40 → 0:50)

### Objetivo

Grabar el patrón singleton + lifespan en sus cabezas.

### Cómo abrir

> *"Ayer cuando prepararon el notebook con su modelo, ¿cuánto se demora `mlflow.load_model()`? ¿5 segundos? Imagínense 1000 peticiones por segundo multiplicadas por 5 segundos. Bye bye servidor."*

### Estructura

1. **El error del principiante** (2 min) — muestra el anti-pattern de cargar en cada request.
2. **El patrón singleton** (4 min) — explica el archivo `model_loader.py` completo.
3. **Los 3 artefactos** (2 min) — modelo, preprocessor, metadata.
4. **Consistencia train/serve** (2 min) — este es el punto crítico.

### El punto más importante de todo el Bloque 4

El **training-serving skew**. Dilo así:

> *"El 80% de los bugs de ML en producción no son del modelo. Son de que el preprocesamiento al servir no es idéntico al del entrenamiento. Aquí se resuelve cargando el MISMO `DictVectorizer` que se usó al entrenar."*

Muestra el archivo `preprocessor.b` y la línea `pickle.load(f)` en `model_loader.py`. Conéctalo con `copy_model.py`, que trae este archivo desde `batch-deploy/`.

### No confundir

Los estudiantes pueden preguntar: "¿por qué no uno un `.h5` o un `.pkl` solo?". Responde:

> *"Podrían. Pero separar el modelo del preprocesamiento tiene una ventaja: si mañana cambian solo el preprocesamiento (nueva feature), no tienen que reentrenar todo XGBoost. Lo van a ver en el folder de AWS donde sí está todo en un solo pickle."*

Eso deja un hilo suelto que cierras en el Bloque 11.

---

## Bloque 5 · Los 4 endpoints en acción (0:50 → 1:10) — **DEMO EN VIVO**

### Objetivo

Que vean el servicio real funcionando y lo toquen ellos.

### Guion de la demo

**Minuto 0-2 · Encender el servicio**
```bash
cd 04-Deployment/deploy/web-service
docker-compose up -d
docker-compose logs -f
```
Muestra el log `"Modelo cargado correctamente"`.

**Minuto 2-5 · `/health` en el navegador**
- Abre `http://localhost:8000/health`.
- Muestra el JSON con `model_loaded: true`, la versión, el RMSE.
- **Pregunta**: *"¿Qué esperaríamos ver si el modelo estuviera roto?"* → un `503`.
- Detén el contenedor con `docker stop nyc-taxi-api` y recarga `/health`. "Unable to connect".
- Vuélvelo a levantar.

**Minuto 5-9 · `/predict` con la UI web**
- Abre `http://localhost:8000/`.
- Llena el formulario (pickup 161, dropoff 236, distancia 5.2).
- Muestra la respuesta con emoji y todo.
- **Pregunta al aula**: *"Denme otras coordenadas para probar."* Un estudiante propone, tú tecleas.

**Minuto 9-13 · `/predict` con Postman**
- Muestra la misma petición desde Postman.
- Haz notar que la colección tiene varios ejemplos pre-armados.
- Prueba el de "Short trip" y el de "Long trip".

**Minuto 13-16 · `/predict/batch`**
- Abre el request batch de 10 viajes.
- Ejecútalo.
- **Pregunta**: *"Si yo necesitara predecir 5000 viajes, ¿cómo lo haría?"* → varias llamadas de 1000, o ir directo a batch por archivo.

**Minuto 16-20 · `/docs` — el regalo de FastAPI**
- Abre `http://localhost:8000/docs`.
- Despliega el `/predict`. Muestra que el mismo Pydantic que usamos para validar sirve de documentación.
- **Ejecuta desde la UI de Swagger**, sin Postman. Factor wow.

### Errores que te pueden pasar (y ya los preví)

| Error | Solución |
|-------|----------|
| Puerto 8000 ocupado | `lsof -i :8000` → kill | o cambia el puerto en `docker-compose.yml` |
| "Model not found" | No corriste `copy_model.py` antes del build |
| El contenedor da "unhealthy" | Sube el `start_period` del healthcheck |
| CORS error desde el HTML | Ya está configurado con `allow_origins=["*"]`, no debería pasar |

### Ejercicio guiado post-demo (5 min)

> **Ejercicio**: Abran Postman. En la colección hay un request llamado "Predict - Single Trip". Cambien `trip_distance` a `0.01` y envíenlo. Luego cámbienlo a `99.9`. Comparen las predicciones. ¿Tienen sentido?

Esto los pone a **jugar con el modelo** y les muestra que el modelo a veces extrapola mal en los bordes.

---

## Bloque 6 · Docker a fondo (1:10 → 1:25)

### Objetivo

Que entiendan **caché de capas**, porque es lo que distingue un Dockerfile de principiante de uno de senior.

### Estructura

1. **El Dockerfile completo** (3 min) — léelo en voz alta.
2. **El principio de capas** (6 min) — dibuja en el pizarrón las 5 capas y qué cambia con qué frecuencia.
3. **Pinneado de versiones** (2 min) — regla de oro.
4. **`python:3.11-slim` vs otros** (2 min) — tamaños comparados.
5. **`0.0.0.0` es obligatorio** (2 min) — el error #1.

### Demo rápida del caché (4 min, EN VIVO)

Con el contenedor ya construido, haz esto:

```bash
# 1. Cambia UNA línea en app.py (ej: un comentario nuevo)
echo "# comment" >> app.py

# 2. Rebuild
docker build -t nyc-taxi-api .
```

Muestra cómo Docker salta las primeras capas con `CACHED` y solo reconstruye desde `COPY app.py`. Esto toma 5 segundos en vez de 3 minutos.

Ahora haz lo opuesto:

```bash
# 3. Cambia una línea del Dockerfile ANTES de la instalación (ej: cambia la versión de Python)
# 4. Rebuild
```

Ahora todo se reconstruye desde cero. Esto les enseña:

> *"El orden del Dockerfile no es estético. Es una decisión de ingeniería que se paga en minutos de desarrollo."*

### Analogía para no-ingenieros

> *"Docker es como hacer una lasaña en capas. Si cambiaste el queso de arriba, no tienes que rehacer la pasta y la salsa de abajo. Pero si cambias la pasta, rehaces todo lo que va encima."*

### Preguntas que van a salir

| Pregunta | Respuesta |
|----------|-----------|
| "¿Por qué no usamos Alpine si es más pequeño?" | Alpine usa musl libc, y muchas libs de ML (numpy, scipy, xgboost) vienen compiladas contra glibc. Romper compatibilidad = horas depurando. `slim` es el punto dulce. |
| "¿Qué pasa si mi modelo pesa 10 GB?" | Ahí no lo metes en la imagen: lo montas como **volume** o lo bajas al arranque desde **S3** o **MLflow Model Registry**. |
| "¿Multi-stage builds?" | Mencionalo: `FROM python:3.11 as builder` + `FROM python:3.11-slim as runtime`. Lo dejan como tarea de exploración. |

---

## Bloque 7 · Docker Compose y healthchecks (1:25 → 1:35)

### Objetivo

Que vean que Compose no es magia, es una forma declarativa de reemplazar comandos largos.

### Cómo hilarlo

Arranca con una pregunta:

> *"Si mañana les pido que agreguen una base de datos Postgres al servicio para guardar cada predicción, ¿cómo lo harían solo con `docker run`?"*

Respuesta: escribirían dos comandos largos + una `docker network create`. En Compose, agregan 5 líneas al YAML.

### Estructura

1. **El YAML completo** (2 min).
2. **`docker run` vs Compose** (2 min) — tabla comparativa.
3. **`PYTHONUNBUFFERED=1`** (2 min) — el detalle de oro.
4. **Restart policies** (2 min).
5. **Healthcheck a fondo** (2 min).

### El punto de los healthchecks

Dilo así:

> *"Healthcheck es como el examen médico del contenedor. Docker hace el examen cada 30 segundos. Si falla 3 veces seguidas, marca al contenedor como `unhealthy` y en Kubernetes, lo mataría y crearía uno nuevo."*

Muestra en la terminal:

```bash
docker ps
# STATUS: Up 2 minutes (healthy)
```

Luego rompe el endpoint `/health` (puedes editar `is_loaded()` para que siempre retorne `False` y rebuild). Mira cómo en 90 segundos pasa a `unhealthy`.

### Conexión con producción

> *"En Kubernetes esto mismo se llama `livenessProbe` y `readinessProbe`. En AWS ECS, `healthCheck`. En Databricks Model Serving, el health check es automático y no tienen que hacer nada. Pero saber cómo funciona por debajo les da control cuando algo falla."*

---

## Bloque 8 · Frontend + Postman (1:35 → 1:45)

### Objetivo

Mostrar que tener una UI mínima multiplica el valor de la demo ante stakeholders.

### Estructura

1. **`/` sirve un HTML** (2 min) — explica el `TemplateResponse`.
2. **Por qué tener UI importa** (2 min) — para demos, stakeholders, validación end-to-end.
3. **Postman collection + environments** (4 min) — demo rápida.
4. **cURL vs Postman** (2 min) — cuándo cada uno.

### Demo de environments de Postman (3 min)

Si tienes tiempo, crea 2 environments:

- `Local` → `base_url = http://localhost:8000`
- `EC2` → `base_url = http://ec2-xxx.compute-1.amazonaws.com:9696`

Cambia el dropdown arriba a la derecha y muestra cómo el mismo request va a lugares distintos sin cambiar nada.

Esto les ahorra horas el día que tengan que probar en 3 ambientes.

### Pregunta para mantener atención

> *"¿Quién de ustedes, si fuera Product Manager, querría abrir Postman para probar un modelo vs. llenar un formulario y darle click?"*

Aquí el chiste vende: **nadie** quiere Postman si tiene una UI. Y sin embargo, todos los cursos de MLOps saltan la UI. Un formulario de 20 líneas multiplica tu capacidad de demostrar valor.

---

## Bloque 9 · AWS EC2: fundamentos (1:45 → 2:03)

### Objetivo

Desmitificar la nube. EC2 = laptop rentada. Que el vocabulario deje de sonarles a ruido.

### Encuadre honesto con el aula (importante)

Abre el bloque con una aclaración franca:

> *"Hoy no vamos a desplegar en AWS en vivo. La razón es que montar una cuenta, una instancia y un Security Group en tiempo real tomaría media clase y se puede romper por mil lados. Lo que vamos a hacer es entender **exactamente** qué pasa en cada paso, con la guía real que seguiría cualquiera que lo quisiera hacer en su casa. El ejercicio 3 que les dejo los invita a hacerlo después por su cuenta."*

Esto baja la ansiedad de "¿vamos a ver la nube?" y deja claro el trato: **conceptos + walkthrough + tarea**.

### Cómo abrir (después del encuadre)

> *"EC2 suena intimidante. Es solo una laptop que le rentas a Amazon por horas. Si tú prendes tu laptop, le pones una IP pública y la dejas encendida 24/7, sería lo mismo. EC2 te da la IP pública, el internet, el respaldo eléctrico y la garantía de que no se va a apagar."*

### Estructura

1. **La analogía del apartamento** (4 min) — la más pedagógica.
2. **Vocabulario AWS** (6 min) — tabla completa, rápido pero sin atropellar.
3. **Los 6 pasos de despliegue** (4 min) — vista aérea antes de meternos al detalle.
4. **Regiones, AMIs y free tier** (4 min) — geografía básica de AWS.

### Tour visual (sin desplegar nada)

Tienes dos opciones, elige la que puedas:

**Opción A · Acceso read-only a la consola AWS**
Abre la consola y muestra:
1. Dashboard de EC2.
2. La columna "Public IPv4 DNS" y cómo se ve el nombre.
3. La pestaña **Security** de una instancia.
4. La UI del Security Group → Edit inbound rules.

**Opción B · Screenshots + diagrama en pizarrón**
Si no tienes acceso, usa capturas previas (internet está lleno de tutoriales con screenshots claros de la consola). Dibuja en el pizarrón el diagrama:

```
[tu laptop]  --ssh-->  [Public DNS de AWS]
                              |
                       [Security Group]
                              |
                       [EC2 Instance]
                              |
                       [Docker Container: 9696]
```

### Pregunta del aula

> *"¿Cuánto creen que cuesta al mes tener una `t2.micro` prendida 24/7?"*

Déjalos adivinar. La respuesta: en el free tier de AWS, los primeros 12 meses son **gratis** (750 h/mes). Después son ~$8.50/mes.

### Si preguntan por SageMaker/Databricks (aprovecha aquí)

> *"SageMaker Endpoints hace exactamente lo que describiría la guía de hoy, pero sin que tú veas EC2 ni SSH ni Docker. Por dentro, AWS levanta una instancia, instala Docker, hace pull de tu imagen, la corre, y le pone un load balancer delante. Lo que vamos a caminar ahora paso a paso es para que mañana, cuando usen SageMaker o Databricks Model Serving, sepan qué está pasando debajo del botón 'Deploy'."*

Esto conecta directamente con la memoria de que les interesa mucho SageMaker/Databricks.

---

## Bloque 10 · Walkthrough comentado del despliegue — teórico (2:03 → 2:18)

### Objetivo

Que al final del bloque los estudiantes puedan **narrar con sus palabras** los 6 pasos del despliegue AWS, entender qué comando hace qué, y saber dónde puede fallar cada paso. No necesitan haberlo ejecutado para quedar con el modelo mental correcto.

### Formato

Abre `web-service-aws/GUIA_AWS_EC2.md` en el proyector (es el mismo documento que ellos tienen). Haces un recorrido comentado, comando por comando, simulando la terminal en una ventana aparte (puedes escribir los comandos pero **sin ejecutarlos**, o simplemente leer desde la guía).

### Abrir el bloque

> *"Les voy a caminar por la guía completa. Imagínense que estamos haciendo pair programming: yo describo qué hace cada línea y ustedes levantan la mano cuando algo no cuadre. Si alguien quiere hacerlo después de clase, esta es literalmente la receta que tienen que seguir."*

### Guion paso a paso (15 min)

**Minuto 0-2 · Paso 1: SSH**

Muestra en la guía:
```bash
chmod 400 tu-clave.pem
ssh -i tu-clave.pem ec2-user@ec2-12-34-56-78.compute-1.amazonaws.com
```

Explica en voz alta:
- `chmod 400` = lectura solo para el dueño. Pregunta al aula: *"¿Qué creen que pasa si dejan la clave en `644`?"* → SSH la rechaza con un warning gigante. Es un control de seguridad que viene con el protocolo, no con AWS.
- `ec2-user@...` = el usuario por defecto en Amazon Linux. En Ubuntu sería `ubuntu@`. En RHEL, `ec2-user` también.
- El banner que verían al conectarse: "Welcome to Amazon Linux 2". Escríbelo en la terminal simulada para que sientan el momento.

**Minuto 2-5 · Paso 2: Instalar Docker**

Muestra:
```bash
sudo yum update -y
sudo yum install -y docker git
sudo service docker start
sudo usermod -a -G docker ec2-user
exit
```

Pregunta clave al aula: *"¿Por qué creen que dice `exit` al final, si todavía no hemos hecho nada?"*

Respuesta: los grupos de Linux solo se aplican al hacer login. Tienes que salir y volver a entrar para que tu usuario **herede** el grupo `docker` recién asignado. Este es el tipo de detalle que se descubre perdiendo 20 minutos frustrado la primera vez.

Analogía:
> *"Es como cuando te suben de cargo en el trabajo pero te dicen 'los permisos nuevos se aplican mañana'. Hoy sigues siendo el mismo."*

**Minuto 5-8 · Pasos 3 y 4: Clonar, construir, correr**

Muestra:
```bash
git clone https://github.com/tu-usuario/tu-repositorio.git
cd tu-repositorio/04-Deployment/deploy/web-service-aws
docker build -t taxi-prediction .
docker run -d -p 9696:9696 --name taxi-service taxi-prediction
docker ps
```

Aquí viene el **punto de alta densidad**: aprovecha para decirles que los comandos 3-4 son **idénticos** a lo que hicieron el día que vieron Docker la primera vez. No hay nada nuevo.

> *"Se dan cuenta de algo? Los pasos más complejos conceptualmente ya los hicimos. Lo 'nuevo' de AWS son los pasos 1 (SSH), 2 (instalar Docker) y 5 (Security Group). El resto es Docker de ayer."*

Este reframe reduce el miedo a la nube.

**Minuto 8-11 · Paso 5: Security Group (el paso que más atasca en la vida real)**

Muestra en el pizarrón o con screenshot el panel del Security Group:

```
Edit inbound rules:
  Type: Custom TCP
  Port range: 9696
  Source: 0.0.0.0/0
  Description: Taxi Prediction API
```

Pregunta al aula: *"¿Qué significa `0.0.0.0/0`?"*

Respuesta: "cualquier IP del mundo". Muestra la alternativa `My IP` (solo tu IP actual).

Anécdota real que puedes contar (ficticia pero creíble):
> *"Un estudiante en un curso anterior dejó su endpoint abierto al mundo durante una semana. Un bot encontró el puerto, empezó a hacer 1000 requests/segundo, y cuando llegó la factura de AWS eran 40 USD de transferencia de datos. En free tier, 40 USD duelen."*

Esto sirve de puente al Bloque 12.

**Minuto 11-14 · Paso 6: Probar desde fuera**

Muestra:
```bash
curl -X POST http://ec2-12-34-56-78.compute-1.amazonaws.com:9696/predict \
  -H "Content-Type: application/json" \
  -d '{"PULocationID": 161, "DOLocationID": 236, "trip_distance": 2.5}'
```

Respuesta esperada (léela en voz alta):
```json
{"duration": 12.34}
```

Dilo con énfasis:
> *"Esta respuesta viaja desde un servidor de Amazon en Virginia, pasa por los cables submarinos del Atlántico, atraviesa su ISP local, y llega a su laptop. Eso es lo que significa 'desplegar en la nube'."*

Este es el reemplazo conceptual del *glory shot* que hubiera sido ejecutarlo en vivo.

**Minuto 14-15 · Resumen visual**

Dibuja en el pizarrón (o muestra el diagrama que está en el Bloque 12 de `CLASE_MAGISTRAL_WEB_SERVICE.md`):

```
Paso 1: SSH          → llave en mano
Paso 2: Install      → Docker en el servidor
Paso 3-4: Build/Run  → igual que en tu laptop
Paso 5: Security Grp → abres la puerta
Paso 6: Test         → el mundo puede llamar
```

### Interacción sugerida (en paralelo, no adicional al tiempo)

Tres preguntas insertadas en el guion, una cada 4-5 min:

1. (Después del paso 1) *"¿Qué pasaría si subo mi `.pem` a GitHub por accidente?"* → cualquiera con internet puede entrar a la instancia.
2. (Después del paso 2) *"¿Por qué `ec2-user` y no `root`?"* → principio de menor privilegio; usar root es un anti-pattern.
3. (Después del paso 5) *"¿Qué otros puertos creen que están abiertos en el Security Group por defecto?"* → 22 para SSH. Ninguno más, salvo que lo agregues.

### Tarea de refuerzo (anúnciala al final del bloque)

> *"Si quieren hacer este despliegue en AWS después de clase, está el Ejercicio 3 en la sección de tareas. Requiere crear una cuenta AWS (gratuita primer año), y les recomiendo configurar un Budget Alert de 5 USD antes de hacer nada más. Con eso puestos, la guía que acabamos de caminar es literalmente el paso a paso."*

### Puntos de énfasis (no olvidar)

1. **"Los pasos 3-4 ya los saben."** Reduce ansiedad.
2. **"El `.pem` es la llave de la casa."** Si la pierden, pierden la instancia.
3. **"El Security Group es el paso que más gente olvida."** 80% de los "no me funciona" en tutoriales de AWS son puertos cerrados.
4. **"`0.0.0.0/0` en producción es inaceptable."** Plantar la semilla para Bloque 12.

---

## Bloque 11 · Flask vs FastAPI (2:15 → 2:20)

### Objetivo

Cerrar el misterio que dejamos en los Bloques 2-4.

### Cómo abrirlo

> *"Habrán notado que en la carpeta de AWS el código se ve más simple que en la de FastAPI. ¿Por qué?"*

### Estructura

1. **Muestra `predict.py`** (2 min) — ~15 líneas, Flask.
2. **Tabla comparativa** (2 min) — la del Bloque 11 del magistral.
3. **gunicorn vs uvicorn** (1 min) — referencia rápida.

### El punto clave

> *"No es que Flask sea peor. Es que tiene menos cosas. Cuando ustedes están aprendiendo EC2 por primera vez, 15 líneas de código es mejor que 200. Cuando ya dominen EC2 y estén en una empresa, FastAPI va a ser su opción por todo lo que vimos hoy."*

### Qué no hacer

No entres en guerra de frameworks. Di claramente: **los dos funcionan, eligen según contexto**.

---

## Bloque 12 · Seguridad, costos y producción real (2:20 → 2:30)

### Objetivo

Que salgan con humildad: hoy aprendieron el 70% de un despliegue. El 30% restante es lo que separa un MVP de producción.

### Estructura

1. **Lo que el tutorial hace bien** (1 min).
2. **Lo que el tutorial NO hace** (4 min) — tabla de riesgos.
3. **Costos del free tier** (2 min).
4. **Mapeo a servicios reales** (3 min) — la tabla de "en producción real".

### Pregunta final para fijar

> *"Si mañana su gerente les dice: 'Desplieguen su modelo para que 10,000 usuarios lo usen', ¿qué cosas de la tabla del Bloque 12 priorizarían ustedes?"*

Respuesta esperada:
1. Autenticación (API key mínimo).
2. HTTPS.
3. Rate limiting.
4. Monitoreo.
5. Billing alerts.

Este momento los **vacuna** contra creer que saben más de lo que saben.

### Mensajes de cierre

Dilo con énfasis:

> *"Hoy hicieron algo que hace 10 años requería un equipo de DevOps: desplegar un modelo de ML a internet. La diferencia entre ustedes y alguien que solo usa SageMaker es que ustedes entienden qué pasa por dentro. Eso los vuelve más valiosos, porque cuando algo se rompa en SageMaker, ustedes van a saber por dónde empezar a mirar."*

---

## Momentos de interacción — resumen

| Momento | Bloque | Tipo | Duración |
|---------|--------|------|----------|
| "Díganme una app con ML en tiempo real" | 1 | Pregunta abierta | 2 min |
| "¿Qué pasa si borro `@app.on_event`?" | 2 | Pregunta predictiva | 2 min |
| Demo de 422 en Postman | 3 | Demo dirigida (en vivo) | 4 min |
| Demo del servicio FastAPI completo | 5 | **Live demo + preguntas** | 20 min |
| Ejercicio de Postman con `trip_distance` extremo | 5 | Ejercicio guiado | 5 min |
| Demo del caché de capas Docker | 6 | Live demo | 4 min |
| Demo del healthcheck | 7 | Live demo | 2 min |
| Demo de environments de Postman | 8 | Live demo | 3 min |
| Tour de consola AWS (read-only) o screenshots | 9 | Tour dirigido | 5 min |
| "¿Cuánto cuesta una t2.micro?" | 9 | Pregunta abierta | 1 min |
| Walkthrough comentado del despliegue AWS | 10 | **Walkthrough teórico con preguntas** | 15 min |
| "¿Qué pasa si subo el `.pem` a GitHub?" + 2 preguntas más | 10 | Preguntas reflexivas | incluido |
| "¿Qué priorizarían para producción?" | 12 | Pregunta reflexiva | 3 min |

**Total de tiempo interactivo: ~66 minutos (44% de la clase).** Justo lo que necesita un aula de posgrado de 2h30.

**Nota**: la única **demo en vivo con comandos ejecutándose** es la del Bloque 5 (FastAPI + Docker local). Los Bloques 6, 7 y 8 tienen demos cortas sobre ese mismo servicio que ya está corriendo. El Bloque 10 es walkthrough teórico con terminal "simulada" (comandos leídos, no ejecutados).

---

## Ejercicios para dejar después de clase

### Ejercicio 1 — Agregar un endpoint (nivel fácil)

> Agregar un endpoint `GET /metrics` que devuelva:
> - Número de predicciones desde que arrancó el servicio
> - Predicción promedio de duración
> - Distribución (min, max, mediana) de `trip_distance` recibidos
>
> Pista: usar una variable global o Redis.

### Ejercicio 2 — Proteger la API (nivel medio)

> Agregar autenticación por API key.
> - Leer el header `X-API-Key` de cada petición.
> - Si no coincide con una variable de entorno, devolver `401 Unauthorized`.
> - El Dockerfile debe aceptar la API key como `ENV`.

### Ejercicio 3 — Desplegar con auto-restart (nivel medio)

> Modificar el Dockerfile del folder AWS para que tenga healthcheck.
> Redesplegar en EC2 con `--restart always`.
> Romper el servicio a propósito (matando el proceso desde adentro) y verificar que se auto-recupere.

### Ejercicio 4 — CI/CD básico (nivel avanzado)

> Escribir un GitHub Action que:
> - Se active en cada push a `main`.
> - Construya la imagen Docker.
> - La pushee a Docker Hub.
> - Haga SSH a una instancia EC2 y corra `docker pull` + `docker restart`.
>
> Pista: secrets de GitHub Actions para las credenciales.

### Ejercicio 5 — De EC2 a ECS (nivel experto)

> Reemplazar la instancia EC2 manual por un cluster ECS con Fargate.
> Comparar:
> - Tiempo de despliegue.
> - Costo mensual.
> - Esfuerzo operacional.
>
> Escribir un mini-informe de 1 página.

---

## Preguntas frecuentes que van a salir (respuestas listas)

### Sobre producción

**P: ¿Cómo se actualiza el modelo en producción sin tirar el servicio?**
R: Dos patrones: (1) **blue/green deployment** — levantas una nueva instancia con el modelo nuevo, cambias el load balancer, apagas la vieja. (2) **rolling update** — si tienes N instancias, las vas reemplazando una por una. En Kubernetes y ECS esto es automático.

**P: ¿Qué hago si mi modelo necesita GPU?**
R: EC2 tiene instancias con GPU (`p3.2xlarge`, `g4dn.xlarge`). Tu Dockerfile cambia: usas `nvidia/cuda` como base, instalas PyTorch con soporte CUDA, y corres el contenedor con `--gpus all`. El patrón FastAPI es idéntico.

**P: ¿Cómo sé si mi modelo está degradado?**
R: Este es el tema de **model monitoring**. Herramientas como **Evidently AI**, **Arize**, **Whylabs**, o construirlo con CloudWatch + alertas sobre distribuciones de inputs/outputs.

**P: ¿Databricks Model Serving vs SageMaker Endpoints vs esto?**
R: Databricks y SageMaker te ahorran el 80% del trabajo pero te encierran en su ecosistema. Lo que aprendieron hoy es el lingua franca: si entienden esto, pueden cambiar de plataforma. Para equipos de 1-3 personas, SageMaker/Databricks vale la pena. Para equipos >10, muchas veces es más barato mantener lo propio.

### Sobre alerting

**P: ¿Cómo me entero si mi API se cae a las 3 AM?**
R: **CloudWatch Alarms** → SNS → email/SMS/Slack. O, si usas Datadog/Grafana Cloud, configuran alertas sobre la métrica `up` del container. Regla básica: **si una alarma no despierta a alguien de noche, no es una alarma útil**.

### Sobre Docker en general

**P: ¿Y Kubernetes?**
R: Kubernetes es cuando tienes **muchos** contenedores (decenas o cientos) y necesitas orquestarlos. Lo que aprendieron hoy es la base. Cuando llegue el momento de Kubernetes, lo único nuevo son YAMLs adicionales y conceptos como pods, services, ingress. La lógica del contenedor no cambia.

**P: ¿Vale la pena aprender Docker bien?**
R: Es la habilidad transferible #1 entre roles de ML engineer, data scientist, MLOps, DevOps. Sí, vale cada minuto invertido.

### Sobre costos

**P: ¿Me van a cobrar si me olvido de apagar la instancia?**
R: Sí. Por eso lo primero que hacen hoy al salir es configurar un **Budget Alert** en AWS Billing Dashboard. $5/mes como umbral es un buen punto de partida para practicantes.

**P: ¿Puedo hacer esto todo gratis?**
R: Para este curso, sí — el free tier aguanta. Para producción real, empezarían a pagar desde ~$10/mes (instancia + storage + transferencia).

---

## Material complementario sugerido

Si quieres armar recursos extra para después de clase:

- **Video corto (5 min)**: grabar la demo del Bloque 10 en modo tutorial, subir a YouTube.
- **Cheatsheet imprimible**: los 6 pasos de AWS + los comandos de Docker más útiles.
- **Repo-plantilla**: fork del folder `web-service/` sin el modelo, para que hagan los ejercicios.
- **Post-mortem del día**: al día siguiente, un doc con las preguntas que salieron y no resolviste bien.

---

## Si algo sale mal: plan B

### Si Docker en tu laptop no arranca

Esta es la demo crítica de la clase (Bloque 5). Plan B: ten grabado un **screencast corto (5-10 min)** de la demo del servicio funcionando — `/health`, `/predict`, `/docs`. Si Docker muere en vivo, proyectas el video y comentas sobre él. No ideal, pero salva la clase.

Otra opción: tener la imagen ya corriendo en un contenedor de respaldo (`docker ps` debería mostrar `nyc-taxi-api` activo desde la noche anterior, así no dependes de levantarlo en vivo).

### Si no tienes internet

- El Bloque 5 funciona offline (todo corre en `localhost`).
- Los Bloques 6-8 también (Docker y Postman son locales).
- El Bloque 9 (tour AWS) es el más vulnerable: si dependías de la consola AWS, cambia a screenshots y al diagrama en pizarrón.
- El Bloque 10 es 100% offline por diseño (walkthrough de un archivo).

En general, esta clase es bastante resistente a la falta de internet.

### Si una pregunta te agarra en frío

> *"Buena pregunta. Déjenme pensarlo y les respondo bien al inicio de la próxima clase."*

Anótala. Respóndela al día siguiente con calma. Esto genera más confianza que inventar una respuesta imprecisa.

### Si un estudiante insiste en "por qué no lo hacemos en vivo en AWS"

Respuesta lista:

> *"Porque crear una cuenta AWS, verificarla con tarjeta de crédito, configurar IAM, lanzar una instancia y esperar a que pase los health checks de AWS toma entre 20 y 40 minutos en el mejor caso. Y si algo falla en vivo, se nos va media clase en debugging. Prefiero que hoy entiendan cada paso a profundidad y que hagan el despliegue ustedes la semana siguiente con el ejercicio 3, cuando puedan tomarse su tiempo y romper cosas sin afán."*

---

## Indicador de éxito al final de clase

Al terminar, ellos deberían poder responder (a sí mismos) estas 5 preguntas:

1. ¿Cómo valido inputs en una API de ML?
2. ¿Por qué cargo el modelo una sola vez y cómo?
3. ¿Qué es un healthcheck y por qué importa?
4. ¿Cuáles son los 6 pasos para desplegar en EC2?
5. ¿Por qué un Security Group cerrado mata mi API sin que yo lo note?

Si el 80% del aula puede, ganaste el día.
