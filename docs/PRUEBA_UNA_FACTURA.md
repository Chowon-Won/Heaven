# Procedimiento: probar UNA factura real

Objetivo: comprobar con una sola escuela que la selección, el producto, el guardado y la impresión
funcionan antes de habilitar el modo automático.

## Preparación
1. Instale y calibre (ver `MANUAL.md`, sección Calibración).
2. En Configuración pulse **Probar conexión con SisFaCon**: debe encontrar la ventana, no listar
   ventanas pendientes y leer bien los campos calibrados.
3. Haga una jornada **simulada** completa para familiarizarse con los controles.

## La prueba
1. En SisFaCon abra «Registro de Conduce a Centro Educativo» con un formulario **nuevo** (0 líneas)
   y compruebe la FECHA.
2. En AutoFacturador → **Nueva jornada** → producto del día → **una** escuela → tipo **real** →
   Crear jornada.
3. En **Automatización** elija **Prueba**, seleccione la escuela en la tabla y pulse
   **Ejecutar escuela seleccionada**. Acepte el aviso. No toque el teclado ni el ratón.
4. El macro pulsa F7, busca la escuela, pulsa Enter y **verifica el código**. Luego introduce el
   producto y **verifica la línea y la descripción**.
5. Pregunta **«¿Grabar ahora esta factura REAL con Ctrl+G?»**. Mire SisFaCon: escuela y producto
   deben ser correctos. Pulse *Grabar* solo si lo son.
6. Espera la ventana **Preview**. Pregunta **«¿Imprimirlo ahora?»** → *Imprimir* (F9 → OK).
7. Cierra la vista previa con Esc y verifica que cambió «ULTIMAS CONDUCE REGISTRADO».
8. Pregunta **«¿El conduce aparece correcto…?»**. Revise en SisFaCon (F5 Busca Facturas) y el papel
   impreso. Responda *Sí, todo correcto* solo si todo está bien → se habilita el modo automático.

## Si algo no sale bien
* **Producto no reconocido** con la línea en 0: quizá SisFaCon necesita otro Enter. En Configuración
  cambie «Tras escribir el código de producto» a `{ENTER}{ENTER}` (o `{TAB}`), limpie el formulario
  con *Cancelar* en SisFaCon, marque la factura como pendiente y repita.
* **Aparece una ventana desconocida**: el modo de prueba le pregunta si es un mensaje inofensivo. Si
  lo es (por ejemplo «Registro guardado»), elija *Aceptar y recordar*.
* Cualquier detención deja un mensaje claro en la tabla y una captura en la carpeta de datos.

Después de una prueba correcta, ejecute un **grupo de prueba** de 2–3 escuelas en modo automático
con «Confirmar la siguiente operación» activado, antes de lanzar la jornada completa.
