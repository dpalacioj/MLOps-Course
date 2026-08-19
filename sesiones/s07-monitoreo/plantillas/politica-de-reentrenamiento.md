# Política de reentrenamiento — `<nombre del sistema>`

> **Plantilla.** Una página. Si no cabe en una página, no se va a leer el día que haga
> falta. Sustituye todo lo que esté entre `<>` y borra las notas en cursiva.
>
> Regla de oro para rellenarla: **cada campo tiene que ser verificable por alguien que
> no seas tú**. "El equipo revisa periódicamente" no es una política; es una intención.

- **Sistema / modelo registrado:** `<models:/mi-modelo@champion>`
- **Responsable de esta política:** `<nombre y rol>`
- **Última revisión:** `<AAAA-MM>` · **Próxima revisión:** `<AAAA-MM>`
- **Clasificación AI Act:** `<riesgo mínimo | transparencia art. 50 | alto riesgo anexo III | alto riesgo anexo I>` (ver `riesgos.md`)

---

## 1. Trigger — qué dispara un reentrenamiento

*Elige uno o varios y **da el número**. Un trigger sin umbral no es un trigger.*

| Tipo | Condición exacta | Fuente de la señal | Frecuencia de evaluación |
|---|---|---|---|
| Drift de datos | `<fracción de columnas con drift > 0.30>` | `<comando del check>` | `<diaria / semanal>` |
| Degradación de performance | `<RMSE de 7 días > 1.10 × RMSE del holdout>` | `<job que compara con etiquetas>` | `<cuando lleguen etiquetas>` |
| Calendario | `<el día 5 de cada mes>` | `<schedule del orquestador>` | — |
| Evento de negocio | `<cambio de tarifa, producto nuevo, cambio de proveedor de datos>` | `<quién avisa y por qué canal>` | — |
| Volumen | `<el lote diario cae por debajo de 10.000 filas>` | `<mismo check>` | diaria |

**Label lag de este sistema:** `<minutos / días / meses>`.
*Si el label lag es alto, el trigger por performance no es utilizable como señal
primaria y hay que decirlo aquí explícitamente.*

**Lo que NO dispara un reentrenamiento:** *escríbelo, porque es la mitad de la política.*

- drift en una sola columna por debajo del umbral de dataset;
- un problema de calidad de datos (esquema, unidades, nulos): eso se arregla en el
  pipeline, reentrenar lo enmascara;
- un patrón estacional ya identificado como recurrente: se modela como feature, no se
  persigue reentrenando.

## 2. Datos — con qué se reentrena

- **Ventana:** `<últimos N meses / desde AAAA-MM>`. Justificación: `<por qué esa ventana>`.
- **Se incluyen los datos que dispararon la alerta:** `<sí / no>` y por qué.
- **Validación:** `<split temporal: train hasta X, valid X+1>`. *Nunca aleatorio con
  datos temporales: produce leakage y una métrica optimista.*
- **Holdout de decisión:** `<partición fija>`. No se toca para tunear.
- **Contrato de datos aplicado antes de entrenar:** `<sí / no>` · `<comando>`.

## 3. Aprobación — quién decide

| Paso | Quién | Qué mira | Puede vetar |
|---|---|---|---|
| Reentrenamiento lanzado | `<automático / persona>` | — | — |
| Gate técnico | `<automático>` | `<mejora global ≥ 1% y ningún subgrupo degradado > 5%>` | sí, bloquea el merge |
| Aprobación de promoción | `<nombre y rol — una persona identificable>` | métricas globales y por subgrupo, model card, reporte de drift | sí |
| Notificación | `<canal>` | — | — |

**El reentrenamiento produce un `@candidate`, nunca un `@champion`.**
*Un pipeline que promueve solo convierte el drift en degradación automática.*

## 4. Rollback — cómo se vuelve atrás

*Esto es lo que se lee a las 3 de la mañana. Comandos exactos, no descripciones.*

- **Síntoma que dispara el rollback:** `<p95 > X ms, tasa de error > Y%, RMSE online > Z>`.
- **Quién puede ejecutarlo sin pedir permiso:** `<rol>`.
- **Cómo:**

  ```bash
  <comando exacto que reasigna el alias a la versión anterior>
  <comando que verifica qué versión está sirviendo>
  ```

- **Tiempo objetivo de vuelta atrás:** `<minutos>`.
- **La versión anterior se conserva:** `<sí — el registry no borra versiones>`.
- **Se ha probado el rollback:** `<fecha del último ensayo>`.
  *Un rollback no ensayado no es un rollback: es una esperanza.*

## 5. Registro — qué queda escrito

Cada ciclo de reentrenamiento deja, sin excepción:

- [ ] el run de tracking con params, métricas, artefactos y hash de los datos;
- [ ] el reporte de drift que lo motivó (`<ruta>`), archivado, no sobrescrito;
- [ ] la decisión del gate y quién la aprobó;
- [ ] la model card regenerada (`<comando>`);
- [ ] una entrada en el CHANGELOG o en el registro de decisiones con **el motivo en una
      frase**;
- [ ] si se rechazó el candidato: por qué, y qué se hizo en su lugar.

## 6. Casos que esta política no cubre

*Sé explícito. Un límite declarado es gobernanza; un límite tácito es un incidente
futuro.*

- `<p. ej.: cambio de esquema de la fuente de datos → requiere revisar el contrato y las features, no solo reentrenar>`
- `<p. ej.: aparición de un subgrupo nuevo de usuarios → requiere revisar la evaluación por subgrupo antes de promover>`
- `<p. ej.: caída total de la fuente de datos → plan de degradación del servicio, no de reentrenamiento>`
