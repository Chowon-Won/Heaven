"""Pestaña «Automatización»: modo, jornada, controles y estado por escuela."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QGroupBox, QHBoxLayout,
                               QLabel, QListWidget, QMenu, QPushButton, QRadioButton,
                               QSpinBox, QSplitter, QVBoxLayout, QWidget)

from automation import RunOptions
from day_manager import InvoiceStatus, Mode, PrintStatus
from ui.common import confirm, error, fill_table, make_table, selected_ids
from ui.styles import STATUS_COLORS


class ControlButtons(QWidget):
    """Iniciar / Pausar / Reanudar / Detener (se usa también en el panel)."""

    def __init__(self, on_start, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.start = QPushButton("▶ Iniciar", objectName="Primary")
        self.pause = QPushButton("⏸ Pausar", objectName="Warn")
        self.resume = QPushButton("⏵ Reanudar")
        self.stop = QPushButton("⏹ Detener", objectName="Danger")
        self.start.clicked.connect(on_start)
        self.pause.clicked.connect(ctl.pause)
        self.resume.clicked.connect(ctl.resume)
        self.stop.clicked.connect(ctl.stop)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        for b in (self.start, self.pause, self.resume, self.stop):
            b.setMinimumHeight(36)
            lay.addWidget(b)
        ctl.running_changed.connect(self.update_state)
        ctl.state_changed.connect(lambda *_: self.update_state())
        self.update_state()

    def update_state(self, *_):
        running = self.ctl.running
        self.start.setEnabled(not running)
        self.pause.setEnabled(running and not self.ctl.paused)
        self.resume.setEnabled(running and self.ctl.paused)
        self.stop.setEnabled(running)


class AutomationTab(QWidget):
    day_selected = Signal(int)

    def __init__(self, app, ctl, parent=None):
        super().__init__(parent)
        self.app, self.ctl = app, ctl

        # --- jornada
        self.day_combo = QComboBox()
        self.day_combo.currentIndexChanged.connect(self._day_changed)
        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.reload_days)
        day_row = QHBoxLayout()
        day_row.addWidget(QLabel("Jornada:"))
        day_row.addWidget(self.day_combo, 1)
        day_row.addWidget(refresh)

        # --- modo
        self.r_sim = QRadioButton("Simulado")
        self.r_test = QRadioButton("Prueba (1 escuela, confirma cada paso)")
        self.r_auto = QRadioButton("Automático")
        self.modes = QButtonGroup(self)
        for r in (self.r_sim, self.r_test, self.r_auto):
            self.modes.addButton(r)
        self.mode_hint = QLabel(objectName="Hint")
        self.mode_hint.setWordWrap(True)
        mode_box = QGroupBox("Modo de funcionamiento")
        mv = QVBoxLayout(mode_box)
        mr = QHBoxLayout()
        for r in (self.r_sim, self.r_test, self.r_auto):
            mr.addWidget(r)
        mr.addStretch(1)
        mv.addLayout(mr)
        mv.addWidget(self.mode_hint)

        # --- ejecución
        self.confirm_each = QCheckBox("Confirmar la siguiente operación (preguntar antes de cada escuela)")
        self.confirm_each.setChecked(bool(app.settings["confirmar_cada_escuela"]))
        self.confirm_each.toggled.connect(lambda v: app.settings.set("confirmar_cada_escuela", v))
        self.group_n = QSpinBox(minimum=1, maximum=100, value=3)
        run_one = QPushButton("Ejecutar escuela seleccionada")
        run_one.clicked.connect(self.run_selected)
        run_group = QPushButton("Ejecutar grupo de prueba")
        run_group.clicked.connect(self.run_group)
        self.controls = ControlButtons(self.run_all, ctl)
        self.controls.start.setText("▶ Ejecutar todas las seleccionadas")
        run_box = QGroupBox("Ejecución")
        rv = QVBoxLayout(run_box)
        r1 = QHBoxLayout()
        r1.addWidget(run_one)
        r1.addWidget(run_group)
        r1.addWidget(QLabel("primeras"))
        r1.addWidget(self.group_n)
        r1.addStretch(1)
        rv.addLayout(r1)
        rv.addWidget(self.confirm_each)
        rv.addWidget(self.controls)
        rv.addWidget(QLabel("Emergencia: lleve el ratón a la esquina SUPERIOR IZQUIERDA de la "
                            "pantalla para abortar al instante.", objectName="Hint"))

        # --- estado
        self.state = QLabel("En espera", objectName="State")
        self.table = make_table(["#", "Código", "Escuela", "Estado", "Impresión",
                                 "Intentos", "Etapa", "Mensaje"])
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        manual = QHBoxLayout()
        for text, slot in (("Marcar pendiente (verifiqué que NO existe)", self.mark_pending),
                           ("Marcar completada (verifiqué en SisFaCon)", self.mark_done),
                           ("Omitir", self.mark_skip)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            manual.addWidget(b)
        manual.addStretch(1)
        self.log = QListWidget()

        split = QSplitter(Qt.Vertical)
        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(self.table, 1)
        tv.addLayout(manual)
        split.addWidget(top)
        split.addWidget(self.log)
        split.setSizes([400, 150])

        lay = QVBoxLayout(self)
        lay.addLayout(day_row)
        h = QHBoxLayout()
        h.addWidget(mode_box, 1)
        h.addWidget(run_box, 2)
        lay.addLayout(h)
        lay.addWidget(self.state)
        lay.addWidget(split, 1)

        ctl.state_changed.connect(lambda _s, label: self.state.setText(label))
        ctl.invoice_changed.connect(lambda _i: self.refresh_invoices())
        ctl.event_logged.connect(self._on_event)
        ctl.running_changed.connect(lambda _r: self.refresh_invoices())
        self.reload_days()

    # ---------------------------------------------------------------- datos
    def reload_days(self, select_id: int | None = None):
        current = select_id or self.day_combo.currentData()
        self.day_combo.blockSignals(True)
        self.day_combo.clear()
        for d in self.app.days.list_days(100):
            tipo = "SIMULADA" if d["modo"] == Mode.SIMULADO else "REAL"
            self.day_combo.addItem(
                f"#{d['id']} · {d['fecha']} · {d['producto_nombre']} ({d['producto_codigo']}) · "
                f"{tipo} · {d['estado']}", d["id"])
        if current:
            i = self.day_combo.findData(current)
            if i >= 0:
                self.day_combo.setCurrentIndex(i)
        self.day_combo.blockSignals(False)
        self._day_changed()

    def current_day(self) -> dict | None:
        did = self.day_combo.currentData()
        return self.app.days.get_day(did) if did else None

    def _day_changed(self, *_):
        day = self.current_day()
        simulated = not day or day["modo"] == Mode.SIMULADO
        unlocked = bool(self.app.settings["prueba_superada"])
        self.r_sim.setEnabled(simulated)
        self.r_test.setEnabled(not simulated)
        self.r_auto.setEnabled(not simulated and unlocked)
        if simulated:
            self.r_sim.setChecked(True)
            self.mode_hint.setText("Jornada simulada: no se toca SisFaCon.")
        else:
            (self.r_auto if unlocked and not self.r_test.isChecked() else self.r_test).setChecked(True)
            self.mode_hint.setText(
                "Jornada real. " + ("Modo automático habilitado (prueba superada)." if unlocked else
                                    "El modo automático se habilita tras una factura de prueba "
                                    "correcta en modo Prueba."))
        if day:
            self.day_selected.emit(day["id"])
        self.refresh_invoices()

    def refresh_invoices(self):
        day = self.current_day()
        if not day:
            self.table.setRowCount(0)
            return
        rows, ids, colors = [], [], []
        for f in self.app.days.invoices(day["id"]):
            rows.append([f["orden"], f["escuela_codigo"], f["escuela_nombre"],
                         InvoiceStatus.LABELS.get(f["estado"], f["estado"]),
                         PrintStatus.LABELS.get(f["estado_impresion"], f["estado_impresion"]),
                         f["intentos_recuperacion"], f["etapa"], f["mensaje"]])
            ids.append(f["id"])
            colors.append(STATUS_COLORS.get(f["estado"]))
        fill_table(self.table, rows, ids, colors)

    def _on_event(self, ev: dict):
        self.log.insertItem(0, f"{ev['fecha_hora'][11:]}  {ev['escuela_codigo']:>6}  {ev['mensaje']}")
        if self.log.count() > 500:
            self.log.takeItem(self.log.count() - 1)

    # ------------------------------------------------------------ ejecución
    def _mode(self) -> str:
        if self.r_auto.isChecked():
            return Mode.AUTOMATICO
        if self.r_test.isChecked():
            return Mode.PRUEBA
        return Mode.SIMULADO

    def _start(self, **kw):
        day = self.current_day()
        if not day:
            return error(self, "Cree o seleccione una jornada.")
        mode = self._mode()
        if mode == Mode.PRUEBA and len(kw.get("invoice_ids") or []) != 1:
            return error(self, "En modo de prueba seleccione UNA escuela y use "
                               "«Ejecutar escuela seleccionada».")
        if mode != Mode.SIMULADO and not confirm(
                self, "SisFaCon real",
                "Se va a controlar SisFaCon Express.\n\n"
                "• Abra la pantalla «Registro de Conduce a Centro Educativo» con un formulario nuevo.\n"
                "• Verifique la FECHA en SisFaCon.\n• No use el teclado ni el ratón mientras trabaja.\n"
                "• Emergencia: ratón a la esquina superior izquierda.\n\n¿Continuar?"):
            return
        self.ctl.start(day["id"], RunOptions(mode=mode, confirm_each=self.confirm_each.isChecked(),
                                             **kw))

    def run_all(self):
        self._start()

    def run_group(self):
        self._start(limit=self.group_n.value())

    def run_selected(self):
        ids = selected_ids(self.table)
        if len(ids) != 1:
            return error(self, "Seleccione una escuela de la tabla.")
        inv = self.app.days.invoice(ids[0])
        if inv["estado"] != InvoiceStatus.PENDIENTE:
            return error(self, "Solo se pueden ejecutar facturas pendientes. Si verificó en SisFaCon "
                               "que no existe, use «Marcar pendiente».")
        self._start(invoice_ids=ids)

    # --------------------------------------------------- acciones manuales
    def _menu(self, pos):
        m = QMenu(self)
        m.addAction("Ejecutar esta escuela", self.run_selected)
        m.addSeparator()
        m.addAction("Marcar pendiente (verifiqué que NO existe)", self.mark_pending)
        m.addAction("Marcar completada", self.mark_done)
        m.addAction("Omitir", self.mark_skip)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _guard(self) -> list[int]:
        if self.ctl.running:
            error(self, "Detenga la automatización antes de cambiar estados.")
            return []
        return selected_ids(self.table)

    def mark_pending(self):
        ids = self._guard()
        if ids and confirm(self, "Marcar pendiente",
                           "Solo haga esto si comprobó en SisFaCon que el conduce de estas escuelas "
                           "NO existe. Si existe, se crearía un duplicado.\n\n¿Continuar?"):
            for i in ids:
                self.app.days.reset_to_pending(i)
                self.app.logger.log("INFO", "Marcada como pendiente por el usuario.",
                                    factura=self.app.days.invoice(i))
            self.refresh_invoices()

    def mark_done(self):
        ids = self._guard()
        if ids and confirm(self, "Marcar completada", "¿Confirmó en SisFaCon que el conduce existe?"):
            printed = confirm(self, "Impresión", "¿También está impreso?")
            for i in ids:
                self.app.days.mark_completed_manually(i, printed)
                self.app.logger.log("INFO", "Marcada como completada por el usuario.",
                                    factura=self.app.days.invoice(i))
            self.refresh_invoices()

    def mark_skip(self):
        ids = self._guard()
        if ids and confirm(self, "Omitir", f"¿Omitir {len(ids)} escuela(s) en esta jornada?"):
            for i in ids:
                self.app.days.skip(i)
            self.refresh_invoices()
