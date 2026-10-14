"""Utilidades comunes de las pruebas unitarias (sin SisFaCon real)."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_context import AppContext  # noqa: E402
from automation import AutomationEngine, EngineUI, RunOptions  # noqa: E402
from day_manager import Mode  # noqa: E402
from simulator import SimulatedDriver  # noqa: E402

FAST = {
    "intervalo_sondeo": 0.01, "espera_tras_tecla": 0.0, "timeout_ventana": 0.5,
    "timeout_guardado": 0.5, "timeout_impresion": 0.5, "espera_estabilizacion": 0.0,
    "espera_tras_imprimir": 0.0, "capturas_en_error": False,
}


def make_ctx(n_schools: int = 3) -> AppContext:
    ctx = AppContext.create(db_path=":memory:")
    ctx.settings.update(FAST)
    for i in range(n_schools):
        ctx.schools.add(codigo=f"0{2950 + i}", nombre=f"ESCUELA PRUEBA {i + 1}")
    return ctx


class RecordingUI(EngineUI):
    """Responde automáticamente y guarda lo que el motor comunica."""

    def __init__(self, answers: dict[str, str] | None = None):
        self.answers = answers or {}
        self.asked: list[tuple[str, str]] = []
        self.notifications: list[tuple[str, str, str]] = []
        self.states: list[str] = []
        self.on_invoice_hook = None

    def ask(self, title, message, options):
        self.asked.append((title, message))
        return self.answers.get(title, options[0])

    def notify(self, level, title, message):
        self.notifications.append((level, title, message))

    def on_state(self, state, label):
        self.states.append(state.value)

    def on_invoice(self, invoice):
        if self.on_invoice_hook:
            self.on_invoice_hook(invoice)


def make_day(ctx: AppContext, product_code: str = "1000", fecha: str = "2026-10-14",
             mode: str = Mode.SIMULADO) -> int:
    product = ctx.products.get_by_code(product_code)
    schools = ctx.schools.list(only_active=True)
    return ctx.days.create_day(fecha, product, schools, mode)


def make_engine(ctx: AppContext, driver: SimulatedDriver | None = None,
                ui: RecordingUI | None = None):
    driver = driver or ctx.make_driver(Mode.SIMULADO, step_delay=0)
    ui = ui or RecordingUI()
    return AutomationEngine(driver, ctx.days, ctx.logger, ctx.settings, ui), driver, ui


def run_in_thread(engine: AutomationEngine, day_id: int, options: RunOptions | None = None):
    result = {}
    t = threading.Thread(target=lambda: result.setdefault(
        "summary", engine.run(day_id, options or RunOptions())), daemon=True)
    t.start()
    return t, result
