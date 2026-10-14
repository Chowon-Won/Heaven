# SisFaCon AutoFacturador

Herramienta de escritorio para Windows 10/11 que **controla SisFaCon Express** y automatiza la
preparación diaria de conduces para centros educativos. No sustituye a SisFaCon ni accede a su base
de datos: maneja la aplicación igual que lo haría una persona, verificando cada paso.

> **Principio de diseño:** la exactitud está por encima de la velocidad. Ante cualquier duda
> (escuela distinta, producto no reconocido, ventana desconocida, guardado incierto) el macro se
> detiene y le explica qué pasó. **Nunca vuelve a grabar una factura cuyo guardado es incierto.**

---

## 1. Flujo que automatiza (confirmado en su equipo)

| Paso | Acción en SisFaCon | Cómo se verifica |
|---|---|---|
| 1 | Formulario «Registro de Conduce a Centro Educativo» listo | Ventana encontrada, sin diálogos abiertos, «0 Linea(s)» |
| 2 | **F7** → «Seleccione un Cliente» → escribe el código en «Texto búsqueda» → **Enter** | El campo CODIGO muestra exactamente el código esperado (con ceros) |
| 3 | Clic en la celda azul **Código** → código del producto → **Enter** → aparece la descripción y queda seleccionada la Cantidad → escribe la **cantidad de la escuela** → **Enter** | La descripción coincide; «1 Linea(s)»; (opcional) la cantidad de la línea coincide |
| 4 | **Ctrl+G** | Se abre la ventana **«Preview - [No name]»** (prueba de que se grabó) |
| 5 | **F9** en la vista previa → diálogo **«Print»** → **OK** | El diálogo se cierra sin errores |
| 6 | **Esc** cierra la vista previa | El número de «ULTIMAS CONDUCE REGISTRADO» cambió |

La **violación de acceso** («Violación de acceso en la dirección … en módulo 'sisfaconexpress.exe'»)
se reconoce por el texto y el módulo, no por las direcciones. Se pulsa OK **solo** en ese mensaje y:

* si ocurrió **antes** de Ctrl+G → vuelve a seleccionar la misma escuela con F7 y sigue;
* si ocurrió **después** de Ctrl+G y no hay prueba de guardado → la factura queda **«Necesita
  revisión»** y la jornada se detiene (no se repite el guardado);
* si ocurrió al imprimir → la factura ya está grabada; solo se reintenta F9 si todavía no se había
  pulsado OK en el diálogo de impresión;
* máximo **3 intentos** por factura (configurable); después se detiene y deja el mensaje visible.

## 2. Instalación

### Opción A — instalador único (recomendado)

1. En un PC con Windows 10/11 e Internet, descomprima el ZIP y haga doble clic en
   **`CREAR_INSTALADOR.bat`**. El script hace todo solo:
   * instala Python 3.12 (solo para compilar, si no lo tiene) y las bibliotecas;
   * ejecuta las pruebas automáticas;
   * empaqueta el programa con PyInstaller (incluye Python dentro);
   * descarga Tesseract OCR y los idiomas español/inglés;
   * instala Inno Setup (puede pedir permiso de administrador) y genera el instalador.
2. Resultado: **`build\salida\SisFaConAutoFacturador_Setup_1.0.0.exe`**, un único archivo.
3. Ese `Setup.exe` se instala en cualquier PC con Windows 10/11 (x64) **sin Python**: crea accesos
   directos, instala Tesseract si falta (casilla opcional) y deja manual y plantillas en el menú Inicio.
   Al desinstalar, sus datos (escuelas, productos, historial) se conservan.

Alternativa: si sube el proyecto a GitHub, la acción `.github/workflows/instalador-windows.yml`
genera el mismo instalador en la nube (Actions → Run workflow → Artifacts).

### Opción B — ejecutar desde el código

