"""SisFaCon Express simulado en memoria.

Reproduce el flujo confirmado:
  F7 -> «Seleccione un Cliente» -> Texto búsqueda -> Enter
  Código de producto -> Enter
  Ctrl+G -> ventana «Preview - [No name]»
  F9 (en la vista previa) -> diálogo «Print» -> Enter -> Esc

Permite inyectar fallos (violación de acceso, escuela equivocada, producto
desconocido, ventanas desconocidas...) para probar la lógica sin tocar la
aplicación real. No guarda ni imprime nada fuera de la memoria.
"""
from __future__ import annotations

import itertools
import threading
import time

from window_detection import DriverError, EmergencyStop, SisFaConDriver, WinInfo

AV_TITLE = "SisFaCon Express - Menú Principal"
AV_TEXT = ("[Violación de acceso en la dirección {a1} en módulo 'sisfaconexpress.exe'. "
           "Leer de dirección {a2}. Pulse Ok para continuar]")
CONTADO = ("PERSONAL", "<<CONTADO>>")


class SimulatedDriver(SisFaConDriver):
    simulated = True

    def __init__(self, clients: dict[str, str] | None = None,
                 products: dict[str, str] | None = None,
                 step_delay: float = 0.0, start_conduce: int = 83941):
        self.clients = dict(clients or {})
        self.products = dict(products or {})
        self.step_delay = step_delay
        self._lock = threading.RLock()
        self._handles = itertools.count(1000)
        self._addr = itertools.count(0x00402DE1, 0x37)
        self.main_open = True
        self.main_handle = 1
        self.windows: dict[int, dict] = {}
        self.foreground = self.main_handle
        self.school = CONTADO
        self.cell_focused = False
        self.cell_buffer = ""
        self.entry_desc = ""
        self.lines: list[tuple[str, str]] = []
        self.last_conduce = start_conduce
        self.label_stale = False
        self.saved: list[dict] = []
        self.printed: list[str] = []
        self.keys_log: list[tuple[str, str]] = []
        self.print_without_preview = 0
        self.ok_presses: list[str] = []
        self.faults: list[dict] = []
        self.emergency = False
        self.counter_unreadable = False   # imita un OCR que no lee «Linea(s)»
        self.conduce_unreadable = False   # imita un OCR que no lee «CONDUCE: FCR …»
        self.search_names_only = False    # la búsqueda solo filtra por nombre
        self.no_match_selects_first = False  # Enter sin resultados elige la 1.ª fila
        self.keeps_school_after_save = False  # tras grabar no vuelve a <<CONTADO>>

    # ------------------------------------------------------------ fallos
    def inject(self, event: str, code: str | None = None, times: int = 1, **kw) -> None:
        self.faults.append({"event": event, "code": code, "times": times, **kw})

    def _fault(self, event: str, code: str | None = None) -> dict | None:
        for f in self.faults:
            if f["event"] == event and f["times"] != 0 and (f["code"] in (None, code)):
                if f["times"] > 0:
                    f["times"] -= 1
                return f
        return None

    # ---------------------------------------------------------- ventanas
    def _open(self, kind: str, title: str, text: str = "", cls: str = "TForm",
              buttons: list[str] | None = None) -> int:
        h = next(self._handles)
        self.windows[h] = {"kind": kind, "info": WinInfo(h, title, cls, text, buttons or [])}
        self.foreground = h
        return h

    def _close(self, h: int) -> None:
        self.windows.pop(h, None)
        self.foreground = max(self.windows) if self.windows else self.main_handle

    def _open_av(self) -> None:
        text = AV_TEXT.format(a1=f"{next(self._addr):08X}", a2=f"{next(self._addr):08X}")
        self._open("av", AV_TITLE, text, "#32770", ["OK"])

    def _of_kind(self, kind: str) -> int | None:
        for h, w in self.windows.items():
            if w["kind"] == kind:
                return h
        return None

    def _delay(self):
        if self.step_delay:
            time.sleep(self.step_delay)

    # ----------------------------------------------------- interfaz driver
    def find_main(self) -> bool:
        return self.main_open

    def focus_main(self) -> None:
        self.focus_window(self.main_handle)

    def focus_window(self, handle: int) -> None:
        self._check()
        if handle == self.main_handle:
            if not self.main_open:
                raise DriverError("SisFaCon no está abierto.")
        elif handle not in self.windows:
            raise DriverError("La ventana ya no existe.")
        self.foreground = handle

    def capture_baseline(self) -> list[WinInfo]:
        return self.list_windows()

    def list_windows(self) -> list[WinInfo]:
        with self._lock:
            return [w["info"] for w in self.windows.values()]

    def window_exists(self, handle: int) -> bool:
        return handle in self.windows or (handle == self.main_handle and self.main_open)

    def _modal_open(self) -> bool:
        return bool(self.windows)

    def send_keys(self, keys: str, handle: int | None = None) -> None:
        self._check()
        self._delay()
        target = handle or self.main_handle
        self.focus_window(target)
        with self._lock:
            kind = "main" if target == self.main_handle else self.windows[target]["kind"]
            self.keys_log.append((kind, keys))
            k = keys.upper()
            if kind == "main":
                if self._modal_open():
                    return  # la ventana principal no responde con modales abiertos
                if k == "{F7}":
                    self._open("search", "Seleccione un Cliente", "Texto búsqueda")
                    self.windows[self.foreground]["search"] = ""
                elif k == "{ENTER}" and self.cell_focused:
                    self._enter_product()
                elif k == "^G":
                    self._save()
                elif k == "{F9}":
                    self.print_without_preview += 1
            elif kind == "search":
                if k == "{ENTER}":
                    self._confirm_search(target)
                elif k == "{ESC}":
                    self._close(target)
            elif kind == "preview":
                if k == "{F9}":
                    if self._fault("av_on_print"):
                        self._open_av()
                    else:
                        self._open("print", "Print", "Printer\nName: EPSON LX-350 ESC/P",
                                   "#32770", ["OK", "Cancel"])
                elif k == "{ESC}":
                    self._close(target)
                    if self._fault("unknown_after_preview"):
                        self._open("other", "Aviso", "Mensaje desconocido", "#32770", ["OK"])
            elif kind == "print":
                if k == "{ENTER}":
                    self._do_print(target)
                elif k == "{ESC}":
                    self._close(target)
            elif kind in ("av", "other"):
                if k == "{ENTER}":
                    self.ok_presses.append(self.windows[target]["info"].title)
                    self._close(target)

    def press_ok(self, win: WinInfo) -> None:
        self._check()
        with self._lock:
            if win.handle not in self.windows:
                raise DriverError("La ventana ya no existe.")
            w = self.windows[win.handle]
            self.ok_presses.append(w["info"].title)
            if w["kind"] == "print":
                self._do_print(win.handle)
            else:
                self._close(win.handle)

    def type_search_text(self, search_handle: int, text: str) -> None:
        self._check()
        self._delay()
        with self._lock:
            if search_handle not in self.windows:
                raise DriverError("La búsqueda no está abierta.")
            self.windows[search_handle]["search"] = text

    def click_point(self, name: str, window_handle: int | None = None) -> None:
        self._check()
        if name == "celda_codigo_producto":
            if self._modal_open():
                return
            self.cell_focused = True
            self.cell_buffer = ""

    def type_text(self, text: str) -> None:
        self._check()
        self._delay()
        if self.cell_focused and not self._modal_open():
            self.cell_buffer += text

    def is_calibrated(self, name: str) -> bool:
        return True

    def read_field(self, name: str) -> str | None:
        with self._lock:
            if name == "codigo_centro":
                return self.school[0]
            if name == "nombre_centro":
                return self.school[1]
            if name == "ultimo_conduce":
                if self.conduce_unreadable:
                    return None
                return f"CONDUCE: FCR {self.last_conduce - (1 if self.label_stale else 0):07d}"
            if name == "contador_lineas":
                return None if self.counter_unreadable else f"{len(self.lines)} Linea(s)"
            if name == "descripcion_producto":
                return self.entry_desc or (self.lines[-1][1] if self.lines else "")
        return None

    def emergency_requested(self) -> bool:
        return self.emergency

    def _check(self):
        if self.emergency:
            raise EmergencyStop("Parada de emergencia (simulada).")

    # ------------------------------------------------------- lógica interna
    def _confirm_search(self, handle: int) -> None:
        text = self.windows[handle].get("search", "").strip()
        match = None
        if text in self.clients and not self.search_names_only:
            match = (text, self.clients[text])
        else:
            for c, n in self.clients.items():
                if text and text.upper() in n.upper():
                    match = (c, n)
                    break
        if match is None:
            if not self.no_match_selects_first or not self.clients:
                return            # sin resultados: la búsqueda sigue abierta
            first = next(iter(self.clients))
            match = (first, self.clients[first])
        self._close(handle)
        if self._fault("av_on_select", text):
            self._open_av()
            return
        if match is None:
            return
        wrong = self._fault("wrong_school", text)
        if wrong:
            others = [(c, n) for c, n in self.clients.items() if c != match[0]]
            match = others[0] if others else ("99999", "OTRA ESCUELA")
        self.school = match
        self.cell_focused = False
        if self._fault("av_after_select", text):
            self._open_av()
        if self._fault("unknown_after_select", text):
            self._open("other", "Aviso", "Mensaje desconocido", "#32770", ["OK"])

    def _enter_product(self) -> None:
        code = self.cell_buffer.strip()
        self.cell_buffer = ""
        if self._fault("unknown_product", code) or code not in self.products:
            self.entry_desc = ""
            return
        desc = self.products[code]
        if self._fault("wrong_product_desc", code):
            desc = "PRODUCTO DIFERENTE"
        self.lines.append((code, desc))
        self.entry_desc = ""
        self.cell_focused = False

    def _save(self) -> None:
        code = self.school[0]
        if self._fault("save_ignored", code):
            return
        if self.school == CONTADO or not self.lines:
            self._open("other", "Información", "Debe seleccionar un centro y un artículo",
                       "#32770", ["OK"])
            return
        if self._fault("av_on_save_not_saved", code):
            self._open_av()
            return
        self.last_conduce += 1
        conduce = f"FCR {self.last_conduce:07d}"
        self.saved.append({"conduce": conduce, "escuela": code,
                           "productos": [c for c, _ in self.lines]})
        self.lines = []
        self.entry_desc = ""
        if not self.keeps_school_after_save:
            self.school = CONTADO
        if self._fault("av_on_save_saved", code):
            self.label_stale = True
            self._open_av()
            return
        self.label_stale = False
        self._open("preview", "Preview - [No name]",
                   f"CONDUCE NO: {conduce}\nCODIGO: {code}")

    def _do_print(self, handle: int) -> None:
        if not self._of_kind("preview"):
            self.print_without_preview += 1
        self._close(handle)
        self.printed.append(self.saved[-1]["conduce"] if self.saved else "?")

    # Ayudas para pruebas
    def saved_count(self, school_code: str) -> int:
        return sum(1 for s in self.saved if s["escuela"] == school_code)
