"""Herramienta de calibración (solo Windows).

El usuario coloca el ratón sobre el elemento de SisFaCon y la aplicación
guarda la posición RELATIVA a la ventana correspondiente, junto con el
tamaño de la ventana en ese momento. Si después la ventana tiene otro
tamaño, el motor se detiene en lugar de hacer clic en un sitio equivocado.
"""
from __future__ import annotations

import sys

from config import CALIBRATION_FIELDS


def cursor_position() -> tuple[int, int]:
    if sys.platform.startswith("win"):
        import win32api
        return win32api.GetCursorPos()
    raise RuntimeError("La calibración solo está disponible en Windows.")


class Calibrator:
    def __init__(self, settings, driver):
        self.settings = settings
        self.driver = driver  # RealDriver

    def _window_rect(self, field_name: str):
        which = CALIBRATION_FIELDS[field_name]["ventana"]
        if which == "principal" and not self.driver.find_main():
            raise RuntimeError("Abra SisFaCon en «Registro de Conduce a Centro Educativo».")
        return self.driver.window_rect(which)

    def save_point(self, field_name: str, pos: tuple[int, int]) -> dict:
        """Guarda un punto (región pequeña de 6x6 alrededor del cursor)."""
        return self.save_region(field_name, (pos[0] - 3, pos[1] - 3), (pos[0] + 3, pos[1] + 3))

    def save_region(self, field_name: str, p1: tuple[int, int], p2: tuple[int, int]) -> dict:
        left, top, width, height = self._window_rect(field_name)
        x1, x2 = sorted((p1[0], p2[0]))
        y1, y2 = sorted((p1[1], p2[1]))
        if not (left <= x1 and x2 <= left + width and top <= y1 and y2 <= top + height):
            raise RuntimeError("La posición está fuera de la ventana de SisFaCon.")
        meta = CALIBRATION_FIELDS[field_name]
        cal = dict(self.settings["calibracion"] or {})
        previous = cal.get(field_name, {})
        entry = {
            "ventana": meta["ventana"], "tipo": meta["tipo"],
            "x": x1 - left, "y": y1 - top,
            "w": max(2, x2 - x1), "h": max(2, y2 - y1),
            "metodo": previous.get("metodo", "auto"),
            "ancho_ventana": width, "alto_ventana": height,
        }
        cal[field_name] = entry
        self.settings.set("calibracion", cal)
        return entry

    def set_method(self, field_name: str, method: str) -> None:
        cal = dict(self.settings["calibracion"] or {})
        if field_name in cal:
            cal[field_name] = {**cal[field_name], "metodo": method}
            self.settings.set("calibracion", cal)

    def remove(self, field_name: str) -> None:
        cal = dict(self.settings["calibracion"] or {})
        cal.pop(field_name, None)
        self.settings.set("calibracion", cal)

    def test_read(self, field_name: str) -> str:
        """Lee el campo y describe con qué método se obtuvo."""
        entry = (self.settings["calibracion"] or {}).get(field_name)
        if not entry:
            return "Sin calibrar."
        if entry["tipo"] == "punto" and field_name != "descripcion_producto":
            x, y, w, h = self.driver.absolute_rect(field_name)
            return f"Punto en pantalla: ({x + w // 2}, {y + h // 2}). Correcto si cae sobre el elemento."
        x, y, w, h = self.driver.absolute_rect(field_name)
        ctrl = self.driver._control_text_at(x, y, w, h)
        ocr = None
        if entry.get("metodo") != "control":
            ocr = self.driver.ocr.read_rect((x, y, w, h))
        parts = [f"Control de Windows: «{ctrl}»" if ctrl else "Control de Windows: (sin texto)"]
        if entry.get("metodo") != "control":
            parts.append(f"OCR: «{ocr}»" if ocr else
                         "OCR: (sin resultado — ¿Tesseract instalado?)")
        parts.append(f"Lectura usada por el macro: «{self.driver.read_field(field_name)}»")
        return "\n".join(parts)


# ----------------------------------------------------------------------------
# Calibración con celdas arrastrables: conversión entre recuadros en pantalla
# (coordenadas lógicas de Qt, relativas a la ventana de SisFaCon) y entradas
# de calibración (píxeles reales, relativos a la misma ventana).
# ----------------------------------------------------------------------------
DEFAULT_SIZES = {"region": (170, 26), "punto": (40, 22)}


def fields_for_window(ventana: str) -> list[str]:
    return [name for name, meta in CALIBRATION_FIELDS.items() if meta["ventana"] == ventana]


def entries_to_boxes(cal: dict, ventana: str, ratio: float) -> dict[str, tuple[int, int, int, int]]:
    """Recuadros iniciales (x, y, w, h lógicos). Usa la calibración guardada o,
    si un campo no está calibrado, una posición escalonada para arrastrarlo."""
    ratio = ratio or 1.0
    boxes = {}
    pending = 0
    for name in fields_for_window(ventana):
        entry = (cal or {}).get(name)
        if entry:
            x, y = entry["x"], entry["y"]
            w, h = entry.get("w", 1), entry.get("h", 1)
            if entry.get("tipo") == "punto" and w < 20:   # puntos antiguos de 6x6
                cx, cy = x + w / 2, y + h / 2
                dw, dh = DEFAULT_SIZES["punto"]
                x, y, w, h = cx - dw * ratio / 2, cy - dh * ratio / 2, dw * ratio, dh * ratio
            w, h = max(w, 8), max(h, 8)
            boxes[name] = (round(x / ratio), round(y / ratio), round(w / ratio), round(h / ratio))
        else:
            dw, dh = DEFAULT_SIZES[CALIBRATION_FIELDS[name]["tipo"]]
            boxes[name] = (40 + 30 * pending, 120 + 44 * pending, dw, dh)
            pending += 1
    return boxes


def boxes_to_entries(boxes: dict, cal: dict, ventana: str, ratio: float,
                     window_size: tuple[int, int], removed: set[str] = frozenset()) -> dict:
    """Nueva calibración completa a partir de los recuadros colocados."""
    ratio = ratio or 1.0
    out = dict(cal or {})
    win_w, win_h = window_size
    for name in fields_for_window(ventana):
        if name in removed:
            out.pop(name, None)
            continue
        if name not in boxes:
            continue
        x, y, w, h = boxes[name]
        px, py = round(x * ratio), round(y * ratio)
        pw, ph = max(2, round(w * ratio)), max(2, round(h * ratio))
        # Se recorta a la ventana: un recuadro fuera de SisFaCon no sirve.
        px, py = max(0, min(px, win_w - 2)), max(0, min(py, win_h - 2))
        pw, ph = min(pw, win_w - px), min(ph, win_h - py)
        meta = CALIBRATION_FIELDS[name]
        out[name] = {"ventana": meta["ventana"], "tipo": meta["tipo"],
                     "x": px, "y": py, "w": pw, "h": ph,
                     "metodo": (out.get(name) or {}).get("metodo", "auto"),
                     "ancho_ventana": win_w, "alto_ventana": win_h}
    return out
