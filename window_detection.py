"""Acceso a las ventanas de SisFaCon Express.

``SisFaConDriver`` define las operaciones de bajo nivel que necesita el
motor. Hay dos implementaciones:

* ``RealDriver`` (este archivo): controla SisFaCon en Windows. Usa primero
  los controles de Windows (pywinauto, backend win32, adecuado para
  aplicaciones Delphi como SisFaCon) y, cuando un dato no está expuesto
  como control (por ejemplo rótulos o celdas de la tabla), recurre a OCR
  sobre una región calibrada.
* ``SimulatedDriver`` (simulator.py): imita SisFaCon en memoria.

Ninguna coordenada está escrita en el código: todas salen de la calibración
y son relativas a la esquina de la ventana correspondiente.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


class DriverError(RuntimeError):
    """Error de comunicación con SisFaCon (mensaje para el usuario)."""


class CalibrationError(DriverError):
    pass


class EmergencyStop(RuntimeError):
    """El usuario llevó el ratón a la esquina superior izquierda."""


@dataclass
class WinInfo:
    handle: int
    title: str
    class_name: str = ""
    text: str = ""          # texto de los controles hijos (o OCR)
    buttons: list[str] = field(default_factory=list)

    def describe(self) -> str:
        body = self.text.strip().replace("\n", " ")
        return f"«{self.title}» [{self.class_name}] {body[:300]}"


class SisFaConDriver:
    """Interfaz común. Los métodos lanzan DriverError ante fallos."""

    simulated = False

    def find_main(self) -> bool: ...
    def focus_main(self) -> None: ...
    def capture_baseline(self) -> list[WinInfo]: ...
    def list_windows(self) -> list[WinInfo]: ...
    def window_exists(self, handle: int) -> bool: ...
    def focus_window(self, handle: int) -> None: ...
    def send_keys(self, keys: str, handle: int | None = None) -> None: ...
    def press_ok(self, win: WinInfo) -> None: ...
    def type_search_text(self, search_handle: int, text: str) -> None: ...
    def read_field(self, name: str) -> str | None: ...
    def is_calibrated(self, name: str) -> bool: ...
    def click_point(self, name: str) -> None: ...
    def type_text(self, text: str) -> None: ...
    def screenshot(self, path: Path) -> bool: return False
    def emergency_requested(self) -> bool: return False
    def click_button(self, text: str) -> bool: return False
    def input_hint(self) -> str: return ""


def escape_keys(text: str) -> str:
    """Escapa texto literal para pywinauto.keyboard.send_keys."""
    out = []
    for c in text:
        out.append("{%s}" % c if c in "{}+^%~()[]" else c)
    return "".join(out)


DIALOG_CLASSES = ("#32770", "TMessageForm")


def find_window_rect(title_part: str):
    """(izq, arriba, der, abajo) en píxeles reales de la primera ventana visible
    cuyo título contiene ``title_part``; None si no hay (o no es Windows)."""
    if not sys.platform.startswith("win") or not title_part:
        return None
    try:
        import win32gui
    except ImportError:
        return None
    found = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd) \
                and title_part.lower() in win32gui.GetWindowText(hwnd).lower():
            found.append(win32gui.GetWindowRect(hwnd))
            return False
        return True

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:  # EnumWindows lanza al detenerse desde el callback
        pass
    return found[0] if found else None


def self_is_admin() -> bool | None:
    """¿El AutoFacturador se está ejecutando como administrador?"""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return None


def process_is_elevated(pid: int) -> bool | None:
    """¿El proceso indicado se ejecuta como administrador? None = no se pudo saber
    (lo normal cuando el proceso es de administrador y nosotros no)."""
    if not sys.platform.startswith("win") or not pid:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k32, adv = ctypes.windll.kernel32, ctypes.windll.advapi32
        h = k32.OpenProcess(0x1000, False, int(pid))      # QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            token = wintypes.HANDLE()
            if not adv.OpenProcessToken(h, 0x0008, ctypes.byref(token)):   # TOKEN_QUERY
                return None
            try:
                elevated, size = wintypes.DWORD(), wintypes.DWORD()
                if not adv.GetTokenInformation(token, 20, ctypes.byref(elevated), 4,
                                               ctypes.byref(size)):           # TokenElevation
                    return None
                return bool(elevated.value)
            finally:
                k32.CloseHandle(token)
        finally:
            k32.CloseHandle(h)
    except Exception:
        return None


def calibrated_screen_rects(settings, main_rect) -> list[tuple[int, int, int, int]]:
    """Zonas de la ventana principal de SisFaCon que el macro lee o pulsa."""
    if not main_rect:
        return []
    left, top = main_rect[0], main_rect[1]
    out = []
    for entry in (settings["calibracion"] or {}).values():
        if entry.get("ventana") != "principal":
            continue
        x, y = left + entry["x"], top + entry["y"]
        out.append((x - 10, y - 10, x + entry.get("w", 1) + 10, y + entry.get("h", 1) + 10))
    return out


def _ocr_accept():
    """Criterios para dar por buena una lectura OCR sin probar más variantes."""
    import re
    from verification import parse_conduce, parse_line_count
    return {
        "contador_lineas": lambda t: parse_line_count(t) is not None,
        "ultimo_conduce": lambda t: bool(parse_conduce(t)),
        "codigo_centro": lambda t: bool(re.search(r"\d{4,}|PERSONAL", t.upper())),
        "nombre_centro": lambda t: len(t.strip()) >= 4,
        "descripcion_producto": lambda t: len(t.strip()) >= 3,
    }


_OCR_ACCEPT = _ocr_accept()


class RealDriver(SisFaConDriver):
    """Controla la aplicación real. Solo funciona en Windows."""

    def __init__(self, settings, ocr=None):
        if not sys.platform.startswith("win"):
            raise DriverError("El modo real solo funciona en Windows 10/11.")
        try:
            from pywinauto import Desktop, keyboard, mouse  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise DriverError("Falta pywinauto. Ejecute instalar.bat.") from exc
        self.settings = settings
        self._desktop = Desktop(backend="win32")
        self._main = None
        self._pid = None
        self._baseline: set[tuple[str, str]] = set()
        if ocr is None:
            from ocr import OcrEngine
            ocr = OcrEngine(settings)
        self.ocr = ocr
        try:
            import pyautogui
            pyautogui.FAILSAFE = True  # esquina superior izquierda = abortar
            self._pyautogui = pyautogui
        except Exception:  # pragma: no cover
            self._pyautogui = None

    # ------------------------------------------------------------ ventanas
    def _all_top(self):
        return self._desktop.windows(visible_only=True)

    def find_main(self) -> bool:
        wanted = self.settings["titulo_ventana_principal"].lower()
        for w in self._all_top():
            try:
                if wanted in w.window_text().lower():
                    self._main = w
                    self._pid = w.process_id()
                    return True
            except Exception:
                continue
        self._main = None
        return False

    def _require_main(self):
        if self._main is None or not self.window_exists(self._main.handle):
            if not self.find_main():
                raise DriverError("No se encuentra la ventana principal de SisFaCon "
                                  f"(«{self.settings['titulo_ventana_principal']}»).")
        return self._main

    def focus_main(self) -> None:
        self.focus_window(self._require_main().handle)

    def focus_window(self, handle: int) -> None:
        self._check_emergency()
        import win32gui
        w = self._desktop.window(handle=handle)
        last_error = None
        for _ in range(4):
            try:
                if w.is_minimized():
                    w.restore()
                w.set_focus()
            except Exception as exc:  # p. ej. la ventana se está redibujando
                last_error = exc
            time.sleep(0.2)
            if win32gui.GetForegroundWindow() == handle:
                return
            time.sleep(0.3)
        raise DriverError("Windows no permitió poner SisFaCon en primer plano"
                          + (f": {last_error}" if last_error else "."))

    def window_exists(self, handle: int) -> bool:
        import win32gui
        return bool(win32gui.IsWindow(handle) and win32gui.IsWindowVisible(handle))

    def _process_windows(self):
        self._require_main()
        out = []
        for w in self._desktop.windows(process=self._pid, visible_only=True):
            if w.handle != self._main.handle:
                out.append(w)
        return out

    def _info(self, w) -> WinInfo:
        title = w.window_text()
        cls = w.class_name()
        texts, buttons = [], []
        try:
            for c in w.children():
                t = c.window_text().strip()
                if not t:
                    continue
                if c.class_name().lower().endswith("button") or c.class_name() == "Button":
                    buttons.append(t)
                else:
                    texts.append(t)
        except Exception:
            pass
        text = "\n".join(texts)
        if not text and cls in DIALOG_CLASSES:
            # Mensaje no expuesto como control: OCR de la ventana completa.
            r = w.rectangle()
            text = self.ocr.read_rect((r.left, r.top, r.width(), r.height())) or ""
        return WinInfo(handle=w.handle, title=title, class_name=cls,
                       text=text, buttons=buttons)

    def capture_baseline(self) -> list[WinInfo]:
        """Ventanas «de fondo» de SisFaCon (p. ej. Menú Principal).

        Solo se aceptan como fondo ventanas que no parecen diálogos.
        Devuelve las que SÍ parecen diálogos para que el motor las trate.
        """
        pending = []
        self._baseline = set()
        for w in self._process_windows():
            try:
                info = self._info(w)
            except Exception:
                continue  # la ventana se cerró mientras se leía
            if info.class_name in DIALOG_CLASSES or self._is_transient_title(info.title):
                pending.append(info)
            else:
                self._baseline.add((info.title, info.class_name))
        return pending

    def _is_transient_title(self, title: str) -> bool:
        t = title.lower()
        s = self.settings
        names = [s["titulo_busqueda_cliente"], s["titulo_vista_previa"],
                 *s["titulos_dialogo_impresion"]]
        return any(n and n.lower() in t for n in names)

    def list_windows(self) -> list[WinInfo]:
        out = []
        for w in self._process_windows():
            try:
                key = (w.window_text(), w.class_name())
                if key in self._baseline:
                    continue
                out.append(self._info(w))
            except Exception:
                continue
        return out

    # -------------------------------------------------------------- teclado
    def send_keys(self, keys: str, handle: int | None = None) -> None:
        from pywinauto import keyboard
        self._check_emergency()
        self.focus_window(handle or self._require_main().handle)
        keyboard.send_keys(keys, pause=0.03, with_spaces=True)

    def type_text(self, text: str) -> None:
        from pywinauto import keyboard
        self._check_emergency()
        keyboard.send_keys(escape_keys(text), pause=0.03, with_spaces=True)

    def press_ok(self, win: WinInfo) -> None:
        """Pulsa OK/Aceptar SOLO en la ventana indicada."""
        self._check_emergency()
        w = self._desktop.window(handle=win.handle)
        for c in w.children():
            t = c.window_text().replace("&", "").strip().lower()
            if t in ("ok", "aceptar") and c.class_name().lower().endswith("button"):
                c.click()
                return
        # Sin botón accesible: Enter con la ventana en primer plano.
        self.send_keys("{ENTER}", handle=win.handle)

    def type_search_text(self, search_handle: int, text: str) -> None:
        from pywinauto import keyboard
        w = self._desktop.window(handle=search_handle)
        edits = []
        for c in w.descendants():
            try:
                if "edit" in c.class_name().lower() and c.is_visible():
                    edits.append(c)
            except Exception:
                continue
        if edits:
            edit = min(edits, key=lambda c: c.rectangle().top)
            self.focus_window(search_handle)
            edit.set_focus()
            keyboard.send_keys("{END}+{HOME}{DEL}" + escape_keys(text),
                               pause=0.03, with_spaces=True)
            time.sleep(0.2)
            got = edit.window_text().strip()
            if got and got.upper() != text.strip().upper():
                raise DriverError(f"El campo «Texto búsqueda» contiene «{got}» "
                                  f"en lugar de «{text}».")
            return
        if self.is_calibrated("texto_busqueda"):
            self.focus_window(search_handle)
            self.click_point("texto_busqueda", window_handle=search_handle)
            keyboard.send_keys("{END}+{HOME}{DEL}" + escape_keys(text),
                               pause=0.03, with_spaces=True)
            return
        raise CalibrationError("No se detectó el campo «Texto búsqueda». "
                               "Calíbrelo en Configuración > Calibración.")

    # ------------------------------------------------------ calibración
    def is_calibrated(self, name: str) -> bool:
        return name in (self.settings["calibracion"] or {})

    def _window_for(self, entry: dict, window_handle: int | None = None):
        if window_handle:
            return self._desktop.window(handle=window_handle)
        if entry.get("ventana") == "busqueda":
            title = self.settings["titulo_busqueda_cliente"]
            for w in self._process_windows():
                if title.lower() in w.window_text().lower():
                    return w
            raise DriverError("La ventana «Seleccione un Cliente» no está abierta.")
        return self._require_main()

    def absolute_rect(self, name: str, window_handle: int | None = None):
        entry = (self.settings["calibracion"] or {}).get(name)
        if not entry:
            raise CalibrationError(f"Falta calibrar «{name}».")
        w = self._window_for(entry, window_handle)
        r = w.rectangle()
        cw, ch = entry.get("ancho_ventana"), entry.get("alto_ventana")
        if cw and ch and (abs(r.width() - cw) > 12 or abs(r.height() - ch) > 12):
            raise CalibrationError(
                f"La ventana mide {r.width()}x{r.height()} pero se calibró a {cw}x{ch}. "
                "Restaure el tamaño (o maximícela igual que al calibrar) o vuelva a calibrar.")
        return (r.left + entry["x"], r.top + entry["y"],
                max(1, entry.get("w", 1)), max(1, entry.get("h", 1)))

    def click_point(self, name: str, window_handle: int | None = None) -> None:
        from pywinauto import mouse
        self._check_emergency()
        x, y, w, h = self.absolute_rect(name, window_handle)
        mouse.click(coords=(x + w // 2, y + h // 2))
        time.sleep(0.15)

    def read_field(self, name: str) -> str | None:
        entry = (self.settings["calibracion"] or {}).get(name)
        if not entry:
            return None
        x, y, w, h = self.absolute_rect(name)
        method = entry.get("metodo", "auto")
        if method in ("auto", "control"):
            text = self._control_text_at(x, y, w, h)
            if text or method == "control":
                return text
        return self.ocr.read_rect((x, y, w, h), digits=name == "codigo_centro",
                                  variants=True, accept=_OCR_ACCEPT.get(name))

    def _control_text_at(self, x, y, w, h) -> str | None:
        """Texto del control de Windows situado bajo la región.

        Recorre TODOS los controles hijos de SisFaCon (también los bloqueados o
        de solo lectura, que Windows ignora al preguntar «qué hay en este
        punto») y lee el más pequeño que contiene el centro de la región.
        """
        import win32gui
        cx, cy = x + w // 2, y + h // 2
        parents = []
        try:
            if self._main is not None or self.find_main():
                parents.append(self._main.handle)
                for win in self._process_windows():   # p. ej. «Seleccione un Cliente»
                    parents.append(win.handle)
        except Exception:
            pass
        limit = max(4 * w * h, w * h + 20000)
        found = []

        def collect(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                if left <= cx < right and top <= cy < bottom:
                    area = (right - left) * (bottom - top)
                    if area <= limit:
                        found.append((area, hwnd))
            except Exception:
                pass
            return True

        for parent in parents:
            try:
                win32gui.EnumChildWindows(parent, collect, None)
            except Exception:
                continue
        for _area, hwnd in sorted(found):
            try:
                text = self._desktop.window(handle=hwnd).window_text().strip()
            except Exception:
                continue
            if text:
                return text
        return None

    # -------------------------------------------------------------- otros
    def screenshot(self, path: Path) -> bool:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True)
            img.save(path)
            return True
        except Exception:
            return False

    def click_button(self, text: str) -> bool:
        """Pulsa un botón de la ventana principal por su texto (BM_CLICK).
        Devuelve False si no existe como control de Windows."""
        if not text:
            return False
        import win32con
        import win32gui
        self._check_emergency()
        main = self._require_main()
        wanted = text.replace("&", "").strip().lower()
        found = []

        def cb(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                    label = self._desktop.window(handle=hwnd).window_text()
                    if wanted in label.replace("&", "").strip().lower():
                        found.append(hwnd)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumChildWindows(main.handle, cb, None)
        except Exception:
            return False
        if not found:
            return False
        self.focus_window(main.handle)
        win32gui.PostMessage(found[0], win32con.BM_CLICK, 0, 0)
        return True

    def input_hint(self) -> str:
        """Explicación probable cuando SisFaCon no reacciona a las teclas."""
        me = self_is_admin()
        other = process_is_elevated(self._pid) if self._pid else None
        if me is False and other is not False:
            return ("SisFaCon parece ejecutarse como ADMINISTRADOR y el AutoFacturador no: Windows "
                    "bloquea las teclas. Abra el AutoFacturador con clic derecho → «Ejecutar como "
                    "administrador».")
        return ("Compruebe que no haya otra ventana encima de SisFaCon y que F7 abra la búsqueda "
                "cuando lo pulsa usted. Use Configuración → «Probar F7».")

    def emergency_requested(self) -> bool:
        try:
            import win32api
            x, y = win32api.GetCursorPos()
            return x <= 2 and y <= 2
        except Exception:
            return False

    def _check_emergency(self) -> None:
        if self.emergency_requested():
            raise EmergencyStop("Parada de emergencia: ratón en la esquina superior izquierda.")

    # Utilidad para la calibración
    def window_rect(self, which: str):
        if which == "busqueda":
            w = self._window_for({"ventana": "busqueda"})
        else:
            w = self._require_main()
        r = w.rectangle()
        return r.left, r.top, r.width(), r.height()
