# Solución de referencia — Taller de la sesión 8

> **No publicar antes del taller.**

Los números de este documento están **medidos**, no estimados. Se obtuvieron con
`ProveedorFake` y el prompt `v2`.

---

## Ejercicio 1 — Scorer `resumen_en_tercera_persona`

### El código

En `scorers/deterministas.py`:

```python
#: Marcadores de primera persona. Heuristica declarada, con sus limites:
#: - No detecta la primera persona implicita en el verbo sin pronombre
#:   ("Fui dejado en la via").
#: - Falso positivo conocido: un resumen que cite textualmente al usuario, o la
#:   palabra "mi" usada como nota musical (no aplica a este dominio).
#: - "minutos" NO coincide con \b(mi)\b por el limite de palabra: se verifico.
_PRIMERA_PERSONA: Final[re.Pattern[str]] = re.compile(
    r"\b(?:me|mi|mis|yo|nos|nuestro|nuestra)\b|\b\w{3,}(?:amos|imos)\b",
    re.IGNORECASE,
)


def resumen_en_tercera_persona(resultado: ResultadoClasificacion) -> Puntaje:
    """1.0 si el resumen esta en tercera persona.

    Problema que resuelve: la plantilla de respuesta del equipo de soporte asume
    tercera persona. Un resumen en primera ("Me cobraron dos veces") produce
    mensajes incoherentes al usuario final.

    Es un scorer determinista y no un criterio del juez porque la propiedad es
    verificable sintacticamente: no hace falta entender el texto para decidirlo.
    """
    if resultado.clasificacion is None:
        return Puntaje("resumen_en_tercera_persona", 0.0, "no hay salida valida")
    hallado = _PRIMERA_PERSONA.search(resultado.clasificacion.resumen)
    if hallado is None:
        return Puntaje("resumen_en_tercera_persona", 1.0)
    return Puntaje(
        "resumen_en_tercera_persona", 0.0, f"marcador de primera persona: {hallado.group()!r}"
    )
```

Y añadirlo a `puntuar()` y a `SCORERS_DE_CONTRATO`.

### El resultado medido, y es lo interesante

```
resumen_en_tercera_persona = 0.361  (13/36)
```

Fallos de ejemplo:

```
q001: 'Me cobraron 45 mil pesos y la app me habia estimado 28'
q006: 'Me cobraron el viaje dos veces, aparecen dos cargos identicos de 19.500'
q007: 'El conductor me grito porque le pedi que subiera el aire acondicionado.'
```

**El scorer nuevo encontró un defecto real en el primer intento.** El resumidor del
`ProveedorFake` es extractivo —copia las primeras palabras de la queja— y las quejas
están escritas en primera persona. Un 0.361 es un fallo del sistema en dos de cada
tres casos, y no lo detectaba ningún scorer anterior.

**Al corregir, esto es lo que hay que buscar:** que el estudiante note que su scorer
nuevo baja una métrica y **lo reporte** en lugar de ajustar el scorer hasta que suba.
Un scorer nuevo que sale en 1.000 es sospechoso; uno que encuentra un fallo está
haciendo su trabajo.

### Los tests

```python
def test_tercera_persona_aprueba() -> None:
    r = _resultado(resumen="Cobro doble sin explicacion")
    assert det.resumen_en_tercera_persona(r).valor == 1.0


def test_primera_persona_rechaza() -> None:
    p = det.resumen_en_tercera_persona(_resultado(resumen="Me cobraron dos veces"))
    assert p.valor == 0.0
    assert "me" in p.motivo.lower()
```

Casos verificados de la heurística (los ocho pasan):

| Resumen | Tercera persona |
|---|---|
| `Cobro doble sin explicacion` | sí |
| `Me cobraron dos veces el viaje` | no |
| `El conductor no llego a tiempo` | sí |
| `Nos dejaron esperando 40 minutos` | no |
| `Mi tarjeta fue cobrada dos veces` | no |
| `Vehiculo con fuerte olor a cigarrillo` | sí |
| `Demora de 45 minutos; el usuario perdio una reunion` | sí |
| `Esperamos 40 minutos sin respuesta` | no |

---

## Ejercicio 2 — Criterio 5: dato accionable

### El criterio, para `rubricas/juez-resumen.md`

