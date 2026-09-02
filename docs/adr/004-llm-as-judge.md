# ADR 004 — LLM-as-judge: rúbrica externa y calibración obligatoria

- **Estado:** aceptada
- **Fecha:** 2026-08
- **Alcance:** sesión 8, `sesiones/s08-llmops/src/clasificador/scorers/`, `.github/workflows/evals-llm.yml`
- **Decisores:** equipo docente del curso de MLOps
- **Relacionada:** [ADR 002](002-aliases-en-vez-de-stages.md) (aliases y gates), [ADR 001](001-caso-guia-y-particiones.md) (holdout fijo)

## Contexto

La sesión 8 necesita evaluar la calidad de una salida generada por un LLM. Parte de
esa salida es verificable (`categoria`, `severidad`, `requiere_reembolso` tienen una
etiqueta humana) y parte no: el campo `resumen` no tiene una única redacción
correcta, así que no se puede comparar con una cadena de referencia.

Para esa parte hay que usar un juez. El problema es **cómo**, porque la forma
habitual está mal.

### El anti-patrón que se quiere evitar

El flujo que se ve en la mayoría de los tutoriales y de los proyectos reales:

```python
# Anti-patrón
prompt_juez = "Evalúa de 1 a 5 la calidad de este resumen. Responde solo el número."
puntajes = [int(llm(prompt_juez + resumen)) for resumen in resumenes]
print(f"Calidad media: {mean(puntajes):.2f}")  # -> 4.31
```

Ese 4.31 tiene cuatro problemas, y ninguno es visible mirando el número:

1. **Nadie verificó que el juez coincida con un humano.** Si el juez tiende a
   aprobar —el sesgo más común en un juez sin rúbrica— el 4.31 mide la propensión
   del juez a aprobar, no la calidad del sistema.
2. **El criterio no existe en ningún sitio.** "Calidad" no está definida. Dos
   personas que lean el número entienden dos cosas distintas, y nadie puede
   discutir un caso concreto porque no hay contra qué.
3. **La escala de 1 a 5 finge una precisión que no tiene.** El mismo caso saca 3 o
   4 según la temperatura y el orden de los ejemplos. Los humanos tampoco
   distinguen 3 de 4 de forma consistente.
4. **El criterio no se puede versionar.** Está en un f-string. Si cambia, no hay
   diff, no hay review, y los resultados de antes y después del cambio se comparan
   como si fueran comparables.

### Evidencia medida en este proyecto

Se implementó `JuezFake`, un juez por reglas que aplica mecánicamente tres de los
cuatro criterios de la rúbrica y **no puede** aplicar el de fidelidad (detectar un
hecho inventado requiere entender el texto).

Resultados sobre `datos/calibracion-juez.jsonl`:

| Conjunto de calibración | n | Kappa | Lectura según el corte | Punto ciego |
|---|---|---|---|---|
| Versión inicial | 12 | **0.66** | "sustancial: se puede usar como gate" | no detectado |
| Con 3 casos de alucinación añadidos | 15 | **0.35** | "pobre: NO se debe reportar" | 4 de 5 desacuerdos en fidelidad |

**El mismo juez, igual de ciego, con dos veredictos opuestos.** Con 12 casos su
kappa daba vía libre para usarlo como gate; con 15 casos —tres de ellos
alucinaciones fluidas y en tema— quedó descalificado.

Y su tasa de aprobación sobre el eval real es del **100%**: aprueba todos los
resúmenes que produce el sistema. Un número que, presentado solo, sería excelente.

Esta es la evidencia que sostiene toda la decisión: **un juez sin calibrar parece
funcionar**, y una calibración con pocos casos o sin los fallos relevantes puede
avalar un juez inútil.

## Decisión

**Cuatro reglas, las cuatro implementadas en código y no como recomendación.**

### 1. La rúbrica vive en un archivo versionado, nunca en un f-string

`rubricas/juez-resumen.md` es **el artefacto**. `scorers/juez.py` lo lee; si el
archivo no existe, el juez **no corre**:

```python
raise FileNotFoundError(
    f"no existe la rubrica {ruta}. El juez no corre sin rubrica escrita: "
    "es la diferencia entre una metrica y una opinion."
)
```

