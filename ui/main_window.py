"""Ventana principal con las 7 pestañas."""
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from config import APP_NAME, APP_VERSION
from day_manager import Mode
from ui.automation_tab import AutomationTab
from ui.catalog_tab import CatalogTab
from ui.controller import AutomationController
from ui.dashboard_tab import DashboardTab
from ui.day_tab import DayTab
from ui.history_tab import HistoryTab
from ui.settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self, app_ctx):
        super().__init__()
        self.app = app_ctx
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1250, 800)
        self.ctl = AutomationController(app_ctx, self)
        self.ctl.parent_widget = self
        self.ctl.notified.connect(self._notify)
        self.ctl.finished.connect(self._finished)

        self.tabs = QTabWidget()
        self.automation = AutomationTab(app_ctx, self.ctl)
        self.dashboard = DashboardTab(app_ctx, self.ctl, self.automation)
        self.schools = CatalogTab(app_ctx, "escuelas")
        self.products = CatalogTab(app_ctx, "productos")
        self.day = DayTab(app_ctx)
        self.history = HistoryTab(app_ctx)
        self.settings = SettingsTab(app_ctx, self.ctl)
        for w, title in ((self.dashboard, "Panel principal"), (self.schools, "Escuelas"),
                         (self.products, "Productos"), (self.day, "Nueva jornada"),
                         (self.automation, "Automatización"), (self.history, "Historial y registros"),
                         (self.settings, "Configuración")):
            self.tabs.addTab(w, title)
        self.setCentralWidget(self.tabs)

        self.schools.changed.connect(self.dashboard.refresh)
        self.products.changed.connect(lambda: self.day.reload_products())
        self.day.day_created.connect(self._day_created)
        self.day.open_catalog.connect(lambda _k: self.tabs.setCurrentWidget(self.products))
        self.tabs.currentChanged.connect(self._tab_changed)
        self.statusBar().showMessage(f"Datos en {app_ctx.data_dir}")

    def _tab_changed(self, _i):
        w = self.tabs.currentWidget()
        if w is self.automation:
            self.automation.reload_days()
            self.automation._day_changed()
        elif w in (self.schools, self.products):
            w.refresh()

    def _day_created(self, day_id: int):
        self.automation.reload_days(day_id)
        self.tabs.setCurrentWidget(self.automation)

    def open_day(self, day_id: int):
        self.automation.reload_days(day_id)
        self.tabs.setCurrentWidget(self.automation)

    def _notify(self, level, title, message):
        (QMessageBox.critical if level == "ERROR" else QMessageBox.information)(self, title, message)

    def _finished(self, summary: str):
        self.automation.reload_days()
        self.dashboard.refresh()
        self.statusBar().showMessage(summary, 15000)

    def closeEvent(self, event):
        if self.ctl.running:
            if QMessageBox.question(self, "Automatización en marcha",
                                    "La automatización sigue en marcha. ¿Detenerla y salir?\n"
                                    "La factura en curso quedará registrada para revisión.") \
                    != QMessageBox.Yes:
                event.ignore()
                return
            self.ctl.stop()
        event.accept()


def handle_interrupted(window: MainWindow) -> None:
    """Al abrir: detecta jornadas que quedaron a medias por un cierre inesperado."""
    app = window.app
    for day in app.days.find_interrupted():
        affected = app.days.mark_interrupted(day["id"])
        app.logger.log("JORNADA_INTERRUMPIDA", jornada=day)
        c = app.days.counts(day["id"])
        detail = "\n".join(f"• {f['escuela_codigo']} — {f['escuela_nombre']}: "
                           + ("se había enviado Ctrl+G" if f["guardado_intentado"] else
                              "estaba en preparación") for f in affected)
        box = QMessageBox(window)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Jornada interrumpida")
        box.setText(
            f"La jornada #{day['id']} del {day['fecha']} ({day['producto_nombre']}) se interrumpió.\n\n"
            f"Completadas: {c['completadas']} · Pendientes: {c['pendientes']} · "
            f"En revisión: {c['revision']}\n\n"
            + (("Estas facturas tienen estado incierto y NO se reanudarán solas; compruébelas en "
                f"SisFaCon:\n{detail}\n\n") if affected else "")
            + "Las facturas completadas no se repetirán.")
        review = box.addButton("Revisar la jornada", QMessageBox.AcceptRole)
        resume = box.addButton("Reanudar las pendientes", QMessageBox.ActionRole)
        box.addButton("Más tarde", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() in (review, resume):
            window.open_day(day["id"])
        if box.clickedButton() == resume:
            if day["modo"] == Mode.SIMULADO:
                window.automation.run_all()
            else:
                QMessageBox.information(
                    window, "Reanudar",
                    "Compruebe que SisFaCon está abierto con un formulario nuevo y pulse "
                    "«Ejecutar todas las seleccionadas». Solo se procesarán las pendientes.")
