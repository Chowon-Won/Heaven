"""Panel pequeño y siempre visible mientras el macro controla SisFaCon.

La ventana principal se minimiza para no tapar SisFaCon; este panel se coloca
en una esquina de la pantalla que no cubra ninguna zona calibrada (lo que el
macro lee con OCR o donde hace clic). Nunca usa la esquina superior izquierda,
reservada para la parada de emergencia.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from window_detection import calibrated_screen_rects, find_window_rect

WIDTH, HEIGHT, MARGIN = 360, 132, 8


def _intersects(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class MiniPanel(QWidget):
    def __init__(self, app, ctl, on_show_main):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.app, self.ctl = app, ctl
        self.setFixedSize(WIDTH, HEIGHT)
        self.setObjectName("MiniPanel")
        self.setStyleSheet("#MiniPanel { background: #ffffff; border: 2px solid #0f4c81; "
                           "border-radius: 8px; }")
        self.title = QLabel("<b>AutoFacturador</b>")
        self.state = QLabel("Iniciando…")
        self.state.setWordWrap(True)
        self.school = QLabel("")
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(16)
        self.pause = QPushButton("⏸ Pausar", objectName="Warn")
        self.resume = QPushButton("⏵ Seguir")
        self.stop = QPushButton("⏹ Detener", objectName="Danger")
        self.show_main = QPushButton("Ventana")
        self.pause.clicked.connect(ctl.pause)
        self.resume.clicked.connect(ctl.resume)
        self.stop.clicked.connect(ctl.stop)
        self.show_main.clicked.connect(on_show_main)
        row = QHBoxLayout()
        for b in (self.pause, self.resume, self.stop, self.show_main):
            b.setFocusPolicy(Qt.NoFocus)
            row.addWidget(b)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 8)
        lay.setSpacing(3)
        lay.addWidget(self.title)
        lay.addWidget(self.state)
        lay.addWidget(self.school)
        lay.addWidget(self.progress)
        lay.addLayout(row)
        ctl.state_changed.connect(self._on_state)
        ctl.invoice_changed.connect(self._on_invoice)
        self._drag: QPoint | None = None
        self._update_buttons()

    # ------------------------------------------------------------ colocación
    def place(self) -> bool:
        """Elige una esquina libre. Devuelve False si todas tapan zonas calibradas."""
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        ratio = float(screen.devicePixelRatio() or 1.0)
        main = find_window_rect(self.app.settings["titulo_ventana_principal"])
        busy = calibrated_screen_rects(self.app.settings, main)
        corners = [  # (x, y) lógicos; sin la esquina superior izquierda
            (geo.right() - WIDTH - MARGIN, geo.bottom() - HEIGHT - MARGIN),
            (geo.right() - WIDTH - MARGIN, geo.top() + MARGIN),
            (geo.left() + MARGIN, geo.bottom() - HEIGHT - MARGIN),
            (geo.center().x() - WIDTH // 2, geo.bottom() - HEIGHT - MARGIN),
        ]
        for x, y in corners:
            phys = (int(x * ratio), int(y * ratio), int((x + WIDTH) * ratio),
                    int((y + HEIGHT) * ratio))
            if not any(_intersects(phys, r) for r in busy):
                self.move(x, y)
                return True
        return False

    # ----------------------------------------------------------------- datos
    def _on_state(self, _state: str, label: str) -> None:
        self.state.setText(label)
        self._update_buttons()

    def _on_invoice(self, inv: dict) -> None:
        self.school.setText(f"{inv.get('escuela_codigo', '')} — {inv.get('escuela_nombre', '')}"
                            f" · cant. {inv.get('cantidad', '')}")
        if self.ctl.day_id:
            c = self.app.days.counts(self.ctl.day_id)
            self.progress.setMaximum(max(1, c["total"]))
            self.progress.setValue(c["procesadas"])
            self.progress.setFormat(f"{c['procesadas']} de {c['total']}")

    def _update_buttons(self) -> None:
        running = self.ctl.running
        self.pause.setEnabled(running and not self.ctl.paused)
        self.resume.setEnabled(running and self.ctl.paused)
        self.stop.setEnabled(running)

    # ------------------------------------------- arrastrar (sin marco de ventana)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None
