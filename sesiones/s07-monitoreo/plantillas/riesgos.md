# Registro de riesgos — `<nombre del sistema>`

> **Plantilla.** Cinco riesgos es el mínimo y también un buen máximo para empezar: un
> registro de veinte riesgos sin dueño es un documento decorativo. Sustituye lo que esté
> entre `<>`.
>
> Criterio para que un riesgo esté bien escrito: describe **un fallo concreto con una
> consecuencia concreta**, no una categoría. "Sesgo" no es un riesgo; "el modelo predice
> tiempos sistemáticamente más largos para viajes con origen en zonas de renta baja, lo
> que reduce su oferta de servicio" sí lo es.

- **Sistema:** `<nombre>` · **Modelo:** `<models:/...@champion>`
- **Responsable del registro:** `<nombre y rol>`
- **Fecha:** `<AAAA-MM-DD>` · **Próxima revisión:** `<AAAA-MM>`

---

## 1. Clasificación regulatoria (AI Act)

| Campo | Valor |
|---|---|
| Rol en la cadena de valor | `<proveedor / responsable del despliegue (deployer) / importador>` |
| Clasificación tentativa | `<riesgo mínimo / transparencia art. 50 / alto riesgo anexo III / alto riesgo anexo I / prohibido>` |
| Base de la clasificación | `<p. ej.: no decide sobre acceso a empleo, crédito, educación ni servicios esenciales, y no hace inferencia biométrica>` |
| **Fecha de aplicación que le corresponde** | `<2-feb-2025 / 2-ago-2025 / 2-ago-2026 / 2-dic-2027 / 2-ago-2028>` |
| Qué tendría que cambiar para subir de categoría | `<p. ej.: si el modelo pasara a decidir qué conductores reciben viajes, entraría en el anexo III por empleo>` |

*Fechas y fuentes primarias en [`../gobernanza.md`](../gobernanza.md) sección 2. Verificadas el
19 de agosto de 2026; el Digital Omnibus (en vigor el 27-jul-2026) aplazó el alto riesgo.
Confirma antes de reutilizar este documento.*

---

## 2. Riesgos

*Probabilidad e impacto: alto / medio / bajo. La columna que más importa es **Detección**:
un riesgo que no se detecta no se gestiona, se sufre.*

### R1 — `<Data drift no detectado por umbrales mal calibrados>`

| Campo | Contenido |
|---|---|
| Descripción | `<el umbral de una feature categórica de alta cardinalidad está por debajo del ruido del estimador, así que alerta siempre; el equipo silencia la alerta y deja de ver la señal real>` |
| Probabilidad / Impacto | `<alta / medio>` |
| Detección | `<medir la línea base nula cada trimestre y comparar con los umbrales configurados>` |
| Mitigación | `<calibrar los umbrales contra dos mitades de la referencia; documentarlo en un ADR>` |
| Responsable | `<rol>` |
| Riesgo residual | `<el ruido cambia si cambia el volumen del lote; se revisa en cada recalibración>` |

### R2 — `<Concept drift invisible por label lag>`

| Campo | Contenido |
|---|---|
| Descripción | `<las etiquetas llegan con N meses de retraso, así que la degradación real solo se conoce cuando el daño ya ocurrió>` |
| Probabilidad / Impacto | `<media / alto>` |
| Detección | `<proxies: drift de predicciones, tasa de intervención manual, quejas, métricas de negocio correlacionadas>` |
| Mitigación | `<panel de prediction drift; muestra de etiquetado acelerado; estimación de performance sin etiquetas si el caso lo permite>` |
| Responsable | `<rol>` |
| Riesgo residual | `<los proxies no son la métrica; se acepta explícitamente>` |

### R3 — `<Sesgo o degradación en un subgrupo, oculto por el promedio>`

| Campo | Contenido |
|---|---|
| Descripción | `<el error global mejora mientras empeora en un subgrupo minoritario; si ese subgrupo corresponde a un grupo de personas, es un problema de equidad, no solo de calidad>` |
| Probabilidad / Impacto | `<media / alto>` |
| Detección | `<métricas por subgrupo en el gate y en el monitoreo, con tamaño mínimo de subgrupo>` |
| Mitigación | `<el gate bloquea si un subgrupo se degrada por encima del umbral; revisión humana antes de promover>` |
| Responsable | `<rol>` |
| Riesgo residual | `<solo se vigilan los subgrupos definidos; uno no anticipado pasa desapercibido>` |

### R4 — `<Fallo silencioso del pipeline de datos>`

| Campo | Contenido |
|---|---|
| Descripción | `<la fuente entrega un lote parcial o con la unidad cambiada; el modelo predice sobre basura sin lanzar ningún error y el dashboard del servicio sigue verde>` |
| Probabilidad / Impacto | `<alta / alto>` |
| Detección | `<contrato de datos que falla temprano; alerta de volumen del lote; conteo de nulos y de categorías nuevas>` |
| Mitigación | `<validación obligatoria antes de inferencia; el batch no escribe resultados si el contrato falla>` |
| Responsable | `<rol>` |
| Riesgo residual | `<un cambio de significado con el mismo tipo y rango no lo detecta el contrato>` |

### R5 — `<Reentrenamiento que degrada, promovido sin control>`

| Campo | Contenido |
|---|---|
| Descripción | `<un ciclo automático entrena con un lote contaminado y promueve el modelo resultante; el rollback nunca se ensayó y tarda horas>` |
| Probabilidad / Impacto | `<baja / muy alto>` |
| Detección | `<gate de promoción con holdout fijo; comparación contra el champion; alertas del servicio tras el despliegue>` |
| Mitigación | `<el pipeline solo produce @candidate; aprobación humana; rollback por alias ensayado y cronometrado>` |
| Responsable | `<rol>` |
| Riesgo residual | `<el holdout envejece: si el mundo cambió, aprueba modelos que ya no sirven. Se revisa su vigencia cada <N> meses>` |

---

## 3. Riesgos descartados y por qué

*Tan importante como la lista anterior: deja constancia de lo que se consideró y se
decidió no gestionar. Si mañana ocurre, la discusión empieza desde una decisión
documentada y no desde cero.*

| Riesgo | Por qué no se gestiona ahora |
|---|---|
| `<p. ej.: ataque adversario dirigido a las features de entrada>` | `<el input no lo controla un tercero con incentivo; se revisará si se expone la API públicamente>` |
| `<...>` | `<...>` |
