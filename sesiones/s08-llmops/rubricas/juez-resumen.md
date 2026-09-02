# Rúbrica del juez: calidad del resumen

Esta rúbrica es **el artefacto**, no un anexo. El prompt del juez se construye a
partir de este archivo (`scorers/juez.py` lo lee), así que cambiar la rúbrica es
un commit que se diffea y se revisa, igual que cambiar el prompt del clasificador.

Si la rúbrica vive dentro de un f-string en el código, tres cosas se pierden: la
puede leer un anotador humano que no programa, se puede diffear cuando cambia, y
se puede citar en la discusión sobre por qué un caso se calificó así.

## Qué evalúa el juez

Solo el campo `resumen`. Los otros tres campos (`categoria`, `severidad`,
`requiere_reembolso`) los mide un scorer determinista contra la etiqueta humana,
porque **tienen** respuesta correcta. No se usa un juez donde alcanza un `==`:
cuesta dinero, introduce varianza y no mejora la medición.

## Escala

Binaria: `aprobado` / `rechazado`. Deliberadamente binaria y no de 1 a 5.

Una escala de 5 puntos con un LLM produce números que parecen precisos y no lo
son: el mismo caso saca 3 o 4 según la temperatura y el orden de los ejemplos, y
el acuerdo con humanos se derrumba porque los humanos tampoco distinguen 3 de 4
de forma consistente. Una decisión binaria es lo que un juez de LLM hace de forma
razonablemente fiable, y es lo que se puede calibrar con kappa.

Si hace falta granularidad, se agregan **criterios binarios** en lugar de puntos
en una escala. Eso es lo que hace la lista de abajo.

## Criterios

El resumen se **aprueba** solo si cumple los cuatro:

1. **Fidelidad.** Todo lo que afirma el resumen está en la queja. No agrega
   montos, no agrega causas, no agrega intenciones del conductor que el usuario
   no mencionó. Inventar un detalle es rechazo automático, aunque el resumen sea
   por lo demás excelente.
2. **Suficiencia.** Menciona el motivo principal de la queja. Un resumen fiel
   pero vacío ("El usuario presentó una queja") se rechaza.
3. **Sin datos personales.** No copia nombres de personas, teléfonos, correos,
   placas, números de tarjeta ni direcciones exactas. "el conductor" y "la
   dirección de destino" son correctos; "Juan Pérez" y "carrera 43 #12-05" no.
   Este criterio existe porque el resumen se propaga a sistemas de soporte y a
   las trazas (ver `riesgos.md`).
4. **Tono neutro.** Describe, no juzga. "El conductor conducía a exceso de
   velocidad" es correcto; "El conductor es un irresponsable" no.

## Casos límite, resueltos de antemano

Resolver estos casos **antes** de medir es lo que hace que el acuerdo
juez-humano sea interpretable. Si el criterio se define después de ver los
desacuerdos, se está ajustando la rúbrica al resultado.

- **Resumen más corto que el límite pero telegráfico** ("Cobro doble"): se
  aprueba si el motivo principal es identificable. La brevedad no es un defecto.
- **Resumen en primera persona** ("Me cobraron dos veces"): se aprueba. La
  rúbrica del clasificador pide tercera persona, pero eso lo verifica un scorer
  determinista si hace falta; el juez mide contenido, no formato.
- **Menciona un monto que sí está en la queja**: se aprueba. Copiar un monto no
  es un dato personal.
- **Menciona el número parcial de una tarjeta** ("tarjeta terminada en 4321"):
  se **rechaza** por el criterio 3, aunque el dato esté en la queja original.
  Reproducir un identificador financiero en un campo que se propaga es
  precisamente lo que el criterio quiere impedir.
- **Queja que no es queja** (una felicitación): se aprueba si el resumen refleja
  que el comentario es positivo. Se rechaza si lo describe como un problema.

## Regla no negociable

> **Un juez sin calibrar contra una muestra etiquetada por humanos no es una
> métrica: es una opinión con API.**

Antes de usar el número del juez para tomar cualquier decisión —promover un
prompt, aceptar un PR, reportar calidad a alguien— hay que medir cuánto coincide
con esta rúbrica aplicada por una persona. `scorers/acuerdo.py` calcula el
porcentaje de acuerdo y el kappa de Cohen sobre `datos/calibracion-juez.jsonl`.

Umbrales que se usan en esta sesión, y de dónde salen:

| Kappa | Lectura | Qué hacer |
|---|---|---|
| < 0.40 | Acuerdo pobre | El número del juez no se reporta. Se arregla la rúbrica o se cambia el modelo juez. |
| 0.40 – 0.60 | Moderado | Se reporta **siempre acompañado del kappa**. No se usa como gate. |
| > 0.60 | Sustancial | Se puede usar como gate, con el kappa en el reporte. |

Los cortes vienen de la escala de interpretación de kappa de Landis y Koch
(1977), que es una convención, no una ley. Lo importante no es el corte exacto:
es que **exista un corte declarado antes de mirar el resultado**.

## Por qué kappa y no solo el porcentaje de acuerdo

Si el 85% de los resúmenes son buenos, un juez que aprueba todo saca 85% de
acuerdo y no distingue nada. Kappa descuenta el acuerdo esperado por azar y en
ese caso da 0. Es la misma razón por la que en clasificación desbalanceada no se
reporta accuracy sola.

Kappa tiene su propia patología: con clases muy desbalanceadas puede dar valores
bajos aunque el acuerdo sea alto (la *paradoja de kappa*). Por eso se reportan
los dos números y la matriz de confusión, no uno solo.
