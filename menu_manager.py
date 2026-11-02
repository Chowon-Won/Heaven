"""Menú de productos: 5 semanas × (lunes a viernes + sábado)."""
from __future__ import annotations

import calendar
from datetime import date

from database import Database

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
SEMANAS = 5


def week_of_month(d: date) -> int:
    """Semana del menú (1..5) a la que pertenece la fecha.

    Semanas de calendario de lunes a domingo. La semana 1 es la primera que tiene
    algún día de lunes a sábado dentro del mes (si el mes empieza en domingo, ese
    domingo no cuenta). Si un mes llegara a una 6.ª semana, vuelve a la semana 1.
    """
    first = d.replace(day=1)
    offset = first.weekday()                 # 0 = lunes … 6 = domingo
    if offset == 6:                          # empieza en domingo: semana vacía
        offset = -1
    week = (d.day + offset - 1) // 7 + 1
    return (week - 1) % SEMANAS + 1


def menu_day(d: date) -> int | None:
    """0..5 (lunes..sábado) o None si es domingo."""
    wd = d.weekday()
    return None if wd == 6 else wd


class MenuManager:
    def __init__(self, db: Database):
        self.db = db

    def get(self, semana: int, dia: int) -> int | None:
        row = self.db.query_one("SELECT producto_id FROM menu WHERE semana = ? AND dia = ?",
                                (semana, dia))
        return row["producto_id"] if row else None

    def set(self, semana: int, dia: int, producto_id: int | None) -> None:
        if producto_id:
            self.db.execute("INSERT INTO menu(semana, dia, producto_id) VALUES(?,?,?) "
                            "ON CONFLICT(semana, dia) DO UPDATE SET producto_id = excluded.producto_id",
                            (semana, dia, producto_id))
        else:
            self.db.execute("DELETE FROM menu WHERE semana = ? AND dia = ?", (semana, dia))

    def grid(self) -> dict[tuple[int, int], int]:
        return {(r["semana"], r["dia"]): r["producto_id"]
                for r in self.db.query("SELECT * FROM menu")}

    def product_for_date(self, d: date) -> tuple[int | None, int, int | None]:
        """(producto_id del menú o None, semana, día 0..5 o None si domingo)."""
        semana, dia = week_of_month(d), menu_day(d)
        if dia is None:
            return None, semana, None
        pid = self.get(semana, dia)
        if pid:
            p = self.db.query_one("SELECT id FROM productos WHERE id = ? AND eliminado = 0 "
                                  "AND activo = 1", (pid,))
            pid = p["id"] if p else None
        return pid, semana, dia

    @staticmethod
    def label(semana: int, dia: int | None) -> str:
        return f"Semana {semana}, {DIAS[dia] if dia is not None else 'Domingo'}"
