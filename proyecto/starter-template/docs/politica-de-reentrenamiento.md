# Política de reentrenamiento

> Una página. Es el documento que cierra el ciclo: el monitoreo detecta, esta
> política decide y el gate de promoción ejecuta. Sin ella, el reentrenamiento es
> algo que alguien hace cuando se acuerda.
>
> TODO(estudiante) 32: reemplaza cada TODO. El criterio de calificación es si un
> compañero podría **operar** tu sistema leyendo solo este archivo.

## 1. Trigger: qué dispara un reentrenamiento

TODO(estudiante) 32: elige uno como principal y justifícalo contra los otros tres.

| Estrategia | Cuándo conviene | Riesgo |
|---|---|---|
| Periódico (semanal / mensual) | los datos cambian gradualmente | reentrena sin necesidad; cuesta |
| Por llegada de datos | llegan particiones nuevas | hay que detectar la disponibilidad |
| Por `drift` detectado | cambios impredecibles | falsos positivos → churn de modelos |
| Por caída de performance | hay labels en producción | los labels llegan tarde (*label lag*) |

**Elegido:** TODO. **Por qué:** TODO. **Frecuencia máxima:** TODO.

Un anti-patrón concreto que hay que evitar: `cron="*/2 * * * *"` reentrenando el
modelo completo. Cuesta dinero, no aporta señal y enseña el hábito contrario al
correcto.

## 2. Umbrales y su justificación

| Señal | Umbral | Ventana | Por qué **este** número |
|---|---|---|---|
| Fracción de columnas con `drift` | TODO | TODO | TODO |
| Tamaño de efecto por columna (KS / V de Cramer) | TODO | TODO | TODO |
| Degradación de la métrica de negocio | TODO | TODO | TODO |

Dos advertencias que el umbral tiene que respetar:

- **`p < 0.05` no es un criterio de `drift`.** Con n grande todo sale
  significativo: con 500 000 filas, un cambio de la media del 0.1 % da
  p < 1e-10 y no le importa a nadie. Hay que mirar el tamaño del efecto.
- **La estacionalidad no es `drift` accionable.** Si diciembre siempre se comporta
  distinto, la respuesta puede ser incluir la estacionalidad como feature, no
  reentrenar cada diciembre.

## 3. Datos que se usan al reentrenar

TODO(estudiante) 32: ¿ventana móvil de N períodos, o todo el histórico? ¿Se
reponderan los datos recientes? ¿Qué pasa con el período que causó el `drift` —
entra al entrenamiento o se excluye como anómalo? Esta última decisión es la que
más se olvida y la que más cambia el resultado.

## 4. Quién aprueba y qué queda registrado

| Situación | Decide | Evidencia que queda |
|---|---|---|
| El gate aprueba el candidato | automático | tag `validation_status=passed` + `gate_motivo` en la versión |
| El gate rechaza | automático (no se promueve) | tag `validation_status=failed` + motivo |
| Se quiere promover pese al rechazo | TODO: persona | TODO: dónde se registra la excepción |

Que la evidencia del rechazo se guarde importa tanto como la de la aprobación:
tres semanas después, "por qué no se promovió aquel modelo" es una pregunta real.

## 5. Rollback

TODO(estudiante) 32: escribe el comando exacto.

Volver atrás es mover el alias `@champion` a la versión anterior:

```python
from mlflow import MlflowClient

MlflowClient().set_registered_model_alias("miproyecto-modelo", "champion", "6")
```

Es una escritura de metadatos —sub-segundo, sin reentrenar, sin rebuild de imagen,
sin redeploy— y funciona porque las versiones del `registry` son inmutables: el
artefacto de la versión 6 sigue siendo bit a bit el que estaba sirviendo. Esa
propiedad es la razón principal para referenciar el modelo por alias en lugar de
copiarlo a un directorio.

**Criterio para hacer rollback:** TODO. **Quién puede ejecutarlo:** TODO.

## 6. Alertas

Una alerta necesita cuatro cosas o es ruido: **umbral, ventana, destinatario y
acción esperada**. Una alerta sin acción esperada se ignora, y la fatiga de
alertas es un problema de operación tan real como el `drift`.

| Alerta | Umbral | Destinatario | Acción esperada |
|---|---|---|---|
| TODO | TODO | TODO | TODO |