```markdown
5. **Dato accionable.** Si la queja contiene un dato concreto que el agente de
   soporte necesita para actuar —un monto, una duración, un código de cupón, un
   número de veces— el resumen lo conserva. Un resumen fiel y suficiente pero que
   obliga a abrir la queja original para hacer el trabajo no ahorró nada.

   Casos límite, resueltos de antemano:

   - **La queja no contiene ningún dato concreto** ("mal servicio"): se aprueba.
     El criterio solo aplica si hay algo que conservar.
   - **La queja contiene varios datos y el resumen conserva el principal** ("cobro
     de 45 mil" pero omite "estimado 28 mil"): se aprueba. El criterio pide el dato
     necesario para actuar, no un inventario.
   - **El dato es un identificador personal** (los cuatro dígitos de una tarjeta):
     el criterio 3 **manda** sobre este. Se rechaza. Los criterios no son
     independientes y el orden de precedencia hay que declararlo.
```

Ese último caso límite es el que hay que exigir: **declarar la precedencia entre
criterios**. Sin eso, `c03` es ambiguo (¿aprueba por el 5 o rechaza por el 3?) y el
kappa mide la ambigüedad de la rúbrica.

### Casos nuevos para `datos/calibracion-juez.jsonl`

```json
{"id": "c16", "caso_id": "q006", "entrada": "Me cobraron el viaje dos veces, aparecen dos cargos identicos de 19.500 en mi tarjeta.", "resumen": "Se registraron cargos duplicados por el mismo viaje.", "veredicto_humano": "rechazado", "criterio": "5 dato accionable", "notas": "Fiel, suficiente y neutro, pero omite el monto. El agente tiene que abrir la queja para saber cuanto devolver."}
{"id": "c17", "caso_id": "q015", "entrada": "Aplique el cupon PRIMERVIAJE y no se descontó nada, me cobraron la tarifa completa.", "resumen": "Un cupon promocional no se aplico a la tarifa.", "veredicto_humano": "rechazado", "criterio": "5 dato accionable", "notas": "Omite el codigo del cupon, que es el dato con el que se investiga."}
{"id": "c18", "caso_id": "q026", "entrada": "TRES HORAS ESPERANDO Y NADIE ME CONTESTA ESTO ES PESIMO NUNCA MAS", "resumen": "Espera de tres horas sin respuesta del servicio.", "veredicto_humano": "aprobado", "criterio": "cumple los cinco", "notas": "Conserva la duracion y normaliza el tono. Ancla positiva del criterio 5."}
```

### Lo que pasa con el kappa, y la lectura correcta

Con el criterio 5 añadido, `JuezFake` **no lo aplica en absoluto**: no tiene ninguna
regla que compare los datos concretos de la queja con los del resumen. Así que
aprueba `c16` y `c17`, que el humano rechaza.

Resultado esperado: **el kappa baja** (más desacuerdos) y el punto ciego pasa a
repartirse entre dos criterios (`1 fidelidad` y `5 dato accionable`).

**Las dos respuestas válidas al corregir:**

- "El kappa bajó porque añadí casos que un juez por reglas no puede resolver. El
  punto ciego ahora se reparte entre fidelidad y dato accionable. No usaría este
  juez como gate." → **correcta y completa.**
- "El kappa bajó, así que arreglé el juez fake para que detecte el criterio 5
  contando números." → **también válida**, si el estudiante reconoce que eso solo
  cubre los montos numéricos y no los códigos de cupón, y que sigue sin resolver la
  fidelidad. Es una mejora honesta con límite declarado.

**Lo que se rechaza:** quitar `c16` y `c17` porque bajan el kappa. Eso es ajustar el
conjunto de calibración al juez, que es exactamente al revés.

---

## Ejercicio 3 — Prompt v3

### La referencia: [`prompts/v3-sin-ejemplos.txt`](prompts/v3-sin-ejemplos.txt)

Es `v2` sin la sección `## Ejemplos`.

**Hipótesis declarada:** la rúbrica escrita basta para fijar los criterios, y quitar
los tres ejemplos ahorra tokens en cada llamada sin degradar la calidad.

### Resultado medido

