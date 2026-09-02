# Riesgos del sistema

> Cinco riesgos, con mitigación concreta. "Riesgo: que el modelo falle" no es un
> riesgo, es una tautología. Un riesgo útil nombra el mecanismo, el impacto y
> quién lo absorbe.
>
> TODO(estudiante) 33: completa la tabla con riesgos **de tu sistema**. Los que
> están aquí son ejemplos del tipo de cosa que se espera; cámbialos.

## Registro de riesgos

| # | Riesgo | Mecanismo por el que ocurre | Impacto | Prob. | Mitigación implementada | Detección |
|---|---|---|---|---|---|---|
| 1 | El proveedor cambia las unidades de una columna | El pipeline no valida rangos, entrena y sirve normalmente | Predicciones sistemáticamente sesgadas, sin error visible | media | Contrato de datos con rangos de negocio (`data/contract.py`) | El CI falla con el fixture roto; el contrato falla en el `flow` |
| 2 | Aparece una categoría nueva en producción | El encoder la descarta en silencio y el registro se predice como "promedio" | Degradación concentrada en el segmento nuevo | alta | `DictVectorizer` ignora claves no vistas; se monitorea `drift` categórico | `check_drift.py` con V de Cramer |
| 3 | Un modelo peor llega a producción | El pipeline promueve porque el entrenamiento terminó sin excepciones | Pérdida de calidad sin causa aparente | media | Gate de promoción con holdout fijo y criterio por subgrupo | Tag `validation_status` en el `registry` |
| 4 | Degradación silenciosa por `label lag` | Los labels llegan semanas después; nadie mide mientras tanto | Semanas de decisiones malas | alta | Monitoreo de `data drift` y `prediction drift`, que no necesitan labels | Reporte de `drift` desde el pipeline |
| 5 | TODO(estudiante) 33 | TODO | TODO | TODO | TODO | TODO |

## Clasificación tentativa bajo el AI Act

TODO(estudiante) 33: ¿tu sistema entraría en alguna categoría de alto riesgo del
Anexo III (empleo, crédito, educación, servicios esenciales, biometría)? Justifica
la respuesta, sea sí o no.

Marco mental de las tres piezas, que responden preguntas distintas:

| Instrumento | Qué es | Qué pregunta responde |
|---|---|---|
| **AI Act** (UE) | Reglamento | Qué **exige la ley** según el riesgo del sistema |
| **ISO/IEC 42001** | Norma certificable | Cómo **organizas la gobernanza** de IA |
| **NIST AI RMF** | Marco voluntario | Cómo **razonas el riesgo** técnico |

Notas de vigencia (verifícalas antes de citarlas: esta área cambia):

- El AI Omnibus aplazó los plazos de alto riesgo — 2 de diciembre de 2027 para el
  Anexo III y 2 de agosto de 2028 para el Anexo I.
- Las obligaciones de transparencia del Art. 50 aplican desde el 2 de agosto de 2026.

Buena parte del material que circula en la web tiene las fechas pre-Omnibus. Citar
una fecha desactualizada como vigente es un error de fondo, no de forma.

## Riesgos operativos y de seguridad

| # | Riesgo | Mitigación |
|---|---|---|
| S1 | Secreto commiteado | `gitleaks` en `pre-commit` y en CI; `.env` en `.gitignore`; rotación si ocurre |
| S2 | Deserialización de un artefacto no confiable | El modelo se resuelve del `registry` propio; no se cargan `pickle` de terceros |
| S3 | La imagen corre como root | Usuario no-root en el `Dockerfile`; el CI falla si el UID es 0 |
| S4 | Fuga de detalles internos en errores de la API | El detalle va al log con un id de correlación; al cliente va un mensaje estable |
| S5 | TODO(estudiante) 33 | TODO |
