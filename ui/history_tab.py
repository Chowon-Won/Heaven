"""Historial de eventos y de facturas, con filtros y exportación a CSV."""
from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QTabWidget, QVBoxLayout,
                               QWidget)

from day_manager import InvoiceStatus
from import_export import write_table
from logging_manager import EV
from ui.common import fill_table, make_table
from ui.styles import STATUS_COLORS


class HistoryTab(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.since = QDateEdit(QDate.currentDate().addDays(-30), calendarPopup=True)
        self.until = QDateEdit(QDate.currentDate(), calendarPopup=True)
        for d in (self.since, self.until):
            d.setDisplayFormat("dd/MM/yyyy")
        self.school = QLineEdit(placeholderText="Escuela (código o nombre)")
        self.product = QLineEdit(placeholderText="Producto (código o nombre)")
        self.status = QComboBox()
        self.status.addItem("Todos los estados", "")
        for k, v in InvoiceStatus.LABELS.items():
            self.status.addItem(v, k)
        self.status.addItem("Solo errores (nivel)", "ERROR")
        self.kind = QComboBox()
        self.kind.addItem("Todos los eventos", "")
        for k, v in EV.items():
            self.kind.addItem(v, k)
        search = QPushButton("Filtrar", objectName="Primary")
        search.clicked.connect(self.refresh)
        export = QPushButton("Exportar a CSV")
        export.clicked.connect(self.export)
        f = QHBoxLayout()
        for w in (QLabel("Desde"), self.since, QLabel("Hasta"), self.until, self.school,
                  self.product, self.status, self.kind, search, export):
            f.addWidget(w)

        self.events = make_table(["Fecha y hora", "Nivel", "Evento", "Escuela", "Nombre",
                                  "Producto", "Estado", "Mensaje"])
        self.invoices = make_table(["Fecha jornada", "Jornada", "Código", "Escuela", "Producto",
                                    "Código prod.", "Estado", "Impresión", "Conduce",
                                    "Intentos", "Completada", "Mensaje"])
        self.tabs = QTabWidget()
        self.tabs.addTab(self.events, "Eventos")
        self.tabs.addTab(self.invoices, "Facturas")
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(self.tabs, 1)
        self._events: list[dict] = []
        self._invoices: list[dict] = []

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)

    def _range(self):
        return (self.since.date().toString("yyyy-MM-dd"),
                self.until.date().toString("yyyy-MM-dd"))

    def refresh(self):
        desde, hasta = self._range()
        estado = self.status.currentData()
        self._events = self.app.logger.search(desde, hasta, self.school.text().strip(),
                                              self.product.text().strip(), estado,
                                              self.kind.currentData())
        fill_table(self.events, [[e["fecha_hora"].replace("T", " "), e["nivel"],
                                  EV.get(e["tipo"], e["tipo"]), e["escuela_codigo"],
                                  e["escuela_nombre"], e["producto_codigo"], e["estado"],
                                  e["mensaje"]] for e in self._events],
                   colors=["#b91c1c" if e["nivel"] == "ERROR" else None for e in self._events])
        sql = ("SELECT f.*, j.fecha, j.producto_nombre, j.producto_codigo FROM facturas f "
               "JOIN jornadas j ON j.id = f.jornada_id WHERE j.fecha BETWEEN ? AND ?")
        p = [desde, hasta]
        if self.school.text().strip():
            sql += " AND (f.escuela_codigo LIKE ? OR f.escuela_nombre LIKE ?)"
            p += [f"%{self.school.text().strip()}%"] * 2
        if self.product.text().strip():
            sql += " AND (j.producto_codigo LIKE ? OR j.producto_nombre LIKE ?)"
            p += [f"%{self.product.text().strip()}%"] * 2
        if estado and estado in InvoiceStatus.LABELS:
            sql += " AND f.estado = ?"
            p.append(estado)
        sql += " ORDER BY j.fecha DESC, f.jornada_id DESC, f.orden"
        self._invoices = self.app.db.query(sql, p)
        fill_table(self.invoices, [[f["fecha"], f["jornada_id"], f["escuela_codigo"],
                                    f["escuela_nombre"], f["producto_nombre"], f["producto_codigo"],
                                    InvoiceStatus.LABELS.get(f["estado"], f["estado"]),
                                    f["estado_impresion"], f["conduce_despues"],
                                    f["intentos_recuperacion"], f["completado_en"] or "",
                                    f["mensaje"]] for f in self._invoices],
                   colors=[STATUS_COLORS.get(f["estado"]) for f in self._invoices])

    def export(self):
        which = self.tabs.currentIndex()
        name = "historial_eventos.csv" if which == 0 else "historial_facturas.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar historial", name, "CSV (*.csv)")
        if not path:
            return
        if which == 0:
            n = self.app.logger.export_csv(path, self._events)
        else:
            cols = ["fecha", "jornada_id", "escuela_codigo", "escuela_nombre", "producto_nombre",
                    "producto_codigo", "estado", "estado_impresion", "conduce_despues",
                    "intentos_recuperacion", "completado_en", "mensaje"]
            write_table(path, cols, [[f.get(c, "") for c in cols] for f in self._invoices])
            n = len(self._invoices)
        QMessageBox.information(self, "Exportado", f"{n} filas exportadas.")
