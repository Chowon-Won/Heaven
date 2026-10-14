"""Controlador de la automatización: ejecuta el motor en un hilo aparte para
que la interfaz siga respondiendo, y traduce sus avisos en señales Qt."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QMessageBox

from automation import AutomationEngine, EngineUI, FlowAbort, RunOptions
from day_manager import Mode


class _Bridge(EngineUI):
    """Implementación de EngineUI que se ejecuta en el hilo del motor."""

    def __init__(self, ctl: "AutomationController"):
        self.ctl = ctl

    def ask(self, title, message, options):
        box = {"answer": options[-1], "event": threading.Event()}
        self.ctl._ask_request.emit(title, message, options, box)
        box["event"].wait()
        return box["answer"]

    def notify(self, level, title, message):
        self.ctl.notified.emit(level, title, message)

    def on_state(self, state, label):
        self.ctl.state_changed.emit(state.value, label)

    def on_invoice(self, invoice):
        self.ctl.invoice_changed.emit(dict(invoice))


class AutomationController(QObject):
    state_changed = Signal(str, str)
    invoice_changed = Signal(dict)
    event_logged = Signal(dict)
    notified = Signal(str, str, str)
    running_changed = Signal(bool)
    finished = Signal(str)
    _ask_request = Signal(str, str, list, object)

    def __init__(self, app_ctx, parent=None):
        super().__init__(parent)
        self.app = app_ctx
        self.engine: AutomationEngine | None = None
        self._thread: threading.Thread | None = None
        self.day_id: int | None = None
        self._ask_request.connect(self._on_ask)
        self.app.logger.listeners.append(lambda ev: self.event_logged.emit(dict(ev)))
        self.parent_widget = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def paused(self) -> bool:
        return bool(self.engine and self.engine.paused and self.running)

    # ---------------------------------------------------------------- acciones
    def start(self, day_id: int, options: RunOptions) -> None:
        if self.running:
            QMessageBox.information(self.parent_widget, "En marcha",
                                    "La automatización ya está en marcha.")
            return
        self.day_id = day_id
        self._thread = threading.Thread(target=self._run, args=(day_id, options), daemon=True)
        self._thread.start()
        self.running_changed.emit(True)

    def _run(self, day_id: int, options: RunOptions) -> None:
        summary = ""
        com = None
        try:
            if options.mode != Mode.SIMULADO:
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                    com = pythoncom
                except Exception:
                    pass
            driver = self.app.make_driver(Mode.SIMULADO if options.mode == Mode.SIMULADO
                                          else Mode.AUTOMATICO)
            self.engine = AutomationEngine(driver, self.app.days, self.app.logger,
                                           self.app.settings, _Bridge(self),
                                           capture_dir=self.app.capture_dir)
            summary = self.engine.run(day_id, options)
        except FlowAbort as exc:
            summary = exc.message
            self.notified.emit("ERROR", "No se puede iniciar", exc.message)
        except Exception as exc:
            summary = f"Error: {exc}"
            self.notified.emit("ERROR", "Error", str(exc))
        finally:
            if com:
                try:
                    com.CoUninitialize()
                except Exception:
                    pass
            self.running_changed.emit(False)
            self.finished.emit(summary)

    def pause(self):
        if self.engine and self.running:
            self.engine.pause()
            self.state_changed.emit("PAUSING", "Pausando en el siguiente punto seguro…")

    def resume(self):
        if self.engine:
            self.engine.resume()

    def stop(self):
        if self.engine and self.running:
            self.engine.stop()
            self.state_changed.emit("STOPPING",
                                    "Deteniendo: se termina el paso seguro actual…")

    # ------------------------------------------------------------- preguntas
    @Slot(str, str, list, object)
    def _on_ask(self, title, message, options, box):
        mb = QMessageBox(self.parent_widget)
        mb.setWindowTitle(title)
        mb.setText(message)
        mb.setIcon(QMessageBox.Question)
        buttons = {}
        for i, opt in enumerate(options):
            role = QMessageBox.AcceptRole if i == 0 else QMessageBox.RejectRole \
                if i == len(options) - 1 else QMessageBox.ActionRole
            buttons[mb.addButton(opt, role)] = opt
        mb.exec()
        box["answer"] = buttons.get(mb.clickedButton(), options[-1])
        box["event"].set()
