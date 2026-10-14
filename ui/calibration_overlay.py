"""Calibración con celdas arrastrables.

Una capa semitransparente cubre exactamente la ventana de SisFaCon. Cada campo
es un recuadro de color que se arrastra (clic dentro) y se estira (esquina
inferior derecha o Mayús+flechas). Las flechas lo mueven 1 píxel.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QVBoxLayout, QWidget)

from calibration import boxes_to_entries, entries_to_boxes, fields_for_window
from config import CALIBRATION_FIELDS

COLORS = ["#e11d48", "#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777"]
HANDLE = 12
SHORT = {
    "codigo_centro": "CÓDIGO del centro", "nombre_centro": "NOMBRE del centro",
    "ultimo_conduce": "Último CONDUCE (FCR …)", "contador_lineas": "«0 Linea(s)»",
    "celda_codigo_producto": "Celda azul Código", "descripcion_producto":
    "Descripción (1.ª línea)", "texto_busqueda": "Texto búsqueda",
}


class CalibrationOverlay(QWidget):
    saved = Signal(str)       # mensaje para la pantalla de Configuración
    closed = Signal()

    def __init__(self, app, ventana: str, window_rect, ratio: float):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.app, self.ventana, self.ratio = app, ventana, ratio or 1.0
        left, top, right, bottom = window_rect
        self.win_size = (right - left, bottom - top)           # píxeles reales
        self.setGeometry(round(left / self.ratio), round(top / self.ratio),
                         round((right - left) / self.ratio), round((bottom - top) / self.ratio))
        self.boxes: dict[str, QRect] = {
            n: QRect(*b) for n, b in entries_to_boxes(app.settings["calibracion"], ventana,
                                                      self.ratio).items()}
        self.removed: set[str] = set()
        self.colors = {n: QColor(COLORS[i % len(COLORS)])
                       for i, n in enumerate(fields_for_window(ventana))}
        self.selected = next(iter(self.boxes), None)
        self._drag = None          # (modo, nombre, punto inicial, rect inicial)
        self._build_toolbar()

    # ----------------------------------------------------------- barra
    def _build_toolbar(self):
        bar = QFrame(self)
        bar.setStyleSheet("QFrame { background: #0f4c81; border-radius: 8px; }"
                          "QLabel { color: white; } QPushButton { padding: 5px 10px; }")
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setMinimumWidth(420)
        self.add_box = QComboBox()
        add = QPushButton("Añadir")
        add.clicked.connect(self._add_back)
        test = QPushButton("Probar lectura")
        test.clicked.connect(self._test_read)
        save = QPushButton("Guardar")
        save.setStyleSheet("background:#16a34a; color:white; font-weight:700;")
        save.clicked.connect(self._save)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.close)
        move = QPushButton("⇅ Mover barra")
        move.clicked.connect(self._toggle_bar)
        row = QHBoxLayout()
        for w in (QLabel("Campo quitado:"), self.add_box, add, test, move, cancel, save):
            row.addWidget(w)
        lay = QVBoxLayout(bar)
        lay.addWidget(self.info)
        lay.addLayout(row)
        self.bar = bar
        self._bar_top = False
        self._refresh_bar()

    def _place_bar(self):
        self.bar.adjustSize()
        x = max(0, (self.width() - self.bar.width()) // 2)
        y = 4 if self._bar_top else max(0, self.height() - self.bar.height() - 4)
        self.bar.move(x, y)

    def _toggle_bar(self):
        self._bar_top = not self._bar_top
        self._place_bar()

    def _refresh_bar(self, extra: str = ""):
        name = self.selected
        desc = CALIBRATION_FIELDS[name]["descripcion"] if name else ""
        self.info.setText(
            "<b>Arrastre cada recuadro sobre su campo de SisFaCon</b> y estírelo desde la esquina "
            "inferior derecha. Flechas: mover 1 px · Mayús+flechas: cambiar tamaño · "
            "Clic derecho: quitar campo · Enter: guardar · Esc: cancelar."
            + (f"<br>Seleccionado: <b>{SHORT.get(name, name)}</b> — {desc}" if name else "")
            + (f"<br>{extra}" if extra else ""))
        self.add_box.clear()
        for n in sorted(self.removed):
            self.add_box.addItem(SHORT.get(n, n), n)
        self._place_bar()

    def showEvent(self, e):
        self._place_bar()
        self.activateWindow()
        self.setFocus()
        super().showEvent(e)

    # ----------------------------------------------------------- dibujo
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Fondo casi transparente: deja ver SisFaCon y recibe los clics.
        p.fillRect(self.rect(), QColor(0, 0, 0, 35))
        p.setPen(QPen(QColor("#0f4c81"), 3))
        p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        p.setFont(font)
        for name, r in self.boxes.items():
            if name in self.removed:
                continue
            color = self.colors[name]
            fill = QColor(color)
            fill.setAlpha(55 if name == self.selected else 30)
            p.fillRect(r, fill)
            p.setPen(QPen(color, 3 if name == self.selected else 2))
            p.drawRect(r)
            if CALIBRATION_FIELDS[name]["tipo"] == "punto":      # cruz en el punto de clic
                c = r.center()
                p.drawLine(c.x() - 6, c.y(), c.x() + 6, c.y())
                p.drawLine(c.x(), c.y() - 6, c.x(), c.y() + 6)
            handle = QRect(r.right() - HANDLE + 1, r.bottom() - HANDLE + 1, HANDLE, HANDLE)
            p.fillRect(handle, color)
            label = SHORT.get(name, name)
            tw = p.fontMetrics().horizontalAdvance(label) + 8
            ty = r.top() - 18 if r.top() > 20 else r.bottom() + 2
            p.fillRect(QRect(r.left(), ty, tw, 16), color)
            p.setPen(QColor("white"))
            p.drawText(QRect(r.left() + 4, ty, tw, 16), Qt.AlignVCenter, label)

    # ----------------------------------------------------------- ratón
    def _hit(self, pos: QPoint):
        order = [self.selected] + [n for n in self.boxes if n != self.selected]
        for name in order:
            if not name or name in self.removed:
                continue
            r = self.boxes[name]
            grip = QRect(r.right() - HANDLE, r.bottom() - HANDLE, HANDLE + 4, HANDLE + 4)
            if grip.contains(pos):
                return "resize", name
            if r.contains(pos):
                return "move", name
        return None, None

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        mode, name = self._hit(pos)
        if not name:
            return
        self.selected = name
        if e.button() == Qt.RightButton:
            menu = QMenu(self)
            menu.addAction(f"Quitar «{SHORT.get(name, name)}»", lambda: self._remove(name))
            menu.exec(e.globalPosition().toPoint())
            return
        self._drag = (mode, name, pos, QRect(self.boxes[name]))
        self._refresh_bar()
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._drag:
            mode, name, start, orig = self._drag
            d = pos - start
            r = QRect(orig)
            if mode == "move":
                r.moveTo(orig.topLeft() + d)
            else:
                r.setWidth(max(10, orig.width() + d.x()))
                r.setHeight(max(10, orig.height() + d.y()))
            self.boxes[name] = r.intersected(self.rect())
            self.update()
            return
        mode, _ = self._hit(pos)
        self.setCursor(Qt.SizeFDiagCursor if mode == "resize" else
                       Qt.SizeAllCursor if mode == "move" else Qt.ArrowCursor)

    def mouseReleaseEvent(self, _e):
        self._drag = None

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            self.close()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self._save()
            return
        if k == Qt.Key_Tab:
            names = [n for n in self.boxes if n not in self.removed]
            if names:
                i = names.index(self.selected) if self.selected in names else -1
                self.selected = names[(i + 1) % len(names)]
                self._refresh_bar()
                self.update()
            return
        moves = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if k in moves and self.selected:
            dx, dy = moves[k]
            r = QRect(self.boxes[self.selected])
            if e.modifiers() & Qt.ShiftModifier:
                r.setWidth(max(10, r.width() + dx))
                r.setHeight(max(10, r.height() + dy))
            else:
                r.translate(dx, dy)
            self.boxes[self.selected] = r
            self.update()
            return
        super().keyPressEvent(e)

    # ----------------------------------------------------------- acciones
    def _remove(self, name: str):
        self.removed.add(name)
        self.selected = next((n for n in self.boxes if n not in self.removed), None)
        self._refresh_bar()
        self.update()

    def _add_back(self):
        name = self.add_box.currentData()
        if name:
            self.removed.discard(name)
            self.selected = name
            self._refresh_bar()
            self.update()

    def _boxes_tuple(self):
        return {n: (r.x(), r.y(), r.width(), r.height()) for n, r in self.boxes.items()}

    def _save(self):
        cal = boxes_to_entries(self._boxes_tuple(), self.app.settings["calibracion"],
                               self.ventana, self.ratio, self.win_size, self.removed)
        self.app.settings.set("calibracion", cal)
        n = len([x for x in self.boxes if x not in self.removed])
        self.saved.emit(f"Calibración guardada con celdas: {n} campo(s). "
                        f"Ventana de SisFaCon: {self.win_size[0]}x{self.win_size[1]}.")
        self.close()

    def _test_read(self):
        """Oculta la capa, lee el recuadro seleccionado y vuelve a mostrarla."""
        name = self.selected
        if not name:
            return
        r = self.boxes[name]
        g = self.geometry()
        rect = (round((g.x() + r.x()) * self.ratio), round((g.y() + r.y()) * self.ratio),
                round(r.width() * self.ratio), round(r.height() * self.ratio))
        self.hide()

        def read():
            try:
                from window_detection import _OCR_ACCEPT, RealDriver
                drv = RealDriver(self.app.settings)
                ctrl = drv._control_text_at(*rect)
                ocr = drv.ocr.read_rect(rect, variants=True, accept=_OCR_ACCEPT.get(name))
                text = (f"Lectura de «{SHORT.get(name, name)}»: control de Windows = «{ctrl or '—'}» · "
                        f"OCR = «{ocr or '— (¿Tesseract instalado?)'}»")
            except Exception as exc:
                text = f"No se pudo leer: {exc}"
            self.show()
            self._refresh_bar(text)

        QTimer.singleShot(600, read)

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)


def open_overlay(app, ventana: str):
    """Crea la capa sobre la ventana de SisFaCon indicada. Lanza RuntimeError si no está abierta."""
    from window_detection import find_window_rect
    title = app.settings["titulo_ventana_principal" if ventana == "principal"
                         else "titulo_busqueda_cliente"]
    rect = find_window_rect(title)
    if not rect:
        raise RuntimeError(f"No se encuentra la ventana «{title}» de SisFaCon abierta (y sin "
                           "minimizar)." + (" Pulse F7 en SisFaCon para abrir la búsqueda."
                                            if ventana == "busqueda" else ""))
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    screen = QGuiApplication.primaryScreen()
    ratio = float(screen.devicePixelRatio() or 1.0)
    found = QGuiApplication.screenAt(QPoint(round(cx / ratio), round(cy / ratio)))
    if found is not None:
        ratio = float(found.devicePixelRatio() or ratio)
    return CalibrationOverlay(app, ventana, rect, ratio)
