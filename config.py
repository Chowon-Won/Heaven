"""Configuración de SisFaCon AutoFacturador.

Los ajustes se guardan en la tabla ``ajustes`` de la base de datos SQLite
(como JSON), de modo que persisten entre sesiones sin editar código.

Ningún valor de este archivo describe la posición de controles en pantalla:
las coordenadas se obtienen siempre con la herramienta de calibración.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

APP_NAME = "SisFaCon AutoFacturador"
APP_VERSION = "1.0.0"


def data_dir() -> Path:
    """Carpeta de datos del usuario (base de datos, registros, capturas).

    Se puede cambiar con la variable de entorno ``SISFACON_AF_DATA``.
    """
    override = os.environ.get("SISFACON_AF_DATA")
    if override:
        path = Path(override)
    elif sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        path = Path(base) / "SisFaConAutoFacturador"
    else:
        path = Path.home() / ".sisfacon_autofacturador"
    path.mkdir(parents=True, exist_ok=True)
    (path / "registros").mkdir(exist_ok=True)
    (path / "capturas").mkdir(exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Valores por defecto
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS: dict[str, Any] = {
    # --- Identificación de SisFaCon -------------------------------------
    "titulo_ventana_principal": "Registro de Conduce a Centro Educativo",
    "titulo_busqueda_cliente": "Seleccione un Cliente",
    "ejecutable": "sisfaconexpress.exe",
    "titulo_error_acceso": "SisFaCon Express - Menú Principal",

    # --- Teclas (formato pywinauto: ^ = Ctrl, % = Alt, + = Mayús) -------
    "tecla_buscar_cliente": "{F7}",
    # Botón de respaldo si F7 no abre la búsqueda (texto del botón en SisFaCon).
    "boton_buscar_cliente": "Buscar Centro",
    "tecla_confirmar_busqueda": "{ENTER}",
    "tecla_grabar": "^g",
    # Teclas que se pulsan después de escribir el código del producto.
    "teclas_tras_codigo_producto": "{ENTER}",
    # Tras el código y Enter, SisFaCon deja seleccionada la Cantidad: se escribe
    # la cantidad de la escuela y se pulsan estas teclas para añadir la línea.
    "teclas_tras_cantidad": "{ENTER}",
    # True: «descripcion_producto» está calibrada sobre la fila azul de entrada
    # (aparece al escribir el código y se vacía al añadir la línea).
    # False: está sobre la primera línea de la tabla inferior.
    "descripcion_en_fila_entrada": True,

    # --- Búsqueda de escuela ---------------------------------------------
    # "codigo" o "nombre": qué se escribe en «Texto búsqueda».
    "buscar_escuela_por": "codigo",
    "verificar_nombre_escuela": False,
    # Si la búsqueda por código no encuentra la escuela, reintentar por nombre
    # (o al revés). Seguro: aún no se ha introducido el producto.
    "reintentar_busqueda_alternativa": True,
    # CODIGO que muestra SisFaCon en un formulario nuevo (cliente <<CONTADO>>).
    # Se usa para confirmar que el formulario está limpio cuando el contador
    # «Linea(s)» no se puede leer. Vacío = no comprobar.
    "codigo_formulario_nuevo": "PERSONAL",
    "umbral_similitud_nombre": 0.80,

    # --- Producto --------------------------------------------------------
    "verificar_descripcion_producto": True,
    "verificar_contador_lineas": True,
    # Si el contador «Linea(s)» no se puede leer (OCR), seguir verificando
    # solo por la descripción del producto en lugar de detenerse.
    "contador_lineas_opcional": True,
    "umbral_similitud_producto": 0.75,

    # --- Guardado (flujo confirmado por el usuario) ------------------------
    # Ctrl+G abre la ventana «Preview - [No name]» con el conduce grabado.
    # Que aparezca esa ventana es la evidencia principal del guardado.
    "titulo_vista_previa": "Preview",
    # Además, si el rótulo «ULTIMAS CONDUCE REGISTRADO» está calibrado, se
    # comprueba que cambió al cerrar la vista previa.
    "exigir_cambio_ultimo_conduce": True,

    # --- Impresión (flujo confirmado) ------------------------------------
    # En la vista previa: F9 -> diálogo «Print» -> Enter/OK -> Esc.
    "imprimir": True,
    "confirmar_antes_de_imprimir": False,
    "tecla_imprimir": "{F9}",
    "titulos_dialogo_impresion": ["Print", "Imprimir"],
    # Tras Ctrl+G SisFaCon pregunta si se imprime: se acepta y se abre la vista
    # previa. Se reconoce por estas palabras en el título o el mensaje.
    "textos_pregunta_imprimir": ["IMPRIMIR", "IMPRIME", "IMPRESION"],
    "tecla_aceptar_impresion": "{ENTER}",
    "tecla_cerrar_vista_previa": "{ESC}",
    "espera_tras_imprimir": 2.0,

    # --- Tiempos (segundos) ---------------------------------------------
    "intervalo_sondeo": 0.25,
    "espera_tras_tecla": 0.4,
    "timeout_ventana": 10.0,
    "timeout_guardado": 20.0,
    "timeout_impresion": 30.0,
    "espera_estabilizacion": 1.0,

    # --- Recuperación ----------------------------------------------------
    "max_intentos_recuperacion": 3,

    # --- Seguridad -------------------------------------------------------
    "prueba_superada": False,
    "confirmar_cada_escuela": False,
    # En modo real: minimizar la ventana principal al iniciar y mostrar un panel
    # pequeño en una esquina que no tape las zonas calibradas de SisFaCon.
    "minimizar_al_ejecutar": True,
    "capturas_en_error": True,

    # --- OCR -------------------------------------------------------------
    "ruta_tesseract": "",
    "idioma_ocr": "spa+eng",

    # --- Mensajes informativos adicionales --------------------------------
    # Ventanas que el usuario declaró inofensivas desde el modo de prueba.
    # Cada regla: {nombre, titulo_contiene, texto_contiene, accion}
    # Cualquier otra ventana desconocida detiene la automatización.
    "reglas_dialogos": [],

    # --- Calibración -----------------------------------------------------
    # Cada entrada: {"ventana": "principal"|"busqueda",
    #                "tipo": "punto"|"region", "x","y","w","h",
    #                "metodo": "auto"|"control"|"ocr",
    #                "ancho_ventana","alto_ventana"}
    # Coordenadas relativas a la esquina superior izquierda de la ventana.
    "calibracion": {},

    # Ventanas del proceso visibles en reposo (no son diálogos).
    "ventanas_en_reposo": [],

    # Configuraciones frecuentes guardadas desde «Nueva jornada».
    "modo_ultimo": "SIMULADO",
}

# Campos que pueden calibrarse y su descripción para la interfaz.
CALIBRATION_FIELDS: dict[str, dict[str, str]] = {
    "codigo_centro": {
        "ventana": "principal", "tipo": "region",
        "descripcion": "Campo CODIGO del centro educativo (ej. 02968)",
    },
    "nombre_centro": {
        "ventana": "principal", "tipo": "region",
        "descripcion": "Campo NOMBRE del centro educativo",
    },
    "ultimo_conduce": {
        "ventana": "principal", "tipo": "region",
        "descripcion": "Rótulo «CONDUCE: FCR ...» de ULTIMAS CONDUCE REGISTRADO",
    },
    "contador_lineas": {
        "ventana": "principal", "tipo": "region",
        "descripcion": "Texto «0 Linea(s)» debajo de la tabla",
    },
    "celda_codigo_producto": {
        "ventana": "principal", "tipo": "punto",
        "descripcion": "Celda azul de la columna Código (fila de entrada)",
    },
    "descripcion_producto": {
        "ventana": "principal", "tipo": "region",
        "descripcion": "Descripción en la FILA AZUL DE ENTRADA (aparece al escribir el código "
                       "del producto y se vacía al añadir la línea)",
    },
    "cantidad_linea": {
        "ventana": "principal", "tipo": "region",
        "descripcion": "Cantidad de la PRIMERA LÍNEA de la tabla inferior (opcional: "
                       "comprueba que se escribió bien)",
    },
    "texto_busqueda": {
        "ventana": "busqueda", "tipo": "punto",
        "descripcion": "Campo «Texto búsqueda» (solo si no se detecta solo)",
    },
}

# Campos imprescindibles antes de trabajar con SisFaCon real.
REQUIRED_CALIBRATION = ("codigo_centro", "celda_codigo_producto")


class Settings:
    """Acceso tipado a los ajustes persistidos en la base de datos."""

    def __init__(self, db=None):
        self._db = db
        self._values: dict[str, Any] = copy.deepcopy(DEFAULT_SETTINGS)
        if db is not None:
            self.reload()

    def reload(self) -> None:
        self._values = copy.deepcopy(DEFAULT_SETTINGS)
        if self._db is None:
            return
        for row in self._db.query("SELECT clave, valor FROM ajustes"):
            try:
                self._values[row["clave"]] = json.loads(row["valor"])
            except (TypeError, json.JSONDecodeError):
                continue

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._values:
            return self._values[key]
        return DEFAULT_SETTINGS.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value
        if self._db is not None:
            self._db.execute(
                "INSERT INTO ajustes(clave, valor) VALUES(?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def update(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.set(key, value)

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._values)

    def reset_defaults(self) -> None:
        """Restablece ajustes, pero conserva calibración y reglas aprendidas."""
        keep = {k: self._values.get(k) for k in
                ("calibracion", "reglas_dialogos", "ventanas_en_reposo")}
        if self._db is not None:
            self._db.execute("DELETE FROM ajustes")
        self._values = copy.deepcopy(DEFAULT_SETTINGS)
        self.update({k: v for k, v in keep.items() if v})
