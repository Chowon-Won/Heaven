"""Configuración: ajustes, calibración, reglas aprendidas y diagnóstico."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from config import CALIBRATION_FIELDS, REQUIRED_CALIBRATION
from ui.common import confirm, error, fill_table, make_table

# (clave, etiqueta, tipo, opciones)
FIELDS = [
    ("Identificación de SisFaCon", [
        ("titulo_ventana_principal", "Título de la ventana principal (contiene)", "text"),
        ("titulo_busqueda_cliente", "Título de la búsqueda de clientes", "text"),
        ("titulo_vista_previa", "Título de la vista previa (empieza por)", "text"),
        ("ejecutable", "Ejecutable / módulo", "text"),
    ]),
    ("Teclas (formato: {F7}, {ENTER}, {ESC}, ^g = Ctrl+G)", [
        ("tecla_buscar_cliente", "Buscar cliente", "text"),
        ("tecla_confirmar_busqueda", "Confirmar búsqueda", "text"),
        ("teclas_tras_codigo_producto", "Tras escribir el código de producto", "text"),
        ("tecla_grabar", "Grabar", "text"),
        ("tecla_imprimir", "Imprimir (en la vista previa)", "text"),
        ("tecla_cerrar_vista_previa", "Cerrar vista previa", "text"),
    ]),
    ("Verificaciones", [
        ("buscar_escuela_por", "Buscar la escuela por", "choice", ["codigo", "nombre"]),
        ("reintentar_busqueda_alternativa", "Si no encuentra la escuela, reintentar por el otro dato", "bool"),
        ("codigo_formulario_nuevo", "Código de un formulario nuevo (vacío = no comprobar)", "text"),
        ("verificar_nombre_escuela", "Verificar también el nombre de la escuela", "bool"),
        ("verificar_contador_lineas", "Verificar contador «Linea(s)»", "bool"),
        ("contador_lineas_opcional", "Si el contador no se puede leer, verificar solo la descripción", "bool"),
        ("verificar_descripcion_producto", "Verificar descripción del producto", "bool"),
        ("exigir_cambio_ultimo_conduce", "Exigir que cambie «ULTIMAS CONDUCE REGISTRADO»", "bool"),
        ("umbral_similitud_producto", "Similitud mínima de la descripción (0-1)", "float"),
    ]),
    ("Impresión", [
        ("imprimir", "Imprimir cada conduce (F9 → OK → Esc)", "bool"),
        ("confirmar_antes_de_imprimir", "Pedir confirmación antes de imprimir", "bool"),
    ]),
    ("Tiempos (segundos) y recuperación", [
        ("timeout_ventana", "Espera máxima de ventanas", "float"),
        ("timeout_guardado", "Espera máxima tras Ctrl+G", "float"),
        ("timeout_impresion", "Espera máxima de impresión", "float"),
        ("espera_tras_tecla", "Pausa tras escribir", "float"),
        ("espera_estabilizacion", "Estabilización tras cambios", "float"),
        ("espera_tras_imprimir", "Espera tras imprimir", "float"),
        ("intervalo_sondeo", "Intervalo de comprobación", "float"),
        ("max_intentos_recuperacion", "Máximo de intentos de recuperación", "int"),
    ]),
    ("OCR y registros", [
        ("ruta_tesseract", "Ruta de tesseract.exe (vacío = automática)", "text"),
        ("idioma_ocr", "Idioma OCR", "text"),
        ("capturas_en_error", "Guardar captura de pantalla en cada error", "bool"),
        ("minimizar_al_ejecutar", "Al iniciar en modo real, minimizar y mostrar un panel pequeño", "bool"),
    ]),
]


class SettingsTab(QWidget):
    def __init__(self, app, ctl, parent=None):
        super().__init__(parent)
        self.app, self.ctl = app, ctl
        self.inputs = {}
        inner = QWidget()
        v = QVBoxLayout(inner)
        for title, fields in FIELDS:
            box = QGroupBox(title)
            form = QFormLayout(box)
            for spec in fields:
                key, label, kind = spec[:3]
                w = self._make_input(kind, spec[3] if len(spec) > 3 else None)
                self.inputs[key] = (w, kind)
                form.addRow(label, w)
            v.addWidget(box)
        save = QPushButton("Guardar configuración", objectName="Primary")
        save.clicked.connect(self.save)
        reset = QPushButton("Restablecer valores por defecto")
        reset.clicked.connect(self.reset)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addWidget(reset)
        row.addStretch(1)
        v.addLayout(row)
        v.addWidget(self._calibration_box())
        v.addWidget(self._rules_box())
        v.addWidget(self._diag_box())
        v.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        lay = QVBoxLayout(self)
        lay.addWidget(scroll)
        self.load()

    # ---------------------------------------------------------- ajustes
    def _make_input(self, kind, options):
        if kind == "bool":
            return QCheckBox()
        if kind == "int":
            return QSpinBox(minimum=1, maximum=10)
        if kind == "float":
            w = QDoubleSpinBox(minimum=0.0, maximum=300.0, singleStep=0.25, decimals=2)
            return w
        if kind == "choice":
            w = QComboBox()
            w.addItems(options)
            return w
        return QLineEdit()

    def load(self):
        s = self.app.settings
        for key, (w, kind) in self.inputs.items():
            val = s[key]
            if kind == "bool":
                w.setChecked(bool(val))
            elif kind in ("int", "float"):
                w.setValue(val)
            elif kind == "choice":
                w.setCurrentText(str(val))
            else:
                w.setText(str(val))
        self.refresh_calibration()
        self.refresh_rules()

    def save(self):
        values = {}
        for key, (w, kind) in self.inputs.items():
            if kind == "bool":
                values[key] = w.isChecked()
            elif kind == "int":
                values[key] = w.value()
            elif kind == "float":
                values[key] = float(w.value())
            elif kind == "choice":
                values[key] = w.currentText()
            else:
                values[key] = w.text().strip()
        if not values["verificar_contador_lineas"] and not values["verificar_descripcion_producto"]:
            return error(self, "Debe quedar activa al menos una verificación de producto.")
        self.app.settings.update(values)
        QMessageBox.information(self, "Guardado", "Configuración guardada.")

    def reset(self):
        if confirm(self, "Restablecer", "¿Restablecer todos los ajustes? La calibración y las "
                   "reglas aprendidas se conservan; la prueba superada se reinicia."):
            self.app.settings.reset_defaults()
            self.load()

    # ------------------------------------------------------- calibración
    def _calibration_box(self) -> QGroupBox:
        box = QGroupBox("Calibración de pantalla (SisFaCon)")
        v = QVBoxLayout(box)
        v.addWidget(QLabel(
            "Abra SisFaCon en «Registro de Conduce a Centro Educativo» con el MISMO tamaño de ventana "
            "que usará siempre (por ejemplo, maximizada). Pulse «Capturar», coloque el ratón donde se "
            "indica y espere la cuenta atrás. Para regiones se capturan dos esquinas.\n"
            "Recomendado: primero seleccione una escuela e introduzca un producto a mano para que los "
            "campos tengan texto, y luego pulse «Probar lectura».", objectName="Hint"))
        self.cal_table = make_table(["Campo", "Descripción", "Estado", "Método"], multi=False)
        v.addWidget(self.cal_table)
        row = QHBoxLayout()
        self.cal_btn = QPushButton("Capturar", objectName="Primary")
        self.cal_btn.clicked.connect(self.start_capture)
        test = QPushButton("Probar lectura")
        test.clicked.connect(self.test_field)
        self.method = QComboBox()
        self.method.addItems(["auto", "control", "ocr"])
        set_m = QPushButton("Aplicar método")
        set_m.clicked.connect(self.apply_method)
        remove = QPushButton("Borrar")
        remove.clicked.connect(self.remove_field)
        for w in (self.cal_btn, test, QLabel("Método:"), self.method, set_m, remove):
            row.addWidget(w)
        row.addStretch(1)
        v.addLayout(row)
        self.cal_status = QLabel()
        self.cal_status.setWordWrap(True)
        v.addWidget(self.cal_status)
        self._capture = None
        self._timer = QTimer(self, interval=1000, timeout=self._tick)
        self._hint = QLabel(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus)
        self._hint.setAttribute(Qt.WA_ShowWithoutActivating)
        self._hint.setStyleSheet("background:#0f4c81; color:white; font-size:12pt; "
                                 "font-weight:600; padding:10px; border-radius:6px;")
        return box

    def refresh_calibration(self):
        cal = self.app.settings["calibracion"] or {}
        rows, ids = [], []
        for name, meta in CALIBRATION_FIELDS.items():
            e = cal.get(name)
            req = " (obligatorio)" if name in REQUIRED_CALIBRATION else ""
            state = (f"OK · ventana {e['ancho_ventana']}x{e['alto_ventana']}" if e else "Sin calibrar")
            rows.append([name, meta["descripcion"] + req, state, (e or {}).get("metodo", "")])
            ids.append(name)
        fill_table(self.cal_table, rows, ids,
                   [None if cal.get(n) else "#b91c1c" for n in ids])

    def _selected_field(self) -> str | None:
        r = self.cal_table.currentRow()
        if r < 0:
            error(self, "Seleccione un campo de la tabla.")
            return None
        return self.cal_table.item(r, 0).data(Qt.UserRole)

    def _calibrator(self):
        if not sys.platform.startswith("win"):
            raise RuntimeError("La calibración solo funciona en Windows con SisFaCon abierto.")
        from calibration import Calibrator
        from window_detection import RealDriver
        return Calibrator(self.app.settings, RealDriver(self.app.settings))

    def start_capture(self):
        name = self._selected_field()
        if not name:
            return
        try:
            cal = self._calibrator()
        except Exception as exc:
            return error(self, str(exc))
        kind = CALIBRATION_FIELDS[name]["tipo"]
        steps = ["el CENTRO del elemento"] if kind == "punto" else \
            ["la esquina SUPERIOR IZQUIERDA", "la esquina INFERIOR DERECHA"]
        self._capture = {"name": name, "cal": cal, "steps": steps, "points": [], "count": 5}
        self.cal_btn.setEnabled(False)
        # Se aparta la ventana para que SisFaCon quede a la vista; las instrucciones
        # se muestran en un aviso pequeño que no tapa SisFaCon.
        self.window().showMinimized()
        self._hint.show()
        self._timer.start()
        self._tick()

    def _tick(self):
        c = self._capture
        if not c:
            return
        step = c["steps"][len(c["points"])]
        if c["count"] > 0:
            text = (f"«{c['name']}»: coloque el ratón en {step}. "
                    f"Captura en {c['count']} s…")
            self.cal_status.setText(text)
            self._show_hint(text)
            c["count"] -= 1
            return
        from calibration import cursor_position
        c["points"].append(cursor_position())
        if len(c["points"]) < len(c["steps"]):
            c["count"] = 4
            return
        self._timer.stop()
        self.cal_btn.setEnabled(True)
        self._capture = None
        self._hint.hide()
        self._restore_window()
        try:
            if len(c["points"]) == 1:
                entry = c["cal"].save_point(c["name"], c["points"][0])
            else:
                entry = c["cal"].save_region(c["name"], *c["points"])
            self.cal_status.setText(f"«{c['name']}» calibrado: {entry}")
        except Exception as exc:
            self.cal_status.setText(f"No se pudo calibrar: {exc}")
        self.refresh_calibration()

    def test_field(self):
        name = self._selected_field()
        if not name:
            return

        def read():
            try:
                return self._calibrator().test_read(name)
            except Exception as exc:
                return f"Error: {exc}"

        self._with_screen_free(read, lambda r: QMessageBox.information(
            self, f"Lectura de {name}", r))

    # --------------------------------------- dejar SisFaCon a la vista
    def _show_hint(self, text: str) -> None:
        self._hint.setText(text)
        self._hint.adjustSize()
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self._hint.move(geo.right() - self._hint.width() - 12,
                        geo.bottom() - self._hint.height() - 12)

    def _restore_window(self) -> None:
        win = self.window()
        win.showNormal()
        win.raise_()
        win.activateWindow()

    def _with_screen_free(self, work, done) -> None:
        """Minimiza la ventana, espera a que Windows redibuje SisFaCon, ejecuta
        ``work`` (lee la pantalla) y vuelve a mostrar la ventana con el resultado."""
        self.window().showMinimized()

        def run():
            result = work()
            self._restore_window()
            done(result)

        QTimer.singleShot(800, run)

    def apply_method(self):
        name = self._selected_field()
        if name:
            cal = dict(self.app.settings["calibracion"] or {})
            if name in cal:
                cal[name] = {**cal[name], "metodo": self.method.currentText()}
                self.app.settings.set("calibracion", cal)
            self.refresh_calibration()

    def remove_field(self):
        name = self._selected_field()
        if name and confirm(self, "Borrar", f"¿Borrar la calibración de «{name}»?"):
            cal = dict(self.app.settings["calibracion"] or {})
            cal.pop(name, None)
            self.app.settings.set("calibracion", cal)
            self.refresh_calibration()

    # --------------------------------------------------- reglas aprendidas
    def _rules_box(self) -> QGroupBox:
        box = QGroupBox("Mensajes informativos aprendidos (se aceptan con OK automáticamente)")
        v = QVBoxLayout(box)
        self.rules = make_table(["Título contiene", "Texto contiene"], multi=False)
        self.rules.setMaximumHeight(140)
        delete = QPushButton("Eliminar regla")
        delete.clicked.connect(self.delete_rule)
        v.addWidget(self.rules)
        v.addWidget(delete)
        return box

    def refresh_rules(self):
        rules = self.app.settings["reglas_dialogos"] or []
        fill_table(self.rules, [[r.get("titulo_contiene", ""), r.get("texto_contiene", "")]
                                for r in rules], list(range(len(rules))))

    def delete_rule(self):
        r = self.rules.currentRow()
        rules = list(self.app.settings["reglas_dialogos"] or [])
        if 0 <= r < len(rules) and confirm(self, "Eliminar", "¿Eliminar esta regla?"):
            rules.pop(r)
            self.app.settings.set("reglas_dialogos", rules)
            self.refresh_rules()

    # --------------------------------------------------------- diagnóstico
    def _diag_box(self) -> QGroupBox:
        box = QGroupBox("Diagnóstico y seguridad")
        v = QVBoxLayout(box)
        self.test_state = QLabel()
        row = QHBoxLayout()
        probe = QPushButton("Probar conexión con SisFaCon")
        probe.clicked.connect(self.probe)
        relock = QPushButton("Bloquear de nuevo el modo automático")
        relock.clicked.connect(self.relock)
        folder = QPushButton("Abrir carpeta de datos")
        folder.clicked.connect(self.open_folder)
        for b in (probe, relock, folder):
            row.addWidget(b)
        row.addStretch(1)
        v.addWidget(self.test_state)
        v.addLayout(row)
        v.addWidget(QLabel(f"Datos: {self.app.data_dir}", objectName="Hint"))
        self._update_test_state()
        return box

    def _update_test_state(self):
        ok = bool(self.app.settings["prueba_superada"])
        self.test_state.setText("Modo automático: " + ("HABILITADO (prueba superada)" if ok
                                                     else "bloqueado hasta superar la prueba"))

    def showEvent(self, e):
        self._update_test_state()
        super().showEvent(e)

    def relock(self):
        self.app.settings.set("prueba_superada", False)
        self._update_test_state()

    def open_folder(self):
        if self.app.data_dir and sys.platform.startswith("win"):
            os.startfile(str(self.app.data_dir))

    def probe(self):
        def work():
            try:
                from window_detection import RealDriver
                from error_recovery import classify_window
                drv = RealDriver(self.app.settings)
                if not drv.find_main():
                    return False, ("No se encontró la ventana «Registro de Conduce a Centro "
                                   "Educativo». Ábrala en SisFaCon.")
                lines = [f"Ventana principal encontrada: {drv.window_rect('principal')}"]
                for w in drv.capture_baseline():
                    lines.append(f"Ventana pendiente: {w.describe()} → "
                                 f"{classify_window(w, self.app.settings).kind.value}")
                for name in ("codigo_centro", "nombre_centro", "ultimo_conduce",
                             "contador_lineas", "descripcion_producto"):
                    if drv.is_calibrated(name):
                        lines.append(f"{name}: «{drv.read_field(name)}»")
                lines.append("OCR disponible: " + ("sí" if drv.ocr.available() else
                                                   "no (instale Tesseract si algún campo lo necesita)"))
                return True, "\n".join(lines)
            except Exception as exc:
                return False, f"No se pudo comprobar: {exc}"

        def done(result):
            ok, text = result
            if ok:
                QMessageBox.information(self, "Conexión con SisFaCon", text)
            else:
                error(self, text)

        self._with_screen_free(work, done)