1. Instale **Python 3.12** desde <https://www.python.org/downloads/> (marque *Add python.exe to PATH*).
2. Descomprima `SisFaConAutoFacturador.zip` en una carpeta, por ejemplo `C:\AutoFacturador`.
3. Doble clic en **`instalar.bat`** (crea un entorno `.venv` e instala las dependencias).
4. *(Opcional, recomendado)* Instale **Tesseract OCR** para leer los rótulos que no son controles de
   Windows (por ejemplo «0 Linea(s)» o «CONDUCE: FCR …»):
   <https://github.com/UB-Mannheim/tesseract/wiki> — durante la instalación añada el idioma
   *Spanish*. El programa lo busca en `C:\Program Files\Tesseract-OCR\`.

## 3. Ejecución

* Doble clic en **`ejecutar.bat`**, o
* `.venv\Scripts\python main.py`

Los datos (base SQLite, registros y capturas de error) se guardan en
`%LOCALAPPDATA%\SisFaConAutoFacturador\`. Persisten entre sesiones.

## 4. Primeros pasos (resumen — ver `docs/MANUAL.md`)

1. **Escuelas**: añádalas o importe `plantillas/plantilla_escuelas.csv` (códigos como texto: `02968`).
2. **Productos**: revise los ejemplos (Pan 1000, Pan de zanahoria 1005). En «Descripción que muestra
   SisFaCon» ponga el texto exacto que aparece al teclear el código.
3. **Configuración → Calibración**: marque los campos de SisFaCon (código del centro, celda Código,
   contador de líneas, descripción, último conduce).
4. **Nueva jornada** → cree una jornada **simulada** y ejecútela para practicar.
5. Cree una jornada **real** y haga **una factura en Modo de prueba** (`docs/PRUEBA_UNA_FACTURA.md`).
6. Si la prueba es correcta, se habilita el **Modo automático**.

## 5. Modos

| Modo | Qué hace |
|---|---|
| Simulado | Imita SisFaCon en memoria. No graba ni imprime nada real. |
| Prueba | Una sola escuela. Pregunta antes de grabar y antes de imprimir, y al final si todo salió bien. Permite «aprender» mensajes informativos inofensivos. |
| Automático | Procesa las escuelas seleccionadas. Bloqueado hasta superar la prueba. |

Controles: Iniciar, Pausar, Reanudar, Detener, «Confirmar la siguiente operación», ejecutar una
escuela, un **rango (desde la escuela X hasta la Y)**, un grupo de prueba (primeras N) o todas.

**Parada de emergencia:** mueva el ratón a la **esquina superior izquierda** de la pantalla
(mecanismo FAILSAFE de PyAutoGUI, comprobado antes de cada pulsación y durante cada espera).
«Detener» termina el paso seguro actual: nunca abandona una factura entre Ctrl+G y la impresión.

## 6. Pruebas

```
ejecutar_pruebas.bat          (o: .venv\Scripts\python -m pytest tests\unit -v)
```

* `tests/unit/` — 45 pruebas sin SisFaCon (catálogos, ceros iniciales, 48 escuelas, duplicados,
  escuela/producto incorrectos, violación de acceso, límite de intentos, guardado incierto, no
  imprimir antes de grabar, pausa/reanudar, ventanas desconocidas, jornada interrumpida, historial
  tras eliminar, exportación). **Todas pasan** con el SisFaCon simulado.
* `tests/real/` — comprobaciones de **solo lectura** contra SisFaCon real (no graban). Se omiten salvo
  que defina `SISFACON_REAL=1`. **No se han ejecutado todavía**: no había acceso a SisFaCon durante
  el desarrollo.

## 7. Crear un .exe

```
crear_exe.bat
```

Genera `dist\SisFaConAutoFacturador\SisFaConAutoFacturador.exe` (copie la carpeta completa). Tesseract,
si lo usa, se instala aparte.

## 8. Estructura

```
main.py                 Punto de entrada (interfaz)
app_context.py          Crea base de datos, ajustes y gestores
config.py               Ajustes por defecto (persistidos en SQLite)
database.py             Esquema SQLite (escuelas, productos, jornadas, facturas, eventos)
catalog_base.py         CRUD común, borrado lógico, importación
school_manager.py       Escuelas
product_manager.py      Productos
day_manager.py          Jornadas, estados de factura, jornadas interrumpidas
import_export.py        CSV / Excel sin perder ceros
state_machine.py        Máquina de estados (IDLE … COMPLETED)
automation.py           Motor de facturación paso a paso
window_detection.py     Control de SisFaCon real (pywinauto + OCR de respaldo)
error_recovery.py       Clasificación de ventanas y política de recuperación
verification.py         Comparación de códigos, nombres, «Linea(s)», número de conduce
simulator.py            SisFaCon simulado con inyección de fallos
calibration.py          Herramienta de calibración
ocr.py                  OCR opcional (Tesseract)
logging_manager.py      Registro de eventos (BD + archivo) y exportación CSV
ui/                     Interfaz PySide6 (7 pestañas)
tests/unit, tests/real  Pruebas
plantillas/             Plantillas CSV
docs/                   Manual, solución de problemas, prueba de una factura
```

## 9. Lo que queda por confirmar en su equipo

Estas cosas dependen de SisFaCon y se ajustan en **Configuración** sin tocar código:

* Si tras teclear el código del producto basta un **Enter** o hacen falta dos (`{ENTER}{ENTER}`).
* Si los campos se leen como controles de Windows o necesitan OCR (lo indica «Probar lectura»).
* La **cantidad** no se modifica: se usa la que SisFaCon propone (1). Si necesita otra, dígalo y se
  añade al flujo con su verificación.
