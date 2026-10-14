"""Asistente «Nueva jornada» en 6 pasos."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDateEdit, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QRadioButton, QStackedWidget, QTableWidgetItem, QTextEdit,
                               QVBoxLayout, QWidget)

from day_manager import Mode
from product_manager import ProductManager
from ui.common import PRODUCT_FIELDS, confirm, edit_record, error, make_table

STEPS = ["1. Fecha", "2. Producto", "3. Confirmar código", "4. Escuelas",
         "5. Revisión", "6. Confirmar inicio"]


class DayTab(QWidget):
    day_created = Signal(int)
    open_catalog = Signal(str)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.stack = QStackedWidget()
        self.step_label = QLabel(objectName="Title")
        self.back = QPushButton("◀ Atrás")
        self.next = QPushButton("Siguiente ▶", objectName="Primary")
        self.back.clicked.connect(lambda: self.go(self.stack.currentIndex() - 1))
        self.next.clicked.connect(self.on_next)

        self._build_date()
        self._build_product()
        self._build_code()
        self._build_schools()
        self._build_review()
        self._build_confirm()

        nav = QHBoxLayout()
        nav.addWidget(self.back)
        nav.addStretch(1)
        nav.addWidget(self.next)
        lay = QVBoxLayout(self)
        lay.addWidget(self.step_label)
        lay.addWidget(self.stack, 1)
        lay.addLayout(nav)
        self.go(0)

    # --------------------------------------------------------------- pasos
    def _page(self, *widgets) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        for x in widgets:
            if isinstance(x, QWidget):
                v.addWidget(x)
            else:
                v.addLayout(x)
        v.addStretch(1)
        self.stack.addWidget(w)
        return w

    def _build_date(self):
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self._page(QLabel("Fecha de la jornada (debe coincidir con la FECHA de SisFaCon):"),
                   self.date)

    def _build_product(self):
        self.product = QComboBox()
        self.product.setMinimumWidth(320)
        row = QHBoxLayout()
        add = QPushButton("Añadir producto")
        add.clicked.connect(self.add_product)
        edit = QPushButton("Editar productos")
        edit.clicked.connect(self.edit_product)
        admin = QPushButton("Administrar catálogo")
        admin.clicked.connect(lambda: self.open_catalog.emit("productos"))
        for b in (add, edit, admin):
            row.addWidget(b)
        row.addStretch(1)
        self._page(QLabel("Producto de la jornada:"), self.product, row,
                   QLabel("Solo se muestran productos activos.", objectName="Hint"))

    def _build_code(self):
        self.code_info = QLabel(objectName="Card")
        self.code_ok = QCheckBox("Confirmo que este es el código correcto para todas las facturas "
                                 "de la jornada")
        self._page(self.code_info, self.code_ok)

    def _build_schools(self):
        self.school_search = QLineEdit(placeholderText="Buscar escuela…")
        self.school_search.textChanged.connect(self._filter_schools)
        self.schools_table = make_table(["", "Código", "Nombre", "Cantidad"], multi=True)
        self.schools_table.itemChanged.connect(lambda *_: self._update_count())
        self.count_label = QLabel()
        row = QHBoxLayout()
        for text, slot in (("Seleccionar todas las activas", lambda: self._check_all(True)),
                           ("Desmarcar todas", lambda: self._check_all(False)),
                           ("Marcar seleccionadas", lambda: self._check_selected(True)),
                           ("Desmarcar seleccionadas", lambda: self._check_selected(False))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        rng = QHBoxLayout()
        self.range_from = QComboBox()
        self.range_to = QComboBox()
        only = QPushButton("Solo este rango", objectName="Primary")
        only.clicked.connect(lambda: self._mark_range(exclusive=True))
        add = QPushButton("Añadir este rango")
        add.clicked.connect(lambda: self._mark_range(exclusive=False))
        rng.addWidget(QLabel("Desde la escuela"))
        rng.addWidget(self.range_from, 1)
        rng.addWidget(QLabel("hasta"))
        rng.addWidget(self.range_to, 1)
        rng.addWidget(only)
        rng.addWidget(add)
        presets = QHBoxLayout()
        self.preset = QComboBox()
        load = QPushButton("Cargar configuración")
        load.clicked.connect(self.load_preset)
        save = QPushButton("Guardar como frecuente")
        save.clicked.connect(self.save_preset)
        delete = QPushButton("Borrar")
        delete.clicked.connect(self.delete_preset)
        presets.addWidget(QLabel("Configuraciones frecuentes:"))
        presets.addWidget(self.preset, 1)
        for b in (load, save, delete):
            presets.addWidget(b)
        page = QWidget()
        v = QVBoxLayout(page)
        v.addLayout(presets)
        v.addWidget(self.school_search)
        v.addLayout(row)
        v.addLayout(rng)
        v.addWidget(self.schools_table, 1)
        v.addWidget(self.count_label)
        self.stack.addWidget(page)

    def _build_review(self):
        self.review = QTextEdit(readOnly=True)
        self._page(self.review)

    def _build_confirm(self):
        self.mode_sim = QRadioButton("Jornada SIMULADA (no toca SisFaCon; para practicar)")
        self.mode_real = QRadioButton("Jornada REAL en SisFaCon Express")
        self.mode_sim.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.mode_sim)
        group.addButton(self.mode_real)
        self.confirm_text = QLabel(objectName="Card")
        self.confirm_text.setWordWrap(True)
        self._page(QLabel("Tipo de jornada:"), self.mode_sim, self.mode_real, self.confirm_text,
                   QLabel("Al crear la jornada se guarda una copia del producto y de la lista: "
                          "cambiar el catálogo después no altera estas facturas.", objectName="Hint"))

    # ---------------------------------------------------------- navegación
    def go(self, idx: int):
        idx = max(0, min(idx, len(STEPS) - 1))
        if idx == 1:
            self.reload_products()
        if idx == 2:
            p = self.current_product()
            if p:
                self.code_info.setText(
                    f"<b>Producto:</b> {p['nombre']}<br><b>Código que se escribirá en SisFaCon:</b> "
                    f"<span style='font-size:16pt'>{p['codigo']}</span><br>"
                    f"<b>Descripción esperada:</b> {ProductManager.verification_text(p)}")
            self.code_ok.setChecked(False)
        if idx == 3 and self.schools_table.rowCount() == 0:
            self.reload_schools()
        if idx == 4:
            self._fill_review()
        if idx == 5:
            self.confirm_text.setText(self._summary_html(short=True))
        self.stack.setCurrentIndex(idx)
        self.step_label.setText("Nueva jornada — " + STEPS[idx])
        self.back.setEnabled(idx > 0)
        self.next.setText("Crear jornada ✔" if idx == len(STEPS) - 1 else "Siguiente ▶")

    def on_next(self):
        idx = self.stack.currentIndex()
        if idx == 1 and not self.current_product():
            return error(self, "Seleccione un producto.")
        if idx == 2 and not self.code_ok.isChecked():
            return error(self, "Confirme el código del producto para continuar.")
        if idx == 3 and not self.checked_schools():
            return error(self, "Seleccione al menos una escuela.")
        if idx == 3:
            missing = self.app.schools.without_quantity(self.checked_schools())
            if missing:
                return error(self, "Estas escuelas no tienen cantidad (póngala en la pestaña "
                                   "Escuelas o en el Excel e impórtelo):\n\n" + "\n".join(
                                       f"{s['codigo']} — {s['nombre']}" for s in missing[:20]))
        if idx == len(STEPS) - 1:
            return self.create_day()
        self.go(idx + 1)

    # ------------------------------------------------------------- productos
    def reload_products(self, select_id: int | None = None):
        current = select_id or (self.current_product() or {}).get("id")
        self.product.clear()
        for p in self.app.products.list(only_active=True):
            self.product.addItem(ProductManager.label(p), p["id"])
        if current:
            i = self.product.findData(current)
            if i >= 0:
                self.product.setCurrentIndex(i)

    def current_product(self) -> dict | None:
        pid = self.product.currentData()
        return self.app.products.get(pid) if pid else None

    def add_product(self):
        pid = edit_record(self, self.app.products, PRODUCT_FIELDS, "Añadir producto")
        if pid:
            self.reload_products(pid)

    def edit_product(self):
        p = self.current_product()
        if p and edit_record(self, self.app.products, PRODUCT_FIELDS, "Editar producto", p):
            self.reload_products(p["id"])

    # -------------------------------------------------------------- escuelas
    def reload_schools(self, checked_ids: set[int] | None = None):
        prev = checked_ids if checked_ids is not None else {s["id"] for s in self.checked_schools()}
        rows = self.app.schools.list(only_active=True)
        t = self.schools_table
        t.blockSignals(True)
        t.setRowCount(len(rows))
        for r, s in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if s["id"] in prev else Qt.Unchecked)
            chk.setData(Qt.UserRole, s["id"])
            t.setItem(r, 0, chk)
            t.setItem(r, 1, QTableWidgetItem(s["codigo"]))
            t.setItem(r, 2, QTableWidgetItem(s["nombre"]))
            t.setItem(r, 3, QTableWidgetItem(str(s["cantidad"] or "FALTA")))
        t.blockSignals(False)
        t.resizeColumnsToContents()
        for combo, pick_last in ((self.range_from, False), (self.range_to, True)):
            combo.clear()
            for r, s in enumerate(rows):
                combo.addItem(f"{r + 1}. {s['codigo']} — {s['nombre']}", r)
            if rows:
                combo.setCurrentIndex(len(rows) - 1 if pick_last else 0)
        self._filter_schools()
        self._update_count()

    def _mark_range(self, exclusive: bool):
        """Marca las escuelas entre «desde» y «hasta» (orden de la tabla)."""
        if self.range_from.count() == 0:
            return
        lo, hi = sorted((self.range_from.currentData(), self.range_to.currentData()))
        t = self.schools_table
        t.blockSignals(True)
        for r in range(t.rowCount()):
            if lo <= r <= hi:
                self._set_row(r, True)
            elif exclusive:
                self._set_row(r, False)
        t.blockSignals(False)
        self._update_count()

    def _filter_schools(self):
        text = self.school_search.text().lower().strip()
        t = self.schools_table
        for r in range(t.rowCount()):
            hay = (t.item(r, 1).text() + " " + t.item(r, 2).text()).lower()
            t.setRowHidden(r, bool(text) and text not in hay)

    def _set_row(self, r: int, on: bool):
        self.schools_table.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _check_all(self, on: bool):
        t = self.schools_table
        t.blockSignals(True)
        for r in range(t.rowCount()):
            if not t.isRowHidden(r):
                self._set_row(r, on)
        t.blockSignals(False)
        self._update_count()

    def _check_selected(self, on: bool):
        t = self.schools_table
        t.blockSignals(True)
        for r in {i.row() for i in t.selectedIndexes()}:
            self._set_row(r, on)
        t.blockSignals(False)
        self._update_count()

    def checked_schools(self) -> list[dict]:
        t = self.schools_table
        out = []
        for r in range(t.rowCount()):
            it = t.item(r, 0)
            if it and it.checkState() == Qt.Checked:
                out.append(self.app.schools.get(it.data(Qt.UserRole)))
        return [s for s in out if s and not s["eliminado"]]

    def _update_count(self):
        self.count_label.setText(f"Escuelas seleccionadas: {len(self.checked_schools())}")

    # ----------------------------------------------- configuraciones frecuentes
    def _reload_presets(self):
        self.preset.clear()
        for p in self.app.days.list_presets():
            self.preset.addItem(p["nombre"], p)

    def showEvent(self, e):
        self._reload_presets()
        if self.stack.currentIndex() == 1:
            self.reload_products()
        super().showEvent(e)

    def save_preset(self):
        name, ok = QInputDialog.getText(self, "Guardar configuración", "Nombre:")
        if ok and name.strip():
            p = self.current_product()
            self.app.days.save_preset(name.strip(), p["id"] if p else None,
                                      [s["id"] for s in self.checked_schools()])
            self._reload_presets()

    def load_preset(self):
        p = self.preset.currentData()
        if not p:
            return
        if p["producto_id"]:
            self.reload_products(p["producto_id"])
        self.reload_schools(set(p["escuelas_ids"]))

    def delete_preset(self):
        p = self.preset.currentData()
        if p and confirm(self, "Borrar", f"¿Borrar la configuración «{p['nombre']}»?"):
            self.app.days.delete_preset(p["id"])
            self._reload_presets()

    # ---------------------------------------------------------------- revisión
    def _summary_html(self, short: bool = False) -> str:
        p = self.current_product() or {}
        schools = self.checked_schools()
        html = (f"<b>Fecha:</b> {self.date.date().toString('dd/MM/yyyy')}<br>"
                f"<b>Producto:</b> {p.get('nombre', '')}<br>"
                f"<b>Código del producto:</b> {p.get('codigo', '')}<br>"
                f"<b>Escuelas seleccionadas:</b> {len(schools)}<br>"
                f"<b>Facturas previstas:</b> {len(schools)}")
        if not short:
            html += "<hr><b>Lista de escuelas:</b><ol>" + "".join(
                f"<li>{s['codigo']} — {s['nombre']} — cantidad <b>{s['cantidad'] or 'FALTA'}</b></li>"
                for s in schools) + "</ol>"
        return html

    def _fill_review(self):
        self.review.setHtml(self._summary_html())

    # --------------------------------------------------------------- crear
    def create_day(self):
        product = self.current_product()
        schools = self.checked_schools()
        fecha = self.date.date().toString("yyyy-MM-dd")
        real = self.mode_real.isChecked()
        if real:
            dup = self.app.days.schools_already_processed(fecha, [s["codigo"] for s in schools])
            if dup:
                listing = "\n".join(f"{d['escuela_codigo']} — {d['escuela_nombre']} ({d['estado']})"
                                    for d in dup)
                box = QMessageBox(self)
                box.setWindowTitle("Posibles duplicados")
                box.setIcon(QMessageBox.Warning)
                box.setText("Estas escuelas ya tienen una factura procesada (o en revisión) "
                            f"para el {self.date.date().toString('dd/MM/yyyy')}:\n\n{listing}")
                excl = box.addButton("Quitarlas de la jornada", QMessageBox.AcceptRole)
                keep = box.addButton("Incluirlas igualmente", QMessageBox.DestructiveRole)
                box.addButton("Cancelar", QMessageBox.RejectRole)
                box.exec()
                if box.clickedButton() == excl:
                    codes = {d["escuela_codigo"] for d in dup}
                    schools = [s for s in schools if s["codigo"] not in codes]
                elif box.clickedButton() != keep:
                    return
                if not schools:
                    return error(self, "No quedan escuelas en la jornada.")
        try:
            day_id = self.app.days.create_day(fecha, product, schools,
                                              Mode.AUTOMATICO if real else Mode.SIMULADO)
        except ValueError as exc:
            return error(self, str(exc))
        day = self.app.days.get_day(day_id)
        self.app.logger.log("JORNADA_CREADA", f"{len(schools)} escuelas", jornada=day)
        self.app.logger.log("PRODUCTO_SELECCIONADO",
                            f"{day['producto_nombre']} — {day['producto_codigo']}", jornada=day)
        QMessageBox.information(self, "Jornada creada",
                                f"Jornada #{day_id} creada con {len(schools)} facturas previstas.")
        self.day_created.emit(day_id)
        self.go(0)
