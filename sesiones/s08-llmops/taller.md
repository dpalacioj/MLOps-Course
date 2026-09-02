# Taller — Sesión 8: LLMOps

**Entrega:** un PR desde tu fork, con el CI verde.
**Tiempo estimado:** 55 min en clase para el núcleo, el resto como trabajo autónomo.
**Requisitos:** ninguna API key. Todo el taller se completa con `ProveedorFake`.

El taller no te pide construir el sistema desde cero: eso no cabe en cuatro horas y
no es el objetivo. Te pide **añadir una pieza a cada capa** y demostrar que la
pieza funciona. Es el patrón de trabajo real: nadie escribe un sistema de evals de
golpe; se le añade un scorer cada vez que algo falla.

---

## Criterios de aceptación

El PR se acepta si cumple **los cinco**. Cada uno es verificable con un comando o
mirando un archivo: no hay criterios de "se ve bien".

| # | Criterio | Cómo se verifica |
|---|---|---|
| **1** | **Las trazas son navegables.** Existe al menos una traza de tu código nuevo con spans anidados, y puedes señalar en cuál se produce un fallo que provocaste a propósito. | Captura de la UI de MLflow en el PR, o la salida de `mlflow.search_traces()`. Debe verse el span de tu scorer o de tu paso nuevo. |
| **2** | **El eval corre por comando y en CI.** `python -m clasificador.evaluar` termina con exit 0, y el workflow `evals-llm.yml` está verde en tu PR. | `make evals-llm; echo $?` y el check del PR. |
| **3** | **Hay dos versiones de prompt con resultados comparables.** Tu prompt `v3` está en `prompts/`, registrado en `VERSIONES_LOCALES`, y aparece en una tabla comparativa contra `v2` con el delta de cada métrica. | `python -m clasificador.comparar_prompts --base v2 --candidato v3` y el reporte generado. |
| **4** | **El juez tiene rúbrica escrita y se reporta su acuerdo con ≥10 casos etiquetados a mano.** Tu criterio nuevo está en un archivo de `rubricas/`, y hay al menos 10 casos con veredicto humano en `datos/`. | `pytest sesiones/s08-llmops/tests` incluye tu test de calibración, y el eval imprime el kappa. |
| **5** | **Todo verde.** `ruff`, `mypy`, y los tests (los existentes **más** los tuyos) pasan. | `make check` y `make test-llmops`. |

**Regla dura sobre el criterio 4:** si tu juez tiene kappa < 0.40, el PR **sigue
siendo válido** — siempre que lo reportes y expliques hacia dónde se equivoca. Lo
que no se acepta es reportar el resultado del juez sin su kappa. Un kappa bajo bien
diagnosticado es un buen entregable; un número sin calibrar no lo es.

---

## Ejercicio 1 — Un scorer determinista nuevo (15 min)

**Escenario.** El equipo de soporte reporta que algunos resúmenes vienen en primera
persona ("Me cobraron dos veces") y su plantilla de respuesta asume tercera persona,
lo que produce mensajes incoherentes al usuario.

**Qué hacer.**

1. Escribe `resumen_en_tercera_persona(resultado) -> Puntaje` en
   `scorers/deterministas.py`.
2. Añádelo a `puntuar()` y a `SCORERS_DE_CONTRATO`.
3. Escribe **dos** tests: uno que apruebe un resumen en tercera persona y otro que
   rechace uno en primera.

**Qué se está evaluando de ti.** Que el scorer devuelva un `motivo` útil, y que el
test del caso negativo exista. Un scorer probado solo con el caso feliz no está
probado: la mitad de los scorers que fallan en producción devuelven 1.0 siempre.

**Pregunta a responder en el PR (2-3 líneas).** ¿Por qué esto es un scorer
determinista y no un criterio para el juez? ¿Y en qué caso concreto tu regla se
equivocaría?

> Pista sobre el diseño: detectar primera persona con precisión perfecta es
> difícil. No hace falta. Declara tu heurística y sus falsos positivos en el
> docstring, como hace `detectar_pii`. Un scorer honesto sobre sus límites vale más
> que uno que finge no tenerlos.

---

## Ejercicio 2 — Un criterio nuevo en la rúbrica del juez (20 min)

