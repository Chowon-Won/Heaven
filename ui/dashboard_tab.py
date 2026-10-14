"""Panel principal."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QGridLayout, QLabel, QProgressBar, QVBoxLayout, QWidget)

from day_manager import Mode
from ui.automation_tab import ControlButtons


class DashboardTab(QWidget):
    def __init__(self, app, ctl, automation_tab, parent=None):
        super().__init__(parent)
        self.app, self.ctl, self.auto = app, ctl, automation_tab
        self.day_id: int | None = None
        self.cards: dict[str, QLabel] = {}
        grid = QGridLayout()
        specs = [("escuelas", "Escuelas registradas"), ("seleccionadas", "Escuelas en la jornada"),
                 ("completadas", "Facturas completadas"), ("pendientes", "Facturas pendientes"),
                 ("errores", "Facturas con errores"), ("revision", "Necesitan revisión"),
                 ("producto", "Producto de la jornada"), ("codigo", "Código de producto")]
        for i, (key, title) in enumerate(specs):
            lab = QLabel(objectName="Card")
            lab.setMinimumHeight(70)
            self.cards[key] = lab
            lab.setProperty("title", title)
            grid.addWidget(lab, i // 4, i % 4)
        self.day_label = QLabel(objectName="Title")
        self.progress = QProgressBar()
        self.state = QLabel("En espera", objectName="State")
        self.controls = ControlButtons(self.auto.run_all, ctl)
        lay = QVBoxLayout(self)
        lay.addWidget(self.day_label)
        lay.addLayout(grid)
        lay.addWidget(QLabel("Progreso de la jornada:"))
        lay.addWidget(self.progress)
        lay.addWidget(QLabel("Estado del macro:"))
        lay.addWidget(self.state)
        lay.addWidget(self.controls)
        lay.addWidget(QLabel("«Iniciar» usa el modo elegido en la pestaña Automatización. "
                             "Emergencia: ratón a la esquina superior izquierda.", objectName="Hint"))
        lay.addStretch(1)
        ctl.state_changed.connect(lambda _s, label: self.state.setText(label))
        ctl.invoice_changed.connect(lambda _i: self.refresh())
        automation_tab.day_selected.connect(self.set_day)
        self.timer = QTimer(self, interval=3000, timeout=self.refresh)
        self.timer.start()
        self.refresh()

    def set_day(self, day_id: int):
        self.day_id = day_id
        self.refresh()

    def _card(self, key: str, value):
        lab = self.cards[key]
        lab.setText(f"<span style='color:#6b7280'>{lab.property('title')}</span><br>"
                    f"<span style='font-size:20pt;font-weight:700'>{value}</span>")

    def refresh(self):
        self._card("escuelas", self.app.schools.count())
        day = self.app.days.get_day(self.day_id) if self.day_id else self.app.days.latest_day()
        if not day:
            self.day_label.setText("Sin jornadas. Cree una en «Nueva jornada».")
            for k in ("seleccionadas", "completadas", "pendientes", "errores", "revision"):
                self._card(k, 0)
            self._card("producto", "—")
            self._card("codigo", "—")
            self.progress.setValue(0)
            return
        c = self.app.days.counts(day["id"])
        tipo = "simulada" if day["modo"] == Mode.SIMULADO else "real"
        self.day_label.setText(f"Jornada #{day['id']} — {day['fecha']} ({tipo}) — {day['estado']}")
        self._card("seleccionadas", c["total"])
        self._card("completadas", c["completadas"])
        self._card("pendientes", c["pendientes"] + c["en_proceso"])
        self._card("errores", c["errores"])
        self._card("revision", c["revision"])
        self._card("producto", day["producto_nombre"])
        self._card("codigo", day["producto_codigo"])
        self.progress.setMaximum(max(1, c["total"]))
        self.progress.setValue(c["procesadas"])
        self.progress.setFormat(f"{c['procesadas']} de {c['total']} procesadas (%p%)")
