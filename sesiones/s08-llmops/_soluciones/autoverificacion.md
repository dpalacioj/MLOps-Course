# Soluciones — Autoverificación de la sesión 8

> **No publicar antes del taller.**

Las cinco preguntas del [README](../README.md#autoverificación), con la respuesta
completa y con lo que se busca al preguntarlas.

---

## 1. La app clasificó una queja como `app` cuando debía ser `tarifa`. ¿Qué miras en la traza, y en qué orden?

**Respuesta.** Se recorren los spans de fuera hacia dentro:

1. **`clasificar_queja` (CHAIN)** — los tags primero: `intentos`, `prompt`,
   `huella_prompt`, `modelo`, `proveedor`. Antes de depurar hay que confirmar **qué
   se estaba ejecutando**. Si `prompt` dice `v1` y creías estar corriendo `v2`, ya
   está la respuesta y no hace falta seguir. Si `proveedor` dice `fake`, tampoco hay
   nada que depurar: no se llamó a ningún modelo.
2. **`llamar_modelo` (LLM)** — el **input**: el prompt de sistema renderizado. Aquí
   se ve si quedó un `{{...}}` sin sustituir, si la queja llegó truncada, o si el
   prompt no es el que se creía. Y el **output**: el texto crudo del modelo.
3. **`parsear_salida` (PARSER)** — si este span tiene éxito, el parseo no es el
   problema.

**El razonamiento que separa las tres causas:**

| Observación | Causa |
|---|---|
| `parsear_salida` falla, `llamar_modelo` no | El **prompt**: el modelo no entendió el formato pedido |
| Los dos tienen éxito y la categoría es igual en el output crudo y en el resultado | El **modelo**: respondió `app` de verdad |
| El output crudo dice `tarifa` y el resultado dice `app` | El **parseo** (o algo después). Poco probable con validación estricta, y es justo el escenario que la validación estricta convierte en imposible-silencioso. |

En este caso concreto —una categoría equivocada pero válida— casi siempre es el
modelo o el prompt, y los distingue leer el prompt renderizado: si la rúbrica de
desempate que aplicaría a esa queja no está en el prompt, es el prompt.

**Qué se evalúa.** Que se mire **primero** qué se estaba ejecutando (los tags) y no
directamente el contenido. Es el error de depuración más común: empezar a leer el
prompt del repositorio en lugar del prompt que la traza dice que se envió.

---

## 2. Tu juez reporta que el 91% de los resúmenes son buenos. ¿Qué número necesitas antes de publicarlo?

**Respuesta.** El **kappa de Cohen** del juez contra una muestra etiquetada por
humanos, con el **n** al lado. Sin eso, el 91% mide la propensión del juez a aprobar,
no la calidad del sistema.

Si el kappa es **0.3**, está por debajo del corte de 0.40 y el 91% **no se reporta**.
Y hay **dos** acciones distintas según hacia dónde se equivoque el juez —esta es la
parte de la pregunta que la mayoría se salta:

| Diagnóstico | Qué significa | Qué hacer |
|---|---|---|
| **Más permisivo** que el humano (aprueba lo que el humano rechaza) | La rúbrica es demasiado laxa, o el juez no la está aplicando | Endurecer los criterios, añadir los casos límite que el juez aprueba mal, o cambiar a un modelo juez más capaz |
| **Más estricto** que el humano (rechaza lo que el humano aprueba) | La rúbrica es demasiado dura, o hay un criterio ambiguo | Revisar los casos rechazados: normalmente hay un criterio que el humano interpreta con más flexibilidad de lo que está escrito |

`Acuerdo.sesgo_del_juez` da ese diagnóstico.

**Y la respuesta completa incluye una tercera cosa:** mirar si los desacuerdos se
**concentran en un criterio** (`ResultadoCalibracion.punto_ciego`). Si los 4
desacuerdos son del criterio de fidelidad, el juez tiene un punto ciego sistemático y
**más casos de calibración no lo arreglan**: hace falta otro juez o otro método para
ese criterio. Es el caso de `JuezFake` en este repo.

**Qué se evalúa.** Que no se conteste solo "kappa". El número dice si el juez sirve;
la dirección y la concentración del desacuerdo dicen **qué hacer**, que es lo
accionable.

---

## 3. Alguien propone reemplazar `categoria_correcta` por un juez que evalúe "si la categoría es razonable". Dos razones para rechazarlo.

**Respuesta.**

1. **Mide otra cosa.** `categoria_correcta` mide el acuerdo con **la decisión del
   negocio**, escrita en `rubricas/severidad.md` y en las etiquetas del dataset. Un
   juez mide si la categoría es *defendible*. Son distintas: en `q031` (esperó, el
   conductor no llegó, y le cobraron) tanto `tarifa` como `tiempo_de_espera` son
   perfectamente razonables, y el negocio decidió `tarifa`. Un juez aprobaría las
   dos, y el eval dejaría de detectar que el sistema enruta el ticket al equipo
   equivocado.
2. **Es peor en todos los ejes medibles.** Más caro (una llamada por caso), más
   lento, con varianza entre ejecuciones, y necesita su propia calibración para que
   su resultado signifique algo. A cambio de nada: el `==` ya da la respuesta exacta.

Una tercera, si se quiere: **destruye la línea base**. Con `==` se puede comparar el
LLM contra `clasificar_por_reglas`. Con un juez, la comparación depende del juez.

**Cuándo sí tendría sentido.** Cuando **no hay etiquetas**: sobre tráfico de
producción no existe verdad de terreno, y un juez que estime la plausibilidad de la
categoría es una señal de monitoreo útil (un descenso indica un problema) aunque no
sea una medida de exactitud. Es un caso de uso distinto —**monitoreo, no eval**— y es
la respuesta que distingue a quien entendió la separación entre
`SCORERS_DE_CONTRATO` y `SCORERS_DE_EXACTITUD`.

---

## 4. El prompt v2 sube la exactitud de 0.69 a 0.94 y es tres veces más largo. ¿Qué calculas antes de promoverlo?

**Respuesta, dos partes.**

### El costo, y con el volumen real

El prompt de sistema se envía **en cada llamada**, así que un prompt 3 veces más
largo es ~3 veces más caro por request, **para siempre**. Lo que hay que calcular:

```
costo_mensual = requests_por_mes * costo_por_request
```

Y ponerlo al lado de lo que aporta el 0.94. Si el sistema procesa 100 quejas al día,
la diferencia es de céntimos y no hay discusión. Si procesa un millón, la
conversación es otra. **El mismo delta de calidad justifica o no justifica el cambio
según el volumen**, y sin el número no se puede decidir.

Hay que mirar además: **latencia** (un prompt más largo tarda algo más de procesar) y
si aplica **cache de prompts** (con un prefijo de sistema fijo y largo, el descuento
es sustancial y cambia el cálculo).

### La pregunta a quien escribió el prompt

**"¿Cuántas veces corriste el eval mientras escribías el prompt?"**

Si la respuesta es "muchas, iterando hasta que subiera", ese 0.94 está **sobreajustado
al dataset de evals** y no va a replicarse en producción. Es exactamente tunear contra
`PARTICION_TEST`. Un salto de 0.69 a 0.94 en 36 casos es sospechosamente grande —son
9 casos— y la explicación más probable es iteración contra el holdout.

Lo correcto: un conjunto de desarrollo aparte para iterar, y el de evals tocado lo
mínimo.

**Qué se evalúa.** Las dos partes. La primera es la respuesta esperada; la segunda
distingue a quien interiorizó la disciplina del holdout de las sesiones 3 y 6. (Y el
`ProveedorFake` de este repo comete ese pecado a propósito y lo declara: sus reglas
finas se escribieron mirando los 36 casos.)

---

## 5. Un mes en producción sin cambios y los usuarios dicen que responde peor. Tres causas, y qué dato las distingue.

**Respuesta.**

1. **Drift de entrada.** Los usuarios escriben distinto: una promoción nueva generó un
   tipo de queja que no existía, la app cambió y aparecieron reclamos de una pantalla
   nueva, entró tráfico de otra ciudad con otro vocabulario. Es el drift de la
   [sesión 7](../../s07-monitoreo/), sobre texto en lugar de features numéricas.
2. **El proveedor cambió el modelo detrás del mismo alias.** `gpt-4o-mini` no es un
   artefacto inmutable: es un nombre que apunta a lo que el proveedor decida. Puede
   cambiar sin aviso y sin cambiar el nombre.
3. **Un fallback del gateway enrutó a otro modelo.** Hubo un incidente de
   disponibilidad hace tres días, el router mandó el tráfico al secundario, y las
   salidas cambiaron de distribución. La causa está en un incidente que ya se cerró.

Una cuarta, válida: **cambió algo aguas abajo** —el consumidor del `resumen` cambió su
UI y ahora 20 palabras se ven truncadas. El sistema responde igual y la experiencia
empeoró.

### El dato que las distingue

**El campo `modelo` de la traza** — y específicamente que guarde **lo que el proveedor
devolvió, no lo que se pidió**. Es la razón de este detalle en `ProveedorOpenAI`:

```python
modelo = (getattr(respuesta, "model", self.modelo),)
```

Con ese dato:

- Si `modelo` **cambió** en algún punto del mes → causas 2 o 3. Se distinguen mirando
  si el cambio coincide con un incidente (fallback) o es permanente (el proveedor
  actualizó el modelo).
- Si `modelo` es **constante** → causa 1 o 4. Se distinguen comparando la
  **distribución de las entradas** del mes contra la del mes anterior: si cambió, es
  drift de entrada.

Y en los dos casos, los **scorers de contrato sobre tráfico de producción**
(`json_valido`, `intentos_promedio`, `resumen_dentro_del_limite`) dan la serie
temporal para localizar **cuándo** empezó, que es lo que permite correlacionarlo con
un evento.

**Qué se evalúa.** Esta pregunta integra la sesión entera: instrumentación (bloque 4),
la distinción contrato/exactitud (bloque 8), el riesgo del fallback silencioso
(bloque 11) y el drift (sesión 7). Si se responde bien, la sesión quedó.

**Y la lección de fondo:** en ML clásico "no cambié nada" es una afirmación razonable
sobre el sistema. Aquí no lo es, porque parte del sistema es de otra empresa. Por eso
la estrategia pasa de **reproducir** a **evidenciar**: no se puede garantizar que el
sistema haga lo mismo, así que hay que poder demostrar qué hizo.
