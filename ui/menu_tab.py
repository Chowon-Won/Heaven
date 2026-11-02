"""Pestaña «Menú»: producto de cada día (lunes a sábado) de las 5 semanas del mes."""
from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (QComboBox, QHeaderView, QLabel, QTableWidget, QVBoxLayout,
                               QWidget)

from menu_manager import DIAS, SEMANAS, MenuManager

NONE = "— sin producto —"


class MenuTab(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.table = QTableWidget(SEMANAS, len(DIAS))
        self.table.setHorizontalHeaderLabels(DIAS)
        self.table.setVerticalHeaderLabels([f"Semana {i}" for i in range(1, SEMANAS + 1)])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.today = QLabel(objectName="Card")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Elija el producto de cada día. Los sábados tienen su propio menú "
                             "(columna Sábado). Al crear una jornada, el producto se propone "
                             "solo según la fecha; siempre se puede cambiar.", objectName="Hint"))
        lay.addWidget(self.table, 1)
        lay.addWidget(self.today)
        lay.addWidget(QLabel("Semana del mes: la semana 1 es la primera semana (de lunes a "
                             "domingo) que tiene algún día de lunes a sábado en el mes. Si un mes "
                             "tiene 6 semanas, la 6.ª usa el menú de la semana 1.",
                             objectName="Hint"))
        self.refresh()

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)

    def refresh(self):
        products = self.app.products.list(only_active=True)
        grid = self.app.menu.grid()
        for s in range(1, SEMANAS + 1):
            for d in range(len(DIAS)):
                combo = QComboBox()
                combo.addItem(NONE, None)
                for p in products:
                    combo.addItem(f"{p['nombre']} — {p['codigo']}", p["id"])
                pid = grid.get((s, d))
                if pid:
                    i = combo.findData(pid)
                    if i < 0:   # producto inactivo o eliminado: se muestra para no perderlo
                        p = self.app.products.get(pid)
                        if p:
                            combo.addItem(f"{p['nombre']} — {p['codigo']} (inactivo)", pid)
                            i = combo.count() - 1
                    if i >= 0:
                        combo.setCurrentIndex(i)
                combo.currentIndexChanged.connect(
                    lambda _i, s=s, d=d, c=combo: self._changed(s, d, c))
                self.table.setCellWidget(s - 1, d, combo)
        self._update_today()

    def _changed(self, semana: int, dia: int, combo: QComboBox):
        self.app.menu.set(semana, dia, combo.currentData())
        self._update_today()

    def _update_today(self):
        today = date.today()
        pid, semana, dia = self.app.menu.product_for_date(today)
        p = self.app.products.get(pid) if pid else None
        self.today.setText(f"<b>Hoy</b> ({today:%d/%m/%Y}): {MenuManager.label(semana, dia)} → "
                           + (f"<b>{p['nombre']} — {p['codigo']}</b>" if p else
                              ("domingo, sin jornada" if dia is None else "sin producto en el menú")))
