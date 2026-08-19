# ADR 001 — Un solo caso guía: NYC Green Taxi con particiones fijas

- **Estado:** aceptada
- **Fecha:** 2026-04
- **Alcance:** todo el curso (sesiones 1 a 8)
- **Decisores:** equipo docente del curso de MLOps

## Contexto

La auditoría del repositorio anterior encontró que **cada sesión usaba un dataset
distinto** y, peor, que varias usaban el *mismo* dataset con definiciones
incompatibles:

| Módulo | Dataset | Features | Periodo |
|---|---|---|---|
| Experiment Tracking | Green Taxi | `PULocationID`, `DOLocationID`, `trip_distance` | 2023 fijo |
| Orquestación (Prefect) | Green Taxi | `PU_DO`, `trip_distance` | `datetime.now()` → 2025-01 |
| Orquestación (Mage) | Green Taxi | `PULocationID`, `DOLocationID` | 2023, otros meses |
| Monitoreo | datos sintéticos | inventadas | n/a |
| Deployment batch | datos sintéticos | `random.choices([0,1])` como target | n/a |

Las consecuencias eran concretas y medibles en tiempo de clase:

1. **El pipeline estrella no arrancaba.** El módulo de orquestación calculaba el
   periodo con `datetime.now()` y pedía `green_tripdata_2025-01.parquet`, un
   archivo que la NYC TLC puede no haber publicado todavía. Un curso no puede
   depender del calendario de publicación de un tercero.
2. **Nada se podía comparar.** Un RMSE del módulo de tracking y otro del módulo
   de orquestación no eran comparables: distintas features, distintos meses,
   distinto filtrado. La comparación de modelos es el centro de MLOps y el repo
   la hacía imposible.
3. **El target del módulo de deployment era ruido.** `random.choices([0, 1])` no
   tiene señal aprendible; el estudiante veía métricas de azar y aprendía una
   lección falsa sobre qué es un modelo que funciona.
4. **Cada sesión gastaba entre 15 y 40 minutos** re-explicando un dominio nuevo
   en lugar de enseñar la práctica de MLOps de esa sesión.

## Decisión

**Un único caso guía para las ocho sesiones: NYC Green Taxi Trip Records, con
particiones mensuales fijas y explícitas, declaradas en `src/taxi/config.py`.**

```
train      2023-01, 2023-02, 2023-03
valid      2023-04                     ← selección de hiperparámetros
holdout    2023-05                     ← juez del gate de promoción
producción 2023-07, 2024-01            ← drift real para monitoreo
```

Cuatro elementos de la decisión, cada uno resolviendo un problema de la tabla
anterior:

1. **Particiones fijas y del pasado.** Nunca `datetime.now()`. Los archivos de
   2023 y 2024 ya están publicados y no van a cambiar; su SHA-256 se registra en
   `data/raw/metadata.json` y el loader avisa si el proveedor republica el
   archivo (lo que invalidaría cualquier métrica comparada contra la versión
   anterior).
2. **División temporal, no aleatoria.** Se entrena con meses anteriores y se
   evalúa con meses posteriores, porque en producción el modelo siempre predice
   sobre el futuro. Un `train_test_split` aleatorio sobre datos temporales mezcla
   meses y produce métricas optimistas que no se sostienen al desplegar.
3. **Un holdout con un rol exclusivo.** `2023-05` no participa en la selección
   de modelo ni de hiperparámetros: es el juez del gate (sesión 6). Si se usa
   para tunear, el gate deja de medir generalización y pasa a medir cuánto se
   sobreajustó la búsqueda al juez.
4. **Un target binario derivado del mismo dato.** `viaje_largo = duration > 30 min`
   permite enseñar métricas de clasificación, umbrales de decisión y matriz de
   costos **sin traer un segundo dataset**. Es derivado, no inventado: tiene la
   misma señal que el problema de regresión, distribución desbalanceada realista
   (~27% de positivos) y un significado de negocio interpretable.

