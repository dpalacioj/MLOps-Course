# Model card

> **Este archivo debe generarse por script, no escribirse a mano.**
> `make model-card` lo regenera desde los metadatos del run de MLflow. Una model
> card escrita a mano se desactualiza en el primer reentrenamiento y a partir de
> ahí miente, que es peor que no tenerla.
>
> TODO(estudiante) 30: implementa `scripts/model_card.py`. Mientras no exista, esta
> plantilla marca qué campos tiene que rellenar el script.

## Identificación

| Campo | Valor |
|---|---|
| Modelo registrado | `{nombre_registrado}` |
| Versión | `{version}` |
| Alias | `{alias}` |
| `run_id` | `{run_id}` |
| Fecha de entrenamiento | `{fecha}` |
| Commit del código | `{git_sha}` |

Los seis campos juntos son lo que hace auditable el sistema: con ellos se puede
reconstruir exactamente qué produjo una predicción concreta.

## Uso previsto y no previsto

**Previsto:** TODO. **No previsto:** TODO. Esta segunda parte es la que evita que
alguien use tu modelo para decidir algo que nunca estuvo en su alcance.

## Datos de entrenamiento

| Campo | Valor |
|---|---|
| Particiones | `{particiones}` |
| Filas | `{n_filas}` |
| Hash de los datos | `{hash_datos}` |
| Contrato de datos | ver `src/miproyecto/data/contract.py` |

## Métricas

### Globales, en el holdout fijo

| Métrica | Valor |
|---|---|
| `{metrica}` | `{valor}` |

### Por subgrupo

Una métrica global que mejora puede esconder un segmento que empeora. Reportar
solo el promedio es cómo se cuelan las regresiones de equidad.

| Subgrupo | n | Métrica |
|---|---:|---:|
| `{subgrupo}` | `{n}` | `{valor}` |

## Limitaciones conocidas

TODO. Sé específico: en qué rango de entradas el modelo es poco confiable, qué
segmentos tienen poca muestra, qué supuesto se rompe si cambia el proceso de
negocio.

## Consideraciones éticas y de riesgo

Ver `docs/riesgos.md`.