Consecuencias buscadas: la rúbrica se diffea en un PR, la puede leer un anotador que
no programa, y **el humano y el juez trabajan con el mismo texto**. Si el criterio
del juez y el del anotador divergen, el kappa mide la divergencia de los criterios y
no la del juez, y la calibración deja de significar nada.

### 2. Veredicto binario, no escala numérica

`aprobado` / `rechazado`. Si hace falta granularidad, se añaden **criterios
binarios**, no puntos en una escala.

Una decisión binaria es lo que un juez de LLM hace con fiabilidad razonable, y es lo
que se puede calibrar con kappa. Una escala ordinal necesitaría kappa ponderado y
tendría el ruido de los puntos intermedios, que es el ruido que domina.

### 3. Sin calibración no hay número

`resultado_reportable()` es la única vía del módulo para obtener el resultado del
juez, y exige la calibración como argumento. Si el kappa está bajo el corte, no
devuelve la métrica: devuelve el diagnóstico.

```
NO REPORTABLE — el juez 'juez-fake-reglas' tiene kappa=0.35 sobre n=15 (pobre:
el resultado del juez NO se debe reportar). Su tasa de aprobacion (100%) no es
una metrica de calidad. Diagnostico: el juez es mas permisivo que el humano (4
aprobo lo que el humano rechazo). Arregla la rubrica o cambia el modelo juez
antes de usar este numero.
```

No hay una función pública que devuelva la tasa de aprobación sola. **La vía fácil
es la que se usa**, así que la vía fácil tiene que ser la correcta.

Requisitos y cortes, declarados **antes** de medir:

| Requisito | Valor | Origen |
|---|---|---|
| Casos mínimos etiquetados a mano | 10 | Piso práctico para clase. En producción: 50-200 con intervalo de confianza. |
| Kappa mínimo para reportar | 0.40 | Landis y Koch (1977) — "moderado" |
| Kappa mínimo para usar como gate | 0.60 | Landis y Koch (1977) — "sustancial" |

Los cortes son una **convención**, no un resultado. Lo que importa no es el valor
exacto: es que exista un corte declarado antes de ver el número.

### 4. Kappa no basta: hay que analizar la dirección del desacuerdo

Esta regla sale directamente de la evidencia de arriba y es la aportación menos
obvia de este ADR.

Se calculan y se reportan **cuatro** cosas, no una:

- **Porcentaje de acuerdo** — interpretable pero engañoso con clases desbalanceadas.
- **Kappa de Cohen** — descuenta el azar.
- **Sesgo del juez** (`Acuerdo.sesgo_del_juez`) — ¿es más permisivo o más estricto
  que el humano? Son dos arreglos distintos: permisivo indica rúbrica laxa o juez
  que no la aplica; estricto indica rúbrica demasiado dura.
- **Punto ciego** (`ResultadoCalibracion.punto_ciego`) — ¿los desacuerdos se
  concentran en un criterio? Se advierte cuando ≥2 desacuerdos y ≥60% son del mismo
  criterio, **aunque el kappa pase el corte**.

El punto ciego es lo que kappa no puede decir. Dos jueces con kappa 0.66 son muy
distintos si uno falla al azar y el otro falla siempre en el criterio de fidelidad.
El primero mejora con más casos de calibración; el segundo **no**, y hace falta otro
juez o otro método.

### 5. El juez no participa del gate de CI

Decisión operativa que se sigue de las anteriores. `evaluar.decidir()` solo compara
los scorers deterministas.

Un juez con kappa moderado bloqueando un despliegue es peor que no tener gate:
produce rechazos que nadie sabe interpretar y el equipo aprende a saltarse el gate.
El juez se incorpora al gate cuando su kappa supera el corte, y no antes.

Corolario en el workflow: el paso de calibración del juez está marcado
`continue-on-error: true`, con el motivo escrito en el YAML. `JuezFake` tiene kappa
bajo **por diseño** y eso es la lección, no un fallo del pipeline.

## Alternativas consideradas

