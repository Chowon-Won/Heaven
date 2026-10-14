# Manual de uso — SisFaCon AutoFacturador

## Pestañas

### 1. Panel principal
Muestra las escuelas registradas y, para la jornada elegida: escuelas en la jornada, facturas
completadas, pendientes, con errores y que necesitan revisión, el producto y su código, la barra de
progreso y el estado del macro. Los botones Iniciar / Pausar / Reanudar / Detener actúan sobre la
jornada seleccionada en «Automatización» con el modo elegido allí.

### 2. Escuelas
* **Añadir / Editar** (doble clic en una fila) / **Eliminar** (con confirmación).
* **Activar / Desactivar**: una escuela inactiva no aparece al crear jornadas.
* **Buscar** por nombre o código. Selección múltiple con Ctrl o Mayús.
* **Importar CSV/Excel**: columnas `codigo; nombre; activo; notas`. Los códigos se leen como texto
  (`02968` conserva el cero). En Excel, si la columna es numérica con formato `00000`, también se
  respeta. Las filas repetidas o ya existentes se informan al final.
* **Exportar** a CSV o Excel. **Guardar plantilla** crea un archivo de ejemplo.
* Eliminar es un **borrado lógico**: el historial de facturas conserva el nombre y el código.

### 3. Productos
Igual que Escuelas. Campos:
* **Nombre** (lo que ve usted), **Código en SisFaCon** (lo que se teclea, como texto),
* **Descripción que muestra SisFaCon**: el texto que aparece en la columna Descripción al teclear el
  código. Si se deja vacío se compara con el nombre. Se admiten pequeñas diferencias (configurable).

### 4. Nueva jornada (asistente en 6 pasos)
1. **Fecha** (debe coincidir con la FECHA que muestra SisFaCon).
2. **Producto**: lista desplegable «Pan — 1000». Botones *Añadir producto*, *Editar productos* y
   *Administrar catálogo* sin salir del asistente.
3. **Confirmar código**: marque la casilla tras comprobar el código.
4. **Escuelas**: marque las escuelas. *Seleccionar todas las activas*, *Desmarcar todas*, buscar, y
   **configuraciones frecuentes** (guardar/cargar una combinación habitual de producto y escuelas).
5. **Revisión**: fecha, producto, código, cantidad de escuelas, lista y facturas previstas.
6. **Confirmar**: elija *simulada* o *real* y pulse **Crear jornada**.

Al crear una jornada real, si alguna escuela ya tiene ese mismo día una factura completada, en curso
o en revisión, se le avisa y puede quitarla de la lista.

La jornada guarda una **copia** del producto y de las escuelas: editar el catálogo después no cambia
el código de las facturas de esa jornada.

### 5. Automatización
* **Jornada**: elija la jornada a procesar.
* **Modo**: Simulado (jornadas simuladas), Prueba o Automático (jornadas reales).
* **Ejecutar escuela seleccionada**, **Ejecutar grupo de prueba** (primeras N pendientes) y
  **Ejecutar todas las seleccionadas**.
* **Confirmar la siguiente operación**: pregunta antes de cada escuela.
* La tabla muestra el estado de cada factura, la impresión, los intentos de recuperación, la etapa y
  el mensaje. Colores: verde completada, rojo error, naranja revisión.
* **Acciones manuales** (con el macro detenido):
  * *Marcar pendiente (verifiqué que NO existe)*: solo si comprobó en SisFaCon que el conduce no se
    grabó. Permite volver a procesarla.
  * *Marcar completada*: si comprobó que existe (y opcionalmente que se imprimió).
  * *Omitir*: la escuela no se procesará en esta jornada.

### 6. Historial y registros
Filtros por fechas, escuela, producto, estado y tipo de evento. Dos vistas: **Eventos** (cada paso:
jornada iniciada, escuela seleccionada, producto introducido, factura guardada, impresión, error de
acceso, recuperación…) y **Facturas**. **Exportar a CSV** exporta la vista actual.

### 7. Configuración
* **Ajustes**: títulos de ventanas, teclas, verificaciones, impresión, tiempos, intentos, OCR.
* **Calibración**: ver abajo.
* **Mensajes informativos aprendidos**: ventanas que usted declaró inofensivas en modo de prueba.
* **Diagnóstico**: *Probar conexión con SisFaCon* (lee los campos calibrados sin pulsar nada),
  *Bloquear de nuevo el modo automático*, *Abrir carpeta de datos*.

## Calibración

1. Abra SisFaCon → «Registro de Conduce a Centro Educativo». Déjela **siempre del mismo tamaño**
   (lo más sencillo: maximizada).
2. Seleccione a mano una escuela (F7) e introduzca a mano el código de un producto, sin grabar, para
   que los campos tengan texto. Use después «Cancelar» en SisFaCon.
3. En Configuración → Calibración, elija un campo y pulse **Capturar**:
   * Campos de tipo *región* (código del centro, nombre, último conduce, «Linea(s)», descripción):
     coloque el ratón en la esquina **superior izquierda** del texto y espere la cuenta; luego en la
     esquina **inferior derecha**.
   * Campos de tipo *punto* (celda Código): coloque el ratón en el centro de la celda azul.
4. Pulse **Probar lectura**. Si el «Control de Windows» devuelve el texto correcto, no hace falta OCR.
   Si no, instale Tesseract y compruebe que el OCR lo lee bien. Puede forzar el método (auto,
   control, ocr).
5. Obligatorios: `codigo_centro`, `celda_codigo_producto`, y los que pidan las verificaciones activas
   (`contador_lineas`, `descripcion_producto`, `ultimo_conduce`).

Las posiciones se guardan **relativas a la ventana** y junto con su tamaño. Si la ventana cambia de
tamaño, el macro se detiene y pide recalibrar o restaurar el tamaño: nunca hace clic «a ciegas».

## Estados de una factura

| Estado | Significado |
|---|---|
| Pendiente | Aún no se procesó. |
| En proceso | Se está procesando ahora. |
| Completada | Grabada (se vio la vista previa y cambió el número) e impresa o sin impresión solicitada. |
| Guardada (revisar impresión) | Grabada con seguridad, pero la impresión no se pudo confirmar. **No** se volverá a grabar. |
| Error (no grabada) | Se sabe que no se pulsó Ctrl+G (p. ej. escuela o producto incorrectos). |
| Necesita revisión | Se pulsó Ctrl+G y no hay prueba de guardado. Compruebe en SisFaCon (F5 Busca Facturas). |
| Omitida | Excluida por usted. |

## Si el programa se cierra de golpe
Al volver a abrirlo detecta la jornada interrumpida. Las facturas completadas no se repiten. La que
estaba en proceso pasa a «Necesita revisión» (indicando si ya se había enviado Ctrl+G). Usted decide
si la marca como pendiente o completada después de comprobarlo en SisFaCon.
