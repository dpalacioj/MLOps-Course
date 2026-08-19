# Costos: por qué en LLMOps suben de prioridad

## El cambio de régimen

En ML clásico el costo de inferencia es casi invisible. El modelo está cargado en
memoria y una predicción más no cambia la factura; lo que cuesta es la máquina,
y cuesta lo mismo con 100 o con 100.000 predicciones. Por eso el costo aparece al
final de la lista de preocupaciones, si aparece.

Con un LLM el costo es **por request y proporcional al texto**. Eso cambia cuatro
cosas de forma cualitativa, no solo de grado:

1. **Escala lineal, sin amortización.** Mil requests cuestan mil veces uno. No hay
   punto en el que el costo marginal caiga a cero.
2. **Decisiones de diseño que parecen inocuas mueven la factura.** Agregar tres
   ejemplos al prompt de sistema encarece **todas** las llamadas, para siempre.
3. **Los reintentos duplican el costo de ese caso.** Un bucle de reintentos sin
   tope es una factura sin tope.
4. **El eval también cuesta.** Y se corre en cada PR.

La consecuencia práctica es que el costo pasa de ser un tema de infraestructura a
ser una **métrica de ingeniería**, al lado de la latencia y la calidad. Un cambio
de prompt que mejora la exactitud un 3% y triplica el costo por request es una
decisión de negocio, no un merge automático.

## Cómo se estima el costo de un request

Los proveedores cobran por token, con precios distintos para entrada y salida:

```
costo = (tokens_entrada / 1e6) * precio_entrada + (tokens_salida / 1e6) * precio_salida
```

Tres cosas que sorprenden la primera vez:

**La salida es varias veces más cara por token que la entrada.** En este caso de
uso eso importa poco porque la salida es un JSON corto; en un caso que genera
texto largo, domina la factura.

**En una tarea de clasificación, la entrada domina.** Y dentro de la entrada, el
prompt de sistema domina sobre la queja del usuario. Medido en este proyecto:

| Componente | Tokens (estimados) |
|---|---|
| Prompt de sistema `v1-minimo.txt` | ~85 |
| Prompt de sistema `v2-rubrica.txt` | ~958 |
| Queja del usuario (media del dataset) | ~21 |
| Salida JSON | ~35 |

> Estimados con la heurística de 4 caracteres por token, porque `tiktoken` es
> parte del extra opcional `llmops`. Para facturar se usan los tokens que devuelve
> el proveedor en `usage`, no una estimación (ver `proveedor.contar_tokens`).

**Ese es el número que hay que ver:** el prompt de sistema de `v2` es **más de 40
veces** la queja que se quiere clasificar. La rúbrica se envía completa en cada
llamada, y por tanto se paga completa en cada llamada. Pasar de `v1` a `v2`
multiplica el costo por request por ~10.

Eso no significa que `v2` sea la decisión equivocada: sube la exactitud de
categoría de 0.69 a 0.94 (con la advertencia sobre el modo fake del README).
Significa que **es una decisión con un número a los dos lados**, y sin medir el
costo solo se ve un lado.

### Lo que la estimación NO incluye

Presentar el costo de tokens como el costo del sistema es la subestimación más
común. Falta:

- **El juez.** Un eval con LLM-as-judge hace una llamada extra por caso, a un
  modelo típicamente más grande. Puede costar más que el sistema evaluado. Por eso
  `costo_de_resultados` contabiliza al juez con la misma función que al
  clasificador, y `evaluar.py` suma los dos.
- **Embeddings y base vectorial**, si hay retrieval.
- **Almacenamiento de trazas.** Cada traza guarda el prompt completo y la
  respuesta. Con tráfico real no es despreciable, y tiene además implicaciones de
  retención (ver [`riesgos.md`](riesgos.md)).
- **Reintentos por rate limit**, que no aparecen en el código de la app.
- **El tiempo de las personas** que revisan salidas y etiquetan datasets. En un
  sistema con humano en el bucle, suele ser la partida más grande.

## La calculadora

[`src/clasificador/costos.py`](src/clasificador/costos.py), con precios en
[`config/precios.yaml`](config/precios.yaml).

```bash
export PYTHONPATH=sesiones/s08-llmops/src
python -c "
from clasificador import costos
tabla = costos.cargar_precios()
# 36 casos, prompt v2: ~1000 tokens de entrada y ~35 de salida por caso
c = costos.calcular_costo(1000, 35, 'gpt-4o-mini', tabla=tabla, requests=36)
print(costos.formatear_costo(c))
"
```

El eval imprime el costo en cada corrida, siempre. Un eval sin su costo al lado
invita a correr el eval más caro posible en cada PR.

### Decisión de diseño: los precios son configuración

Los precios de los modelos **cambian cada pocas semanas**. Hardcodeados en un
`.py`, el resultado es predecible: nadie revisa una constante que ya está ahí, y
la estimación se vuelve falsa en silencio durante meses.