| Alternativa | Por qué no se eligió |
|---|---|
| **Solo scorers deterministas, sin juez** | Fue la opción más tentada. Cubre la mayoría de los fallos y no cuesta nada. Se descartó porque deja **sin medir** la fidelidad del resumen, que es el fallo más peligroso (`c04`, `c10`, `c13`-`c15` pasan todos los scorers deterministas). Enseñar evals sin abordar eso sería enseñar una versión incompleta. |
| **`mlflow.genai.make_judge()` + scorers de `mlflow.genai.scorers`** | Es la opción correcta **para producción** y está en el material como tal (`Correctness`, `Guidelines`, `Safety`, `PIIDetection`...). Se descartó como implementación principal por dos razones: hace opaco lo que la sesión quiere enseñar —que un juez es un prompt, un parser y un veredicto—, y requiere credenciales, con lo que el material no correría sin API key. |
| **Ragas / DeepEval** | Mismo argumento, más una dependencia adicional en un extra que ya es opcional. Se citan como alternativas vivas. |
| **Escala de 1 a 5 con kappa ponderado** | Más correcto estadísticamente y peor pedagógicamente: añade la discusión de la ponderación sin añadir nada sobre calibración, que es el punto. |
| **El mismo modelo como generador y juez** | Sesgo de auto-preferencia: un modelo tiende a aprobar su propia salida. Se recomienda explícitamente lo contrario, y `gateway/config.yaml` apunta el juez a otro proveedor. |
| **Calibrar "cuando haya tiempo"** | Es el estado por defecto y equivale a no calibrar nunca. Por eso la calibración es un argumento obligatorio y `_evaluar_juez` calibra **antes** de aplicar el juez: si se aplicara primero, el número ya existiría y la tentación de reportarlo sería demasiado grande. |

## Consecuencias

### Positivas

- El resultado del juez **no puede** reportarse sin su calibración. Es una
  propiedad de la API, no una norma de proceso.
- La rúbrica es un artefacto de Git: revisable, diffeable, citable en una discusión
  sobre un caso concreto.
- El material corre completo sin API key. El CI de un fork está verde el primer día.
- El punto ciego detecta el fallo que kappa no ve, que es el modo de fallo que este
  proyecto midió de verdad.
- Un test (`test_el_juez_fake_no_alcanza_el_kappa_para_ser_gate`) **fija la lección**:
  si alguien "mejora" el juez fake hasta pasar el corte sin resolver la fidelidad, el
  test falla y hay que justificarlo en el PR.

### Negativas y costes aceptados

- **Se mantiene un juez propio** en lugar de usar la biblioteca. Es código que hay
  que mantener y que hace menos que `mlflow.genai`. Coste aceptado por la
  transparencia pedagógica; en el material se dice explícitamente que en producción
  se usa la biblioteca.
- **El conjunto de calibración hay que mantenerlo a mano.** 15 casos hoy. Si la
  rúbrica gana un criterio, hacen falta casos nuevos que lo ejerciten, o la
  calibración no puede detectar si el juez lo aplica. Es trabajo manual recurrente y
  no hay forma de evitarlo: automatizarlo con un LLM lo vuelve circular.
- **15 casos son pocos.** El intervalo de confianza de kappa con n=15 es ancho. Se
  declara en el código (`MINIMO_CASOS_CALIBRACION`) que 10 es un piso de clase y no
  una recomendación de producción.
- **El corte de 0.40/0.60 es arbitrario.** Es una convención citada. Un equipo con un
  criterio distinto debería cambiarlo — declarándolo antes de medir.

## Verificación

```bash
export PYTHONPATH=sesiones/s08-llmops/src

# La calibración, con el diagnóstico completo
python -c "
from clasificador.scorers.juez import JuezFake, calibrar, resultado_reportable
cal = calibrar(JuezFake())
print(resultado_reportable(cal, 1.0))
print('desacuerdos:', cal.desacuerdos)
print('punto ciego:', cal.punto_ciego)
"

# Los tests que fijan las reglas de este ADR
pytest sesiones/s08-llmops/tests/test_acuerdo_y_juez.py -v
```

## Referencias

- `sesiones/s08-llmops/rubricas/juez-resumen.md` — la rúbrica
- `sesiones/s08-llmops/src/clasificador/scorers/juez.py` — implementación
- `sesiones/s08-llmops/src/clasificador/scorers/acuerdo.py` — kappa y análisis del desacuerdo
- `sesiones/s08-llmops/datos/calibracion-juez.jsonl` — 15 veredictos humanos
- Landis, J.R. y Koch, G.G. (1977), *The Measurement of Observer Agreement for
  Categorical Data*, Biometrics 33(1) — origen de los cortes de interpretación
- Documentación de MLflow 3.15: `mlflow.genai.make_judge`, `mlflow.genai.scorers`
