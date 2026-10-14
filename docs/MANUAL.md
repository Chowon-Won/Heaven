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

**Cantidad (obligatoria):** cada escuela tiene una cantidad fija que el programa escribe en la
columna Cantidad de SisFaCon. Póngala en el Excel (columna «Cantidad») y vuelva a importarlo
respondiendo **Sí** a «¿ACTUALIZAR?», o edite la escuela. Una escuela sin cantidad no puede entrar
en una jornada. La jornada guarda la cantidad del momento en que se crea.

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
4. **Escuelas**: marque las escuelas. *Seleccionar todas las activas*, *Desmarcar todas*, buscar,
   **rango «Desde la escuela … hasta …»** (*Solo este rango* deja marcadas únicamente esas;
   *Añadir este rango* las suma a las ya marcadas), y
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
* **Ejecutar rango**: elija «Desde la escuela» y «hasta» (por su número # en la jornada) y se
  procesan solo las pendientes de ese tramo; las completadas o en revisión se saltan.
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

## Calibración (con celdas arrastrables)

1. Abra SisFaCon → «Registro de Conduce a Centro Educativo». Déjela **siempre del mismo tamaño**
   (lo más sencillo: maximizada).
2. Seleccione a mano una escuela (F7) e introduzca a mano el código de un producto, **sin grabar**,
   para que los campos tengan texto. Al terminar use «Cancelar» en SisFaCon.
3. En Configuración pulse **«Calibrar con celdas (pantalla de conduce)»**. El AutoFacturador se
   minimiza y sobre SisFaCon aparece una capa con un **recuadro de color por campo**:
   * **Arrastre** cada recuadro (clic dentro) encima de su campo.
   * **Estírelo** desde la esquina inferior derecha para que cubra solo el texto del campo.
   * Flechas: mover 1 píxel · Mayús + flechas: cambiar tamaño · Tab: siguiente recuadro.
   * Clic derecho: quitar un campo que no use.
   * **Probar lectura** (en la barra) lee el recuadro seleccionado sin salir.
   * **Guardar** (o Enter). **Cancelar** (o Esc) no cambia nada.
4. Qué cubrir con cada recuadro:
   * **CÓDIGO del centro** → la casilla CODIGO (ej. 02968). *Obligatorio.*
   * **Celda azul Código** → la celda azul de la columna Código; el clic se hace en la cruz del
     centro. *Obligatorio.*
   * **Descripción (fila azul)** → la columna Descripción de la fila azul de entrada (donde
     aparece el nombre del producto al escribir su código).
   * **Cantidad (1.ª línea)** → la cantidad de la primera línea de la tabla de abajo (opcional:
     comprueba que la cantidad se escribió bien).
   * **«0 Linea(s)»** → el rótulo bajo la tabla.
   * **Último CONDUCE** → el texto «CONDUCE: FCR …» de ULTIMAS CONDUCE REGISTRADO.
   * **DIRECTOR** → la casilla DIRECTOR. El programa **no guarda ni muestra** el nombre: solo
     comprueba si tiene un nombre o si quedó en «-». Si queda en «-» (pasa tras algunos errores de
     SisFaCon), repite F7 y la selección de la escuela (hasta 3 veces). También lo comprueba justo
     antes de grabar. Se puede desactivar en Configuración.
   * **NOMBRE del centro** → opcional.
5. «Texto búsqueda» casi nunca hace falta (se detecta solo). Si se necesitara: pulse F7 en
   SisFaCon y luego **«Calibrar Texto búsqueda (con F7 abierto)»**.

La opción antigua **«Capturar con el ratón»** sigue disponible para un campo suelto.

Las posiciones se guardan **relativas a la ventana** y junto con su tamaño. Si la ventana cambia de
tamaño, el macro se detiene y pide recalibrar o restaurar el tamaño: nunca hace clic «a ciegas».

## Pantalla durante la automatización
En modo Prueba o Automático la ventana del AutoFacturador **se minimiza sola** al iniciar, para que
no tape SisFaCon (el OCR lee la pantalla y los clics deben caer en SisFaCon). En su lugar aparece un
**panel pequeño** con el estado, la escuela, el progreso y los botones Pausar, Seguir, Detener y
Ventana. El panel se coloca en una esquina que no tape ninguna zona calibrada; se puede arrastrar,
pero no lo ponga encima de los campos de SisFaCon. Al terminar, detenerse o mostrar un error, la
ventana vuelve a abrirse. Las preguntas («¿Grabar?», «¿Imprimir?») aparecen siempre encima.
Se desactiva en Configuración: «Al iniciar en modo real, minimizar y mostrar un panel pequeño».

La calibración, «Probar lectura» y «Probar conexión» también minimizan la ventana mientras leen la
pantalla; durante la cuenta atrás de «Capturar» las instrucciones salen en un aviso abajo a la derecha.

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
