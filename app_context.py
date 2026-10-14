"""Crea y agrupa los servicios de la aplicación (sin interfaz gráfica)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import config
from config import Settings
from database import Database
from day_manager import DayManager, Mode
from logging_manager import OperationLogger
from product_manager import ProductManager
from school_manager import SchoolManager


@dataclass
class AppContext:
    db: Database
    settings: Settings
    schools: SchoolManager
    products: ProductManager
    days: DayManager
    logger: OperationLogger
    data_dir: Path | None

    @classmethod
    def create(cls, db_path: str | Path | None = None, data_dir: Path | None = None,
               seed: bool = True) -> "AppContext":
        if db_path is None:
            data_dir = data_dir or config.data_dir()
            db_path = data_dir / "autofacturador.sqlite3"
        db = Database(db_path)
        ctx = cls(db=db, settings=Settings(db), schools=SchoolManager(db),
                  products=ProductManager(db), days=DayManager(db),
                  logger=OperationLogger(db, (data_dir / "registros") if data_dir else None),
                  data_dir=data_dir)
        if seed:
            ctx.products.seed_examples_if_empty()
        from calibration import drop_untouched_defaults
        cal, removed = drop_untouched_defaults(ctx.settings["calibracion"])
        if removed:
            ctx.settings.set("calibracion", cal)
            ctx.logger.log("INFO", "Calibración: se quitaron campos que estaban en su posición "
                           "inicial sin colocar: " + ", ".join(removed), "AVISO")
        return ctx

    def make_driver(self, mode: str, step_delay: float = 0.25):
        """Driver simulado o real según el modo."""
        if mode == Mode.SIMULADO:
            from simulator import SimulatedDriver
            clients = {s["codigo"]: s["nombre"] for s in self.schools.list(include_deleted=True)}
            products = {p["codigo"]: (p["texto_verificacion"] or p["nombre"]).upper()
                        for p in self.products.list(include_deleted=True)}
            return SimulatedDriver(clients, products, step_delay=step_delay)
        from window_detection import RealDriver
        return RealDriver(self.settings)

    @property
    def capture_dir(self) -> Path | None:
        return (self.data_dir / "capturas") if self.data_dir else None
