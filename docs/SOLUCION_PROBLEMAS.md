# Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| «No se encuentra la ventana principal de SisFaCon» | SisFaCon cerrado o en otra pantalla | Abra «Registro de Conduce a Centro Educativo». Si el título es distinto, ajústelo en Configuración. |
| «Windows no permitió poner SisFaCon en primer plano» | Otra ventana bloquea el foco | Cierre ventanas emergentes, no use el ordenador mientras trabaja el macro. Ejecute ambos programas con el mismo nivel de permisos (los dos normales o los dos como administrador). |
| «La ventana mide … pero se calibró a …» | Cambió el tamaño o la resolución | Maximice SisFaCon igual que al calibrar o recalibre. |
| «No se pudo leer el contador Linea(s)» | El rótulo no es un control de Windows | Instale Tesseract (con idioma español) y pruebe la lectura; o desactive esa verificación y deje la de descripción. |
| Escuela incorrecta | La búsqueda devolvió otra fila | Compruebe que el código existe en SisFaCon. Pruebe «Buscar la escuela por: nombre». |
| Producto no reconocido | Falta un Enter, código distinto o descripción distinta | Revise el código y la «Descripción que muestra SisFaCon»; ajuste las teclas tras el código. |
| «No apareció la vista previa tras Ctrl+G» | SisFaCon tardó o no grabó | La factura queda en revisión. Compruebe en SisFaCon (F5). Aumente «Espera máxima tras Ctrl+G» si suele tardar. |
| Violación de acceso repetida | Fallo interno de SisFaCon | Tras 3 intentos el macro se detiene y deja el mensaje. Pulse OK usted, revise el formulario y, si hace falta, reinicie SisFaCon manualmente. |
| Ventana desconocida | Mensaje nuevo de SisFaCon | El macro no pulsa nada. Léalo y resuélvalo. Si es inofensivo, apréndalo en modo de prueba. |
| Modo automático deshabilitado | Falta superar la prueba | Siga `PRUEBA_UNA_FACTURA.md`. |
| La escala de Windows (125 %, 150 %) desplaza los clics | Coordenadas con escalado | El programa usa coordenadas reales de pantalla; recalibre tras cambiar la escala. |
| Al importar se pierden ceros | El archivo se guardó desde Excel como número | Use la plantilla CSV, o formatee la columna como Texto o con formato `00000`. |

## Archivos útiles
* Registro detallado: `%LOCALAPPDATA%\SisFaConAutoFacturador\registros\autofacturador.log`
* Capturas de pantalla de cada error: `...\capturas\`
* Base de datos: `...\autofacturador.sqlite3` (cópiela para hacer una copia de seguridad)

## Parada de emergencia
Ratón a la **esquina superior izquierda**. El macro aborta en la siguiente comprobación (antes de
cada tecla y durante las esperas) y la factura en curso queda con el estado más prudente.
