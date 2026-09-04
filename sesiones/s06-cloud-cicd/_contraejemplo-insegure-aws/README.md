# CONTRAEJEMPLO — NO COPIAR

Este directorio es un servicio de predicción **que funciona**, con su `Dockerfile` y
una guía completa para desplegarlo en una máquina virtual de AWS. Es exactamente lo que
sale de seguir un tutorial de internet de principio a fin, y por eso está aquí: el
bloque de seguridad de la [sesión 6](../README.md) consiste en leer estos cinco
archivos y encontrar qué está mal **antes** de que alguien lo explique.

**No es un ejemplo a seguir.** El servicio correcto está en
[`src/taxi/api/`](../../../src/taxi/api/); la forma correcta de llevarlo a la nube, en
[`../04-demo-ecr-fargate/`](../04-demo-ecr-fargate/).

## Por qué se aprende con un contraejemplo

1. **Es realista.** Ninguno de estos defectos es absurdo; cada uno es lo que sale
   naturalmente cuando se aprende Docker y AWS a la vez y se quiere ver algo funcionar.
   Eso es exactamente lo que los hace peligrosos: no se ven.
2. **Una vulnerabilidad se aprende mejor leyéndola que escuchándola.** "No expongas
   el debugger" es una frase; ver el `debug=True` en la última línea de una guía de
   despliegue con el puerto abierto a internet es una lección.
3. **Todo funciona.** Ningún error de esta carpeta hace fallar nada. Ese es el punto:
   un despliegue inseguro se ve idéntico a uno seguro desde Postman.

El linter lo excluye (`extend-exclude` en el
[`pyproject.toml`](../../../pyproject.toml) de la raíz) para que estos errores no se
mezclen con los del código real. **No cambies esa exclusión**: si el contraejemplo
entrara al lint, alguien "arreglaría" el archivo y el material desaparecería.

Cada archivo lleva `# CONTRAEJEMPLO — NO COPIAR` en su cabecera, porque el archivo
suelto (fuera de este directorio, sin este README) es indistinguible de código real.

## Archivos

| Archivo | Qué es |
|---|---|
| [`predict.py`](predict.py) | El servicio: Flask, `pickle.load` a nivel de módulo, `debug=True` |
| [`test.py`](test.py) | Un `requests.post` a `localhost:9696`. No es un test: no afirma nada |
| [`Dockerfile`](Dockerfile) | Copia `lin_reg.bin` a la imagen; corre como root |
| [`pyproject.toml`](pyproject.toml) | Dependencias del servicio |
| [`guia-despliegue-ec2.md`](guia-despliegue-ec2.md) | La guía de despliegue, con el grupo de seguridad abierto a `0.0.0.0/0` |

---

## Los seis defectos, en orden de gravedad

### 1. El debugger de Werkzeug expuesto es ejecución remota de código

[`predict.py`, última línea](predict.py):

```python
app.run(debug=True, host='0.0.0.0', port=9696)
```

Con `debug=True`, Flask activa el depurador interactivo de Werkzeug. Cuando una
petición provoca una excepción, ese depurador sirve una página web con una **consola
de Python** en el contexto del proceso. Está protegida por un PIN que Werkzeug
imprime en el log del servidor y que se deriva de datos del entorno (usuario,
módulo, dirección MAC, `machine-id`): hay técnicas públicas para reconstruirlo si se
consigue una lectura de archivos, y en un contenedor esos datos son especialmente
predecibles.

Combínalo con lo que dice la guía de despliegue:

```text
Añade una regla de entrada:
  Rango de puertos: 9696
  Origen: Anywhere (0.0.0.0/0)
```

El resultado no es "una mala práctica". Es **una shell remota potencial en internet**,
en una guía que alguien va a seguir paso a paso.

Además, `app.run()` es el servidor de desarrollo de Werkzeug: un solo hilo por
defecto, sin gestión de procesos, y la propia documentación de Flask dice que no se
use en producción. Que el `Dockerfile` de esta misma carpeta arranque con `gunicorn`
y el `if __name__ == "__main__"` use `app.run(debug=True)` es la peor combinación
posible: **el archivo funciona distinto según cómo se arranque**, y el modo inseguro
es el que se copia y pega.

**Corrección:** un servidor ASGI/WSGI real, sin debug, detrás de un balanceador o un
servicio gestionado, y el grupo de seguridad abierto solo a lo que necesita entrar.
Ver `CMD ["uvicorn", ...]` en el [`Dockerfile`](../../../Dockerfile) del repositorio, y
la regla `/32` de la demo del paso 04.

### 2. `pickle.load` a nivel de módulo, de un binario que se descarga

[`predict.py`, líneas 14-16](predict.py):

```python
with open('lin_reg.bin', 'rb') as f_in:
    (dv, model) = pickle.load(f_in)
```

**Pregunta para la clase: ¿qué código se ejecuta al deserializar ese archivo?**

Respuesta: cualquiera. `pickle` no es un formato de datos, es un lenguaje de
serialización con opcodes; `REDUCE` invoca un callable con argumentos que vienen del
propio archivo. Deserializar un pickle equivale a ejecutar un script que alguien te
mandó. La documentación de Python lo dice sin rodeos: *"The pickle module is not
secure. Only unpickle data you trust."*

Dónde importa aquí: el archivo `lin_reg.bin` **no está en el repositorio**. Según la
guía, aparece por un `git clone` o se copia a mano. Nadie puede decir qué lo produjo,
con qué versiones ni si es el que se validó. Y como el `pickle.load` está a nivel de
módulo, se ejecuta **al importar**, antes de que exista un solo endpoint: no hay
forma de aislarlo ni de fallar limpiamente.

