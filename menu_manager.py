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


# ---------------------------------------------------------------- importación
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}
DAY_KEYS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"]


def parse_week(value) -> int | None:
    """«1», «I», «Semana 2», «SEMANA III» → número de semana (1..5); si no, None."""
    import re
    text = str(value or "").upper().replace("SEMANA", "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    if text in _ROMAN:
        return _ROMAN[text]
    if re.fullmatch(r"\d", text) and 1 <= int(text) <= SEMANAS:
        return int(text)
    return None


def parse_cell(text: str) -> tuple[str, str]:
    """«Pan — 1000», «Pan - 1000», «Pan (1000)», «1000» o «Pan» → (nombre, código)."""
    import re
    text = str(text or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if re.fullmatch(r"\d+", text):
        return "", text
    m = re.fullmatch(r"(.*?)\s*(?:[—–\-:/|]\s*|\(\s*)(\d+)\s*\)?", text)
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2)
    return re.sub(r"[\s—–\-:/|(]+$", "", text), ""     # «Pan —» sin código


def import_menu(menu: "MenuManager", rows: list[dict], products: list[dict]) -> dict:
    """Carga el menú desde filas {semana, lunes … sabado}. NO crea productos.

    Cada casilla puede tener el nombre, el código o «nombre — código». Con código
    se busca por código; con solo nombre, por nombre exacto (sin mayúsculas ni
    acentos). Lo que no esté en Productos se informa y la casilla no cambia.
    Las casillas vacías tampoco cambian nada.
    """
    from verification import normalize_text
    by_name, by_code = {}, {}
    for p in products:
        by_code[str(p.get("codigo"))] = p
        for key in (p.get("nombre"), p.get("texto_verificacion")):
            if key:
                by_name.setdefault(normalize_text(key), p)
    report = {"asignadas": 0, "faltan": {}, "errores": []}
    for n, row in enumerate(rows, start=2):
        week = parse_week(row.get("semana"))
        if week is None:
            if any(str(v or "").strip() for v in row.values()):
                report["errores"].append(f"Fila {n}: semana «{row.get('semana')}» no válida (1 a 5).")
            continue
        for dia, key in enumerate(DAY_KEYS):
            cell = str(row.get(key) or "").strip()
            if not cell:
                continue
            name, code = parse_cell(cell)
            p = by_code.get(code) if code else by_name.get(normalize_text(name))
            if p:
                menu.set(week, dia, p["id"])
                report["asignadas"] += 1
            else:
                label = f"{name} — {code}" if name and code else (name or f"código {code}")
                report["faltan"].setdefault(label, []).append(MenuManager.label(week, dia))
    return report