**Escenario.** Detectas resúmenes que son fieles pero **omiten el dato accionable**:
"El usuario reporta un cobro incorrecto" cuando la queja dice un monto concreto. El
agente de soporte tiene que abrir la queja original para hacer su trabajo, y el
resumen no le ahorró nada.

**Qué hacer.**

1. Añade el criterio **5** a `rubricas/juez-resumen.md`. Escríbelo con el mismo
   nivel de detalle que los cuatro existentes, **incluyendo al menos dos casos
   límite resueltos de antemano**.
2. Añade al menos **3 casos nuevos** a `datos/calibracion-juez.jsonl` que ejerciten
   el criterio nuevo, etiquetados por ti a mano. Rellena el campo `notas` con el
   razonamiento.
3. Corre `calibrar(JuezFake())` y mira qué pasa con el kappa y con el punto ciego.
4. Escribe un test que afirme algo sobre la calibración resultante.

**Qué se está evaluando de ti.** Que resuelvas los casos límite **antes** de medir.
Si defines el criterio después de ver los desacuerdos, estás ajustando la rúbrica al
resultado, y eso invalida la calibración. Es el mismo pecado que tunear contra el
holdout.

**Preguntas a responder en el PR.**
- ¿Tu kappa subió o bajó? ¿Por qué? (Bajar es un resultado perfectamente
  respetable: significa que añadiste casos que el juez no puede resolver.)
- ¿El punto ciego cambió de criterio?
- Con tu kappa actual, ¿usarías este juez como gate? Justifica con el número.

---

## Ejercicio 3 — Un prompt v3 y su comparación (20 min)

**Qué hacer.**

1. Crea `prompts/v3-<lo-que-cambias>.txt`. Parte de `v2` y hazle **un cambio con
   una hipótesis detrás**. Ejemplos con hipótesis explícita:
   - quitar los ejemplos → *hipótesis: la rúbrica basta y ahorra ~40% de tokens*;
   - quitar la rúbrica de severidad y dejar solo los ejemplos → *hipótesis: los
     ejemplos enseñan la escala mejor que la descripción*;
   - añadir el criterio de tercera persona del ejercicio 1 → *hipótesis: mejora ese
     scorer sin degradar los demás*.
2. Regístralo en `prompts.VERSIONES_LOCALES`.
3. Corre `python -m clasificador.comparar_prompts --base v2 --candidato v3`.
4. Incluye la tabla comparativa en la descripción del PR.

**Qué se está evaluando de ti.** Que **declares la hipótesis antes de medir**, y que
reportes las métricas que **empeoraron** además de las que mejoraron. Un PR que solo
muestra los deltas positivos no es un experimento: es marketing.

Si tu `v3` no mejora nada, dilo y explica por qué crees que pasó. **Un resultado
negativo bien documentado es un entregable completo.** Es, de hecho, la mayoría de
los resultados reales.

> Recuerda el aviso del README: `ProveedorFake` **simula** sensibilidad al prompt.
> Solo reacciona al marcador `MARCADOR_RUBRICA`. Es probable que tu `v3` puntúe
> igual que `v2` en modo fake. Eso **no es un fallo de tu prompt**: es una
> limitación del fake, y decirlo en el PR es parte de la respuesta correcta. Si
> tienes acceso a un modelo real, corre la comparación también con él y compara las
> dos conclusiones.

---

## Ejercicio 4 — Provocar un fallo y depurarlo con la traza (10 min)

Este ejercicio no produce código: produce entendimiento. Es el que más se salta y
el que más sirve.

**Qué hacer.**

1. Activa el tracing local:
   ```bash
   export PYTHONPATH=sesiones/s08-llmops/src
   export LLMOPS_TRACING=local
   ```
2. Rompe algo **a propósito**. Elige uno:
   - quita una variable del contexto en `prompts.contexto_por_defecto()`;
   - cambia `MAX_PALABRAS_RESUMEN` a 3;
   - usa `ProveedorEco` en lugar de `ProveedorFake`;
   - añade un valor al enum `Categoria` sin tocar el prompt.
3. Corre el eval y **mira la traza antes de mirar el código**.
4. Documenta en el PR: qué rompiste, **en qué span se vio**, y qué te habría costado
   averiguarlo sin trazas.

