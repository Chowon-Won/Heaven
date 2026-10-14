"""Pestañas «Escuelas» y «Productos» (misma lógica, distinto catálogo)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

from import_export import read_table, write_table
from ui.common import (PRODUCT_FIELDS, SCHOOL_FIELDS, confirm, edit_record, error,
                       fill_table, make_table, selected_ids)

ROOT = Path(__file__).resolve().parents[1]


class CatalogTab(QWidget):
    changed = Signal()

    def __init__(self, app, kind: str, parent=None):
        super().__init__(parent)
        self.app = app
        self.kind = kind
        if kind == "escuelas":
            self.manager = app.schools
            self.fields = SCHOOL_FIELDS
            self.headers = ["Orden", "Código", "Nombre", "Cantidad", "Estado", "Notas"]
            self.export_cols = ["orden", "codigo", "nombre", "cantidad", "activo", "notas"]
            self.singular, self.plural = "escuela", "escuelas"
            self.template = ROOT / "plantillas" / "plantilla_escuelas.csv"
        else:
            self.manager = app.products
            self.fields = PRODUCT_FIELDS
            self.headers = ["Código", "Nombre", "Descripción en SisFaCon", "Estado", "Descripción"]
            self.export_cols = ["codigo", "nombre", "texto_verificacion", "activo", "descripcion"]
            self.singular, self.plural = "producto", "productos"
            self.template = ROOT / "plantillas" / "plantilla_productos.csv"

        self.search = QLineEdit(placeholderText=f"Buscar {self.plural} por nombre o código…")
        self.search.textChanged.connect(self.refresh)
        self.only_active = QCheckBox("Solo activos")
        self.only_active.toggled.connect(self.refresh)
        self.table = make_table(self.headers)
        self.table.doubleClicked.connect(self.edit)
        self.info = QLabel(objectName="Hint")

        def btn(text, slot, name=None):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(slot)
            return b

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.only_active)
        actions = QHBoxLayout()
        for b in (btn(f"Añadir {self.singular}", self.add, "Primary"),
                  btn("Editar", self.edit), btn("Eliminar", self.delete, "Danger"),
                  btn("Activar", lambda: self.set_active(True)),
                  btn("Desactivar", lambda: self.set_active(False))):
            actions.addWidget(b)
        actions.addStretch(1)
        for b in (btn("Importar CSV/Excel", self.import_file), btn("Exportar", self.export_file),
                  btn("Guardar plantilla", self.save_template),
                  btn("Detectar duplicados", self.check_duplicates)):
            actions.addWidget(b)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(actions)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.info)
        self.refresh()

    # ------------------------------------------------------------------
    def _row(self, r: dict) -> list:
        estado = "Activo" if r["activo"] else "Inactivo"
        if self.kind == "escuelas":
            return [r["orden"] or "", r["codigo"], r["nombre"],
                    r["cantidad"] or "FALTA", estado, r["notas"]]
        return [r["codigo"], r["nombre"], r["texto_verificacion"] or "(igual al nombre)",
                estado, r["descripcion"]]

    def refresh(self):
        rows = self.manager.list(self.search.text(), self.only_active.isChecked())
        fill_table(self.table, [self._row(r) for r in rows], [r["id"] for r in rows],
                   [None if r["activo"] else "#9ca3af" for r in rows])
        self.info.setText(f"{len(rows)} {self.plural} mostrados · "
                          f"{self.manager.count(True)} activos · {self.manager.count()} en total. "
                          "Los códigos se guardan como texto (se conservan los ceros iniciales).")

    def _done(self):
        self.refresh()
        self.changed.emit()

    def add(self):
        if edit_record(self, self.manager, self.fields, f"Añadir {self.singular}"):
            self._done()

    def edit(self, *_):
        ids = selected_ids(self.table)
        if len(ids) != 1:
            error(self, f"Seleccione una sola {self.singular} para editar.")
            return
        if edit_record(self, self.manager, self.fields, f"Editar {self.singular}",
                       self.manager.get(ids[0])):
            self._done()

    def delete(self):
        ids = selected_ids(self.table)
        if not ids:
            return
        names = [self.manager.get(i)["nombre"] for i in ids]
        if confirm(self, "Eliminar", f"¿Eliminar {len(ids)} {self.plural}?\n\n"
                   + "\n".join(names[:15]) +
                   "\n\nEl historial de facturas anteriores se conserva."):
            for i in ids:
                self.manager.delete(i)
            self._done()

    def set_active(self, active: bool):
        for i in selected_ids(self.table):
            self.manager.set_active(i, active)
        self._done()

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, f"Importar {self.plural}", "",
                                              "CSV o Excel (*.csv *.xlsx *.txt)")
        if not path:
            return
        update = confirm(self, "Importar",
                         "Si un código ya existe, ¿desea ACTUALIZAR sus datos con los del archivo?\n"
                         "(No = conservar los datos actuales y omitir esas filas)")
        try:
            report = self.manager.import_rows(read_table(path), update_existing=update)
        except Exception as exc:
            error(self, f"No se pudo leer el archivo: {exc}")
            return
        QMessageBox.information(self, "Importación terminada", report.resumen())
        self._done()

    def export_file(self):
        path, _ = QFileDialog.getSaveFileName(self, f"Exportar {self.plural}",
                                              f"{self.plural}.csv", "CSV (*.csv);;Excel (*.xlsx)")
        if not path:
            return
        rows = self.manager.list()
        write_table(path, self.export_cols,
                    [[("si" if r[c] else "no") if c == "activo" else r[c]
                      for c in self.export_cols] for r in rows])
        QMessageBox.information(self, "Exportado", f"{len(rows)} {self.plural} exportados.")

    def save_template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar plantilla", self.template.name,
                                              "CSV (*.csv)")
        if path:
            Path(path).write_bytes(self.template.read_bytes())

    def check_duplicates(self):
        dups = self.manager.find_duplicate_codes()
        QMessageBox.information(self, "Duplicados",
                                "No hay códigos duplicados." if not dups
                                else "Códigos duplicados: " + ", ".join(dups))