| | v2 | v3 | delta |
|---|---:|---:|---:|
| Tokens del prompt de sistema | 958 | 783 | **-175 (-18%)** |
| Huella | `589edbecf23b` | `1f6b7c1684c5` | — |
| `categoria_correcta` | 0.944 | 0.944 | +0.000 |
| `severidad_exacta` | 0.861 | 0.861 | +0.000 |

### La lectura correcta, y es la parte que se evalúa

**Sin cambio en las métricas, -18% de tokens.** Y la conclusión correcta **no** es
"v3 gana":

> El `ProveedorFake` no lee los ejemplos. Solo busca el marcador `MARCADOR_RUBRICA`
> ("Como asignar la severidad"), que `v3` conserva. Por construcción va a puntuar
> idéntico. **Esta comparación no dice nada sobre si quitar los ejemplos degrada un
> modelo real** — y con un modelo real es bastante probable que sí, porque los
> ejemplos (few-shot) suelen aportar más que la descripción en tareas de
> clasificación con criterios sutiles.

Lo único que esta comparación establece de verdad es el **-18% de tokens**, que es un
hecho sobre el texto y no sobre el modelo.

**Lo que hay que exigir en el PR:** que la conclusión sea "el ahorro de tokens es real
y medible; el efecto en la calidad **no se puede concluir en modo fake**". Un
estudiante que escriba "v3 es igual de bueno y más barato, promovámoslo" no entendió
el aviso del README.

---

## Ejercicio 4 — Fallo provocado

Cualquiera de los cuatro sirve. La respuesta de referencia, con la opción de apretar
el contrato:

```bash
export PYTHONPATH=sesiones/s08-llmops/src
export LLMOPS_TRACING=local

python - <<'EOF'
from clasificador import esquema
from clasificador.clasificador import clasificar
from clasificador.proveedor import ProveedorFake

esquema.MAX_PALABRAS_RESUMEN = 3
r = clasificar('Me cobraron dos veces el viaje de anoche', proveedor=ProveedorFake())
print('exito:', r.exito, '| intentos:', r.intentos)
for i, e in enumerate(r.errores, 1):
    print(f'  intento {i}:', e)
EOF
```

**Salida medida:**

```
exito: False | intentos: 2
  intento 1: campo 'resumen': Value error, el resumen tiene 8 palabras y el maximo es 3.
  intento 2: campo 'resumen': Value error, el resumen tiene 8 palabras y el maximo es 3.
```

**La respuesta completa tiene tres partes:**

1. **Dónde se vio:** en el span `parsear_salida`, **no** en `llamar_modelo`. El modelo
   respondía perfectamente; era el contrato el que rechazaba la salida.
2. **El retry no convergió**, y eso también se ve en la traza: dos pares de spans que
   fallan en el mismo sitio. El problema no era del modelo, así que ningún reintento
   lo iba a arreglar. **Un reintento que no converge es una señal de que el problema
   no está donde el retry lo busca.**
3. **Sin trazas:** se habría empezado leyendo el prompt, que es donde no estaba el
   problema. El error mencionaba `resumen`, así que con suerte se llega en diez
   minutos; sin suerte, se reescribe el prompt primero.

**Qué se evalúa.** El punto 2. Notar que el reintento se repitió idéntico es la
observación que distingue a quien leyó la traza de quien leyó solo el mensaje de error.

---

## Ejercicio 5 (opcional) — Ampliar el dataset

Cualquier conjunto de 5 casos con `notas` sirve, siempre que `pytest` siga verde.

**El resultado esperado, y hay que anticiparlo al corregir:** los casos nuevos
**bajan** las métricas, porque las reglas del `ProveedorFake` se escribieron mirando
los 36 originales. Una queja escrita de otra forma no la cubre ninguna regla.

Eso es **exactamente el resultado correcto** y hay que decirlo así:

> "Bajaron las métricas porque encontraste casos que el sistema no maneja. Para eso
> sirve ampliar un dataset de evals. Si tus casos nuevos no hubieran bajado nada,
> serían casos redundantes con los que ya había."

Y es también la demostración práctica del sobreajuste del fake: **un clasificador que
saca 0.944 en el conjunto contra el que se escribió y baja en cinco casos nuevos no
tenía 0.944 de exactitud.**

**Lo que se rechaza:** ajustar las reglas del `ProveedorFake` para que los casos
nuevos pasen. Eso es repetir el sobreajuste, ahora a propósito.