**Qué se está evaluando de ti.** Que puedas ir del síntoma al span y del span a la
causa. La respuesta interesante es la última parte: *cuánto habría costado sin
trazas*. Ese es el argumento con el que se justifica el trabajo de instrumentar.

---

## Ejercicio 5 (opcional) — Ampliar el dataset de evals

El trabajo menos glamoroso y el de mayor retorno.

Añade **5 casos nuevos** a `datos/quejas.jsonl` que ejerciten algo que el dataset
actual no cubre. Ideas:

- una queja en un registro muy informal, con abreviaturas y sin puntuación;
- una queja que mezcle dos motivos de forma genuinamente ambigua;
- una queja muy corta ("mal servicio");
- una queja larguísima con el motivo real enterrado al final;
- una queja en la que el usuario cita textualmente al conductor.

Requisitos: `notas` explicando el criterio, y que `pytest` siga verde (los tests
validan el dataset entero).

**Y luego corre el eval otra vez.** Si tus 5 casos bajan las métricas, eso **no es
un problema**: significa que encontraste casos que el sistema no maneja, que es
exactamente para lo que sirve ampliar un dataset de evals. Repórtalo así.

---

## Lo que NO hay que hacer

Anti-patrones que aparecen en las entregas, con el motivo:

- **Iterar el prompt mirando los 36 casos hasta que suban los números.** Eso es
  sobreajuste al holdout, el mismo pecado que tunear contra `PARTICION_TEST`. Si
  necesitas iterar, separa un conjunto de desarrollo y dilo. (El
  `ProveedorFake` de este repo comete este pecado a propósito y lo declara en el
  código; no lo copies.)
- **Reportar el resultado del juez sin el kappa.** Es el único criterio que rechaza
  el PR de forma automática.
- **Añadir un scorer que devuelve 1.0 siempre.** Sube la media y no mide nada.
- **Añadir un juez de LLM para algo que se mide con `==`.** Más caro, más lento, con
  varianza.
- **Subir una API key**, ni siquiera en un comentario, ni con formato de ejemplo.
  `gitleaks` corre en el CI y va a fallar.
- **Bajar un umbral para que el gate pase.** Si el gate se pone rojo, el gate
  funcionó. Bajar el umbral para que pase es desactivar el gate manteniendo la
  apariencia de tenerlo. Si crees que el umbral está mal, argumenta el cambio
  aparte, con los números.

---

## Cómo se ve un PR completo

```markdown
## Ejercicio 1 — scorer resumen_en_tercera_persona
Heurística: detecta pronombres y verbos de primera persona al inicio.
Falso positivo conocido: una cita textual del usuario dentro del resumen.
Es determinista y no criterio del juez porque tiene respuesta verificable.
Tests: test_tercera_persona_aprueba / test_primera_persona_rechaza.

## Ejercicio 2 — criterio 5: dato accionable
3 casos nuevos en calibracion-juez.jsonl (c16-c18).
Kappa: 0.35 -> 0.28 (BAJÓ). Causa: los 3 casos nuevos requieren juzgar si un
dato es accionable, algo que un juez por reglas no puede hacer. El punto ciego
sigue siendo "1 fidelidad" pero ahora con 6 de 8 desacuerdos.
No usaría este juez como gate: kappa 0.28 está bajo el corte de 0.40.

## Ejercicio 3 — prompt v3-sin-ejemplos
Hipótesis: la rúbrica basta; quitar los 3 ejemplos ahorra ~35% de tokens.
Resultado en modo fake: SIN CAMBIO en todas las métricas. Esperado: el fake
solo reacciona a MARCADOR_RUBRICA, que v3 conserva. La comparación no es
concluyente sin un modelo real.
| métrica | v2 | v3 | delta |
|---|---|---|---|
| categoria_correcta | 0.944 | 0.944 | +0.000 |

## Ejercicio 4 — fallo provocado
Cambié MAX_PALABRAS_RESUMEN a 3. Se vio en el span `parsear_salida`, no en
`llamar_modelo`: el modelo respondía bien y el contrato lo rechazaba. Sin
trazas habría empezado buscando en el prompt, que es donde no estaba.
```

Nota lo que tiene ese PR: dos resultados negativos, una limitación del entorno
reconocida, y un falso positivo declarado. Es un buen PR.
