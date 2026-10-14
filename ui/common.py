"""Widgets y utilidades compartidas por las pestañas."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHeaderView, QLineEdit, QMessageBox,
                               QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout)

from catalog_base import CatalogError


def make_table(headers: list[str], multi: bool = True) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.ExtendedSelection if multi
                       else QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.setSortingEnabled(False)
    return t


def fill_table(table: QTableWidget, rows: list[list], ids: list | None = None,
               colors: list[str | None] | None = None) -> None:
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem("" if value is None else str(value))
            if c == 0 and ids is not None:
                item.setData(Qt.UserRole, ids[r])
            if colors and colors[r] and c == 0:
                pass
            if colors and colors[r]:
                item.setForeground(QColor(colors[r]))
            table.setItem(r, c, item)
    table.resizeColumnsToContents()


def selected_ids(table: QTableWidget) -> list:
    rows = sorted({i.row() for i in table.selectedIndexes()})
    return [table.item(r, 0).data(Qt.UserRole) for r in rows if table.item(r, 0)]


def confirm(parent, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) == QMessageBox.Yes


def error(parent, text: str, title: str = "Atención") -> None:
    QMessageBox.warning(parent, title, text)


class RecordDialog(QDialog):
    """Formulario genérico para escuelas y productos."""

    def __init__(self, parent, title: str, fields: list[tuple[str, str, str]],
                 data: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.inputs = {}
        form = QFormLayout()
        data = data or {}
        for key, label, kind in fields:
            if kind == "bool":
                w = QCheckBox()
                w.setChecked(bool(data.get(key, True)))
            elif kind == "multiline":
                w = QPlainTextEdit(str(data.get(key, "") or ""))
                w.setFixedHeight(70)
            else:
                w = QLineEdit(str(data.get(key, "") or ""))
            self.inputs[key] = w
            form.addRow(label, w)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def values(self) -> dict:
        out = {}
        for k, w in self.inputs.items():
            if isinstance(w, QCheckBox):
                out[k] = w.isChecked()
            elif isinstance(w, QPlainTextEdit):
                out[k] = w.toPlainText().strip()
            else:
                out[k] = w.text().strip()
        return out


SCHOOL_FIELDS = [("orden", "Orden en la ruta (1, 2, 3…)", "text"),
                 ("codigo", "Código de escuela", "text"),
                 ("nombre", "Nombre completo", "text"),
                 ("activo", "Activa", "bool"),
                 ("notas", "Notas internas", "multiline")]

PRODUCT_FIELDS = [("nombre", "Nombre del producto", "text"),
                  ("codigo", "Código en SisFaCon", "text"),
                  ("texto_verificacion", "Descripción que muestra SisFaCon\n(vacío = nombre)", "text"),
                  ("descripcion", "Descripción interna (opcional)", "text"),
                  ("activo", "Activo", "bool")]


def edit_record(parent, manager, fields, title: str, record: dict | None = None) -> int | None:
    """Abre el formulario hasta que los datos sean válidos o se cancele."""
    data = dict(record) if record else {}
    while True:
        dlg = RecordDialog(parent, title, fields, data)
        if dlg.exec() != QDialog.Accepted:
            return None
        data = dlg.values()
        try:
            if record:
                manager.update(record["id"], **data)
                return record["id"]
            return manager.add(**data)
        except CatalogError as exc:
            error(parent, str(exc))
