# Cabina — la consola de clase

Una página por sesión, para tener abierta **en la pantalla del instructor** mientras
se dicta. No sustituye al guion: el guion se lee el día antes y explica el porqué; la
cabina es lo único que se mira durante las cuatro horas.

| Sesión | Archivo | Estado |
|---|---|---|
| S03 · tracking y registry | [`s03.html`](s03.html) | en uso |
| S01, S02, S04–S08 | — | pendientes, después de probar la S03 en clase |

## Cómo abrirla

```bash
open instructor/cabina/s03.html
```

Es un archivo autocontenido: no necesita servidor ni dependencias. Solo pide las dos
tipografías a Google Fonts, y sin red usa las del sistema sin romperse.

## El montaje de dos pantallas

| Tu pantalla | Pantalla proyectada |
|---|---|
| la cabina, **en otro navegador** | VS Code, las dos terminales y la UI de MLflow |

**La cabina va en un navegador distinto al de la UI de MLflow.** Contiene las
respuestas de las preguntas que vas a hacer en voz alta; si comparte ventana con lo
que proyectas, en algún momento le enseñas a la clase la respuesta antes de la
pregunta.

Y dos ventanas de terminal **de aspecto distinto**, no dos pestañas: `make mlflow`
secuestra una en primer plano toda la sesión, y un `Ctrl-C` en la pestaña equivocada
mata el servidor a mitad de clase.

## Cómo se maneja

| Tecla | Qué hace |
|---|---|
| `←` `→` | bloque anterior y siguiente |
| `E` | abre y cierra el panel de errores frecuentes |
| `R` | borra las marcas de completado, para volver a ensayar |
| clic en un comando | lo copia al portapapeles |
| clic en un paso | lo marca como hecho |

Las **cinco luces** de la barra superior son el estado invisible de la sesión —
servidor, base de datos limpia, `autolog`, HPO lanzado, `@champion`. Se encienden a
mano y son lo que evita entrar a un bloque con el estado que rompe el siguiente. Las
marcas y las luces viven en memoria: al recargar la página se reinician.

## Qué resuelve respecto al guion

El guion está escrito para leerse; la cabina, para ojearse. Cada vez que bajas la
vista con un guion en prosa pagas unos segundos en reencontrar tu sitio, unas cuarenta
veces en una sesión. La cabina fija las columnas —qué teclo, qué debe salir, qué
pregunto— para que el ojo aterrice siempre en el mismo lugar.

Tres cosas que la cabina dice y el guion de la S03 no:

1. **Qué terminal.** De los 18 comandos de la sesión, solo `make mlflow` va en la
   terminal del servidor. El guion declara dos terminales y casi nunca dice cuál.
2. **El estado entre bloques.** Si `autolog` queda encendido al salir del bloque del
   fallo, cada `fit` posterior crea un run y el bloque de HPO se contamina.
3. **La pausa es un paso.** Lanzar `make hpo` antes de la pausa es lo que hace que al
   volver haya resultados que mostrar. En el guion era una línea bajo un encabezado
   que dice "Pausa".

También resuelve dos solapes de numeración del guion: el paso 4 del notebook 02 lo
reclamaban dos bloques, y el paso 6 otros dos. El reparto vigente —el mismo que usa el
[README de la sesión](../../sesiones/s03-tracking/README.md)— es pasos 1 a 3 en
*Tracking manual*, pasos 4, 5 y 7 en *El fallo*, y paso 6 en *Model card*.