Segundo problema del mismo bloque: un `except` no existe. Si el archivo falta o está
corrupto, el proceso muere en el import con un traceback, y en un orquestador eso es
un contenedor que reinicia en bucle sin diagnóstico.

**Corrección:** resolver el modelo del Model Registry por alias
(`models:/nyc-taxi-duration@champion`), que da versión, run de origen y linaje, y
cargarlo dentro de un ciclo de vida que pueda arrancar degradado. Cuando el riesgo
de `pickle` no sea aceptable (artefactos de terceros), un formato sin ejecución de
código: ONNX, `skops`, o el formato nativo de XGBoost/LightGBM.

### 3. Sin validación de entrada

[`predict.py`, líneas 54-56](predict.py):

```python
ride = request.get_json()
features = prepare_features(ride)
```

`request.get_json()` devuelve lo que mandó el cliente. Si falta `trip_distance`, es
un `KeyError` que Flask convierte en 500. Si viene `-40`, el modelo predice una
duración negativa y el cliente la consume como válida. Si viene `PULocationID:
99999`, el `DictVectorizer` genera una categoría que el modelo nunca vio y la
predicción es ruido con formato de número.

Ninguno de esos tres casos produce un error. El peor es el segundo: **una respuesta
200 con un valor sin sentido** es indistinguible de una respuesta correcta para quien
la consume.

**Corrección:** un contrato ejecutable en la frontera. Ver
[`schemas.py`](../../../src/taxi/api/schemas.py): rangos, `extra="forbid"` y 422 con
el detalle de qué campo está mal.

### 4. Sin `/health` y sin `/metrics`

El servicio tiene un único endpoint: `POST /predict`. No hay forma de preguntarle si
está vivo sin mandarle una predicción, ni de saber qué versión de modelo está
sirviendo, ni de medir latencia o tasa de error.

Consecuencias concretas: un balanceador no puede decidir si sacarlo de rotación; un
orquestador no puede decidir si reiniciarlo; y cuando alguien diga "está lento", la
respuesta será una opinión.

**Corrección:** `/health` (liveness, con `model_loaded` para readiness), `/modelo`
(qué está respondiendo) y `/metrics`. Ver
[`api-contract.md`](../../s05-deployment/api-contract.md).

### 5. La respuesta no dice qué modelo la produjo

```python
result = {'duration': pred}
```

Tres semanas después, ante un reclamo, esa respuesta no permite reconstruir qué
artefacto la generó. No hay `model_name`, ni `model_version`, ni un id de
correlación. Sin eso no hay auditoría, y sin auditoría un rollback es una apuesta.

**Corrección:** `model_name` + `model_version` en cada respuesta, resueltos del
registry en el arranque.

### 6. El modelo viaja dentro de la imagen sin linaje, y la imagen corre como root

[`Dockerfile`](Dockerfile):

```dockerfile
COPY [ "predict.py", "lin_reg.bin", "./" ]
```

Dos problemas independientes:

- **El artefacto entra a la imagen sin que nadie sepa qué es.** `lin_reg.bin` es un
  archivo que estaba en el directorio; no hay versión, no hay run de origen, no hay
  forma de saber si es el que se validó. Compáralo con la demo del paso 04, que también
  mete el modelo en la imagen: lo exporta del registry **por alias**, escribe la versión
  como etiqueta de la imagen y documenta qué se pierde a cambio. La diferencia no es
  dónde está el archivo, es si se sabe cuál es.
- **No hay `USER`.** El proceso corre como root dentro del contenedor. Sumado al
  defecto 1, un atacante que llegue a la consola de Werkzeug la tiene con
  privilegios.

Menor pero real: `RUN pip install -U pip` y `RUN pip install uv` en dos capas
separadas, y `uv pip install --system -e .` sin lockfile, así que la imagen instala
lo que PyPI tenga ese día.

**Corrección:** el modelo se resuelve del registry en el arranque (o se exporta de él
con su versión), `USER` sin privilegios, y `uv sync --locked`. Ver el
[`Dockerfile`](../../../Dockerfile) del repositorio.

---

## Bonus: `test.py` no es un test

```python
response = requests.post(url, json=ride)
print(response.json())
```

Imprime. No afirma nada, así que no puede fallar; un CI que lo ejecute estará siempre
verde. Es un `curl` escrito en Python.

Un test necesita una aserción y, si es de la API, no debería requerir que el
servicio esté levantado en `localhost:9696`. Ver [`tests/api/`](../../../tests/api/):
mismo propósito, con `TestClient` y un doble de prueba, corriendo sin red.

---

## Ejercicio de la sesión (bloque de seguridad, 12 min)

En parejas, sin mirar este README:

1. Abran `predict.py`, `Dockerfile` y `guia-despliegue-ec2.md`.
2. Escriban una lista de todo lo que expondría este despliegue a internet.
3. Ordenen la lista por **gravedad**, no por facilidad de arreglo.
4. Para el primero de la lista, escriban el comando o la línea de código que lo
   corrige.

Después se compara con las seis secciones de arriba. La pregunta de cierre: **¿cuál
de estos defectos habría detectado el CI de este repositorio, y cuál no?**
(`gitleaks` no ve ninguno; `ruff` tampoco. El del usuario root **sí** lo detecta el
job `imagen`. Los otros cinco requieren revisión humana o herramientas de análisis
estático de seguridad, y eso es el argumento para tener una lista de verificación de
despliegue.)