El drift de la sesión 7 también es **real, no sintético**: `2023-07` aporta
estacionalidad de verano y `2024-01` está a un año de distancia, con cambios de
tarifa y de patrones de movilidad. No hace falta inyectar ruido con numpy.

## Alternativas consideradas

**A. Mantener un dataset distinto por sesión (statu quo).**
Ventaja: variedad de dominios, cada instructor elige lo que conoce.
Descartada: es la causa directa de los cuatro problemas listados. La variedad de
dominios no es un objetivo del curso; la práctica de MLOps sí.

**B. Datos completamente sintéticos, generados por el repo.**
Ventaja: sin red, sin descargas, tamaño controlado, reproducibilidad perfecta.
Descartada: los problemas más importantes del curso —drift real, cambio de
unidades, valores no vistos en producción, republicación de archivos por el
proveedor— *no existen* en datos sintéticos, o existen solo porque alguien los
inyectó a propósito. Un contrato de datos que solo atrapa el ruido que uno mismo
metió no enseña nada. Se conserva el uso de datos sintéticos únicamente en los
**fixtures de test**, donde la reproducibilidad sí es el objetivo.

**C. Un dataset tabular clásico (California Housing, Titanic).**
Ventaja: cabe en memoria, viene con scikit-learn, cero descargas.
Descartada: no tiene dimensión temporal. Sin tiempo no hay división temporal, no
hay drift, no hay "producción simulada" y no hay reentrenamiento periódico, que
son cuatro de los ocho temas del curso.

**D. Green Taxi con periodo relativo (últimos N meses disponibles).**
Ventaja: los datos siempre se sienten actuales.
Descartada: es exactamente el bug que se está corrigiendo. Además rompe la
reproducibilidad entre cohortes: el mismo comando ejecutado en dos semestres da
métricas distintas y las guías escritas dejan de coincidir con lo que ve el
estudiante.

**E. Yellow Taxi en lugar de Green.**
Descartada por tamaño: los parquet de Yellow son de 3 a 5 veces más grandes
(millones de filas por mes). Green da ~65 000 viajes/mes, que con un muestreo
determinista de 60 000 filas por partición entrena en segundos. Poder iterar
rápido en clase pesa más que el volumen.

## Consecuencias

**Positivas**

- Las métricas son comparables entre todas las sesiones: mismo dato, mismas
  features (`src/taxi/features/contract.py`), mismo filtrado.
- El pipeline es reproducible entre máquinas y entre cohortes: particiones fijas
  + SHA-256 + semilla explícita (`config.SEMILLA = 42`).
- El caso acumula complejidad en lugar de reiniciarla: en la sesión 7 el
  estudiante ya conoce el dominio y puede concentrarse en el drift.
- Dos problemas de ML (regresión y clasificación) por el precio de un dataset.
- El gate de promoción tiene un juez estable, que es la condición para que
  signifique algo.

**Negativas y su mitigación**

- *Se requiere red la primera vez* (~200 MB de parquet). Mitigación: `taxi data`
  descarga y cachea una vez; el CI restaura `data/` desde caché con una clave
  fija (las particiones no cambian).
- *Un solo dominio puede resultar monótono en ocho sesiones.* Mitigación: el
  proyecto final es de dominio libre, y ahí el estudiante aplica lo aprendido a
  su propio dato.
- *Dependencia de un proveedor externo.* Mitigación: los hashes están registrados
  y el loader avisa si un archivo cambia; si la TLC retirara los archivos, el
  fallo es explícito y no silencioso.
- *Los datos son de 2023-2024, no del mes corriente.* Se asume a propósito: la
  reproducibilidad vale más que la sensación de actualidad. Es, además, una
  lección en sí misma sobre el costo de acoplar un pipeline al reloj.

## Referencias

- `src/taxi/config.py` — las particiones y la semilla, única fuente de verdad
- `src/taxi/features/contract.py` — el conjunto único de features
- `src/taxi/data/contract.py` — contratos de Pandera del crudo y del procesado
- `docs/adr/002-aliases-en-vez-de-stages.md` — la decisión sobre el registry
- NYC TLC Trip Record Data (datos públicos, uso libre con atribución)
