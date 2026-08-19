# Soluciones de referencia — Sesión 8

> **No publicar antes del taller.**

- [`autoverificacion.md`](autoverificacion.md) — las cinco preguntas del README, con
  la respuesta completa y qué se evalúa en cada una.
- [`taller-referencia.md`](taller-referencia.md) — solución de los cinco ejercicios,
  con el código y los números que produce.

## Cómo usar esto al corregir

Los tres criterios que más discriminan, en orden:

1. **¿Reportó el kappa junto al resultado del juez?** Es el único criterio que rechaza
   el PR de forma automática. Un kappa bajo bien diagnosticado es un buen entregable;
   un número del juez sin calibración no lo es.
2. **¿Reportó lo que empeoró?** Un PR que solo muestra deltas positivos no es un
   experimento. Y un resultado negativo bien documentado está **completo**: es la
   mayoría de los resultados reales.
3. **¿Declaró la hipótesis antes de medir, y los límites de su heurística?** Un scorer
   honesto sobre sus falsos positivos vale más que uno que finge no tenerlos.

Lo que **no** hay que penalizar:

- Que el `v3` no mejore nada en modo fake. Es lo esperado (`ProveedorFake` solo
  reacciona a `MARCADOR_RUBRICA`), y decirlo en el PR **es** la respuesta correcta.
- Que el kappa baje al añadir casos de calibración. Significa que añadió casos que el
  juez no puede resolver, que es información útil.
- Un scorer con heurística imperfecta, si los límites están declarados en el docstring.

Lo que **sí** hay que rechazar:

- Bajar un umbral para que el gate pase. Si el gate se puso rojo, el gate funcionó.
- Un scorer que devuelve 1.0 siempre (sube la media y no mide nada).
- Iterar el prompt mirando los 36 casos sin declararlo.
- Un juez para algo que se mide con `==`.