En `config/precios.yaml` con un campo `actualizado`, la calculadora puede
**advertir** cuando los precios llevan más de `vigencia_dias` sin revisarse. Eso es
lo único que evita la cifra plausible y falsa:

```
gpt-4o-mini: 36000 tokens de entrada + 1260 de salida = 0.006156 USD
  [AVISO: los precios de config/precios.yaml estan fuera de vigencia]
```

Los valores del YAML son **placeholders plausibles con fines didácticos, no una
lista de precios vigente**. Antes de usar la calculadora para decidir algo: abrir
la página de precios del proveedor, actualizar el archivo, anotar la fecha.

Dos detalles del diseño que valen como patrón general:

- **Un modelo desconocido se estima con el más caro**, no con cero. Una estimación
  de costos debe equivocarse **hacia arriba**. Un precio cero produce un reporte
  que dice que el sistema es gratis, y esa es la peor forma de equivocarse: la que
  tranquiliza.
- **El fake cuesta cero, y aparece en la tabla.** Costo cero es la señal más clara
  de que no se midió el sistema real.

## Palancas para bajar el costo, en orden de rentabilidad

| Palanca | Efecto | Coste de la palanca |
|---|---|---|
| **Modelo más pequeño** | El más grande, con diferencia. Órdenes de magnitud entre un modelo pequeño y uno grande. | Hay que medir la calidad con el eval. Para clasificación con salida estructurada, el pequeño suele bastar. |
| **Acortar el prompt de sistema** | Proporcional y permanente, porque se paga en cada llamada. | Hay que verificar con el eval que la calidad no cae. Aquí es el trade-off `v1` vs `v2`. |
| **Cache de prompts** | Los proveedores descuentan el prefijo repetido del prompt. Con un prompt de sistema fijo y largo, el ahorro es grande. | Requiere que el prefijo sea estable byte a byte. Un timestamp en el prompt lo invalida entero. |
| **Reducir reintentos** | Cada reintento es una llamada completa. La métrica `intentos_promedio` del eval es la que hay que mirar. | Suele lograrse mejorando el prompt o usando salida estructurada nativa. |
| **Batching / procesamiento asíncrono** | Descuentos significativos en las APIs de batch. | Solo si la tarea tolera latencia de horas. Un clasificador de tickets sí; un chat no. |
| **Rechazar entradas absurdamente largas** | Evita el caso patológico. | Una línea de código: estimar tokens **antes** de llamar. Es para lo que sirve `contar_tokens`. |
| **No llamar al LLM** | El ahorro máximo. | Comparar contra la línea base por reglas. Si empatan, el LLM cuesta dinero por nada. |

La última merece énfasis. `proveedor.clasificar_por_reglas` es la línea base, el
equivalente al `DummyRegressor` de la sesión 3. Se omite mucho más de lo que se
debería, y es la comparación que decide si el proyecto tiene sentido.

## Control de costos, no solo estimación

Estimar es saber cuánto va a costar. Controlar es garantizar que no cueste más.
Son dos cosas distintas y la segunda necesita infraestructura:

- **Budget por clave**, en el gateway. Con tope, el peor caso de un bug es el tope.
  Sin tope, el peor caso es ilimitado. Ver
  [`gateway/README.md`](gateway/README.md).
- **Alertas al 80% del presupuesto.** Un budget que solo avisa cuando ya cortó el
  servicio no es un control de costos: es un incidente programado.
- **Atribución por usuario o equipo**, para que "gastamos 3.000 USD" venga con un
  desglose.

En el curso: una clave virtual con 5 USD por estudiante. Un estudiante que deja un
bucle corriendo gasta sus 5 USD, no el presupuesto del curso, y la clave real del
proveedor nunca sale del gateway.

## Latencia, que va en el mismo paquete

El costo y la latencia suben de prioridad juntos y por la misma razón: los dos
dependen del texto y de un tercero.

- **Milisegundos → segundos.** Un modelo tabular predice en microsegundos; un LLM
  tarda segundos, y la varianza entre p50 y p99 es grande.
- **La latencia crece con los tokens de salida**, porque se generan uno a uno.
  Limitar la longitud de la salida es una palanca de latencia y de costo a la vez.
  El límite de 20 palabras del resumen es también eso.
- **Cada reintento suma una llamada completa** al tiempo de respuesta.
- **Un timeout es obligatorio.** Sin él, un LLM lento es indistinguible de uno
  caído. El default del SDK es generoso para un servicio interactivo; por eso
  `ProveedorOpenAI` fija 30 s.
- **El streaming mejora la latencia percibida, no la total.** Sirve para un chat.
  Para un clasificador cuya salida consume otro sistema, no aporta: el consumidor
  necesita el JSON completo para poder parsearlo.

Y una consecuencia operativa que se olvida: **el gateway agrega un salto de red**.
Suele ser pequeño frente al tiempo del modelo, pero si el presupuesto de latencia
ya está justo, hay que medirlo antes de asumirlo.
