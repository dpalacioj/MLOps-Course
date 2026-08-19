# Rúbrica de severidad (1-5)

Esta rúbrica es la **definición operativa** de la etiqueta `severidad` en
`datos/quejas.jsonl`. Existe por una razón concreta: sin ella, dos personas
etiquetan el mismo dataset de forma distinta, el desacuerdo entre anotadores se
mezcla con el error del modelo, y las métricas del eval dejan de significar algo.

Es también el texto que se copia (resumido) al prompt `v2-rubrica.txt`. Que el
anotador humano y el modelo trabajen con **el mismo criterio escrito** es lo que
hace comparable la etiqueta con la predicción.

## La escala

| Nivel | Definición | Anclas del dataset |
|---|---|---|
| **1** | Molestia menor, sin impacto real. El usuario informa más que reclama. | `q018` (esperó 12 min y llegó bien), `q013` (felicitación) |
| **2** | Impacto leve: incomodidad, pocos minutos perdidos, monto trivial. | `q002` (olor a cigarrillo), `q015` (cupón no aplicado), `q035` (recargo nocturno indebido) |
| **3** | Impacto claro: el servicio no cumplió lo prometido, hay dinero en disputa, o el usuario perdió un compromiso. | `q001` (cobro muy superior al estimado), `q004` (perdió una reunión), `q016` (se manchó antes de una entrevista) |
| **4** | Impacto grave: falta de respeto explícita, monto significativo, usuario dejado en la vía, no pudo viajar. | `q007` (el conductor le gritó), `q024` (120 mil por 15 min), `q021` (silla de ruedas), `q032` (cinturón roto) |
| **5** | Riesgo para la integridad o la seguridad de una persona, presunto delito, o involucra a un menor o a una persona vulnerable. | `q003` (semáforos en rojo), `q014` (zona escolar con una menor), `q019` (conductor alcoholizado), `q036` (la siguió al bajarse) |

## Las tres reglas que resuelven casi todos los desacuerdos

1. **La severidad mide el impacto sobre el usuario, no el tono del texto.** Un
   mensaje en mayúsculas por un recargo de dos mil pesos es un 2. `q026` está en
   el dataset exactamente para fijar esto: tono fuerte, severidad 3.
2. **La severidad es independiente de `requiere_reembolso`.** Son dos ejes. Una
   agresión es 5 y no genera reembolso (`q003`, `q019`, `q036`); un cupón que no
   se aplicó es 2 y sí lo genera (`q015`). Colapsar los dos ejes en uno es el
   error de etiquetado más frecuente.
3. **Ante la duda entre dos niveles adyacentes, se elige el menor** y se anota el
   motivo en `notas`. Inflar la severidad "por si acaso" destruye la utilidad de
   la escala para priorizar la cola: si todo es 4, nada es urgente.

## Casos límite conocidos y sin resolver

Honestidad sobre el dataset: estos casos son genuinamente discutibles y su
etiqueta es una **decisión**, no una verdad.

- `q022` (aire acondicionado dañado): se etiquetó `otro`/2. Un argumento
  defendible lo pondría en `limpieza` (estado del vehículo) o en severidad 3 (32
  grados es más que una molestia). Se dejó así y se documentó.
- `q031` (esperó, el conductor no llegó, y le cobraron): se etiquetó `tarifa`
  porque el usuario reclama el dinero. `tiempo_de_espera` es igualmente
  defendible.
- `q033` (no llega la factura): se etiquetó `tarifa` sin reembolso. Un argumento
  válido lo pondría en `otro`, porque el problema es administrativo y no el monto.

Estos tres casos son la razón por la que la exactitud de categoría **nunca va a
llegar a 1.00**, ni con el mejor modelo. El techo del dataset no es 100%: es el
acuerdo entre anotadores humanos. Reportar un eval sin conocer ese techo lleva a
perseguir mejoras que están dentro del ruido del etiquetado.
