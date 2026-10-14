"""Motor de facturación: recorre las escuelas de una jornada con una máquina
de estados explícita y verifica cada paso antes de continuar.

Flujo por escuela (confirmado en SisFaCon Express):
  1. VALIDATING        SisFaCon abierto, sin ventanas pendientes, formulario vacío.
  2. SELECTING_SCHOOL  F7 -> «Seleccione un Cliente» -> Texto búsqueda -> Enter.
  3. VERIFYING_SCHOOL  El campo CODIGO muestra el código esperado.
  4. ENTERING_PRODUCT  Clic en la celda Código -> código -> Enter.
  5. VERIFYING_PRODUCT 1 línea y descripción esperada.
  6. SAVING_INVOICE    Ctrl+G (se registra ANTES de pulsarlo).
  7. VERIFYING_SAVE    Aparece «Preview - [No name]» = conduce grabado.
  8. PRINTING          F9 en la vista previa -> diálogo «Print» -> OK.
  9. VERIFYING_PRINT   El diálogo se cierra sin errores -> Esc cierra la vista previa.

Reglas de seguridad:
  * Nunca se vuelve a pulsar Ctrl+G para una factura cuyo guardado es incierto.
  * Solo se pulsa OK en la violación de acceso reconocida o en mensajes que
    el usuario declaró inofensivos. Ante cualquier otra ventana: parada.
  * La impresión solo ocurre si la vista previa (prueba de guardado) está abierta.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from database import now_iso
from day_manager import DayManager, DayStatus, InvoiceStatus, Mode, PrintStatus
from error_recovery import Classified, RecoveryPolicy, WinKind, classify_window
from logging_manager import OperationLogger
from state_machine import STATE_LABELS, State, StateMachine
from verification import (best_match, codes_match, normalize_text, parse_conduce,
                          parse_line_count, parse_quantity, text_matches)
from window_detection import (CalibrationError, DriverError, EmergencyStop,
                              SisFaConDriver, WinInfo)


# --------------------------------------------------------------- excepciones
class StopRequested(Exception):
    pass


class AccessViolationDetected(Exception):
    def __init__(self, win: WinInfo):
        super().__init__(win.describe())
        self.win = win


class UnknownWindowDetected(Exception):
    def __init__(self, win: WinInfo):
        super().__init__(win.describe())
        self.win = win


class FlowAbort(Exception):
    """Detiene la jornada dejando la factura en un estado concreto."""

    def __init__(self, message: str, status: str | None = None,
                 print_status: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.print_status = print_status


class Timeout(Exception):
    pass


# ------------------------------------------------------------ comunicación UI
class EngineUI:
    """Puente con la interfaz. La implementación por defecto no pregunta nada
    y elige la opción más conservadora (la última: «Detener»)."""

    def ask(self, title: str, message: str, options: list[str]) -> str:
        return options[-1]

    def notify(self, level: str, title: str, message: str) -> None:
        pass

    def on_state(self, state: State, label: str) -> None:
        pass

    def on_invoice(self, invoice: dict) -> None:
        pass


@dataclass
class RunOptions:
    mode: str = Mode.SIMULADO
    invoice_ids: list[int] | None = None   # None = todas las pendientes
    limit: int | None = None               # grupo de prueba: primeras N
    confirm_each: bool = False


@dataclass
class InvoiceContext:
    inv: dict
    save_attempted: bool = False
    preview_seen: bool = False
    preview_handle: int | None = None
    conduce_before: str = ""
    print_confirmed: bool = False
    print_question_seen: bool = False   # SisFaCon preguntó «¿imprimir?» tras Ctrl+G
    recovering: bool = False
    product_typed: bool = False   # ya se escribió el código del producto alguna vez
    desc_seen: bool = False       # la descripción correcta apareció tras escribir el código
    attempts: int = 0
    notes: list[str] = field(default_factory=list)


# ======================================================================
class AutomationEngine:
    def __init__(self, driver: SisFaConDriver, days: DayManager,
                 logger: OperationLogger, settings, ui: EngineUI | None = None,
                 capture_dir: str | Path | None = None):
        self.driver = driver
        self.days = days
        self.log = logger
        self.settings = settings
        self.ui = ui or EngineUI()
        self.capture_dir = Path(capture_dir) if capture_dir else None
        self.sm = StateMachine(on_change=self._on_state_change)
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._running = False
        self._day: dict | None = None
        self._mode = Mode.SIMULADO
        self.last_summary = ""

    # ------------------------------------------------------------ control
    @property
    def running(self) -> bool:
        return self._running

    @property
    def paused(self) -> bool:
        return not self._resume.is_set()

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def stop(self) -> None:
        """Evita nuevas operaciones. La factura en curso se detiene en el
        siguiente punto seguro (nunca entre Ctrl+G y la impresión)."""
        self._stop.set()
        self._resume.set()

    def _on_state_change(self, old: State, new: State, reason: str) -> None:
        self.ui.on_state(new, STATE_LABELS[new] + (f" — {reason}" if reason else ""))

    def _goto(self, state: State, reason: str = "") -> None:
        self.sm.transition(state, reason)

    def _checkpoint(self, ctx: InvoiceContext | None = None) -> None:
        """Punto seguro: aquí se atienden pausa y parada."""
        if self._stop.is_set():
            raise StopRequested()
        if not self._resume.is_set():
            self.sm.pause("Pausa solicitada")
            self.log.log("JORNADA_PAUSADA", jornada=self._day,
                         factura=ctx.inv if ctx else None)
            if self._day:
                self.days.set_day_status(self._day["id"], DayStatus.PAUSADA)
            self._resume.wait()
            if self._stop.is_set():
                self.sm.resume("Reanudado para detener")
                raise StopRequested()
            self.sm.resume()
            self.log.log("JORNADA_REANUDADA", jornada=self._day)
            if self._day:
                self.days.set_day_status(self._day["id"], DayStatus.EN_CURSO)

    # =============================================================== RUN
    def run(self, day_id: int, options: RunOptions) -> str:
        if self._running:
            raise RuntimeError("La automatización ya está en marcha.")
        day = self.days.get_day(day_id)
        if not day:
            raise ValueError("Jornada inexistente.")
        if options.mode == Mode.AUTOMATICO and not self.driver.simulated \
                and not self.settings["prueba_superada"]:
            raise FlowAbort("El modo automático está bloqueado hasta completar "
                            "con éxito una factura en el modo de prueba.")
        if options.mode != Mode.SIMULADO and self.driver.simulated:
            raise FlowAbort("Los modos de prueba y automático requieren SisFaCon real.")
        self._day, self._mode = day, options.mode
        self._stop.clear()
        self._resume.set()
        self._running = True
        self._counter_warned = False
        self._conduce_warned = False
        self.sm.reset()
        completed = halted = 0
        reason = ""
        try:
            self._preflight()
            filled = self.days.fill_missing_quantities(day_id)
            if filled:
                self.log.log("INFO", f"{filled} factura(s) sin cantidad toman la cantidad actual "
                             "de su escuela.", jornada=day)
            items = self.days.pending_invoices(day_id)
            if options.invoice_ids is not None:
                wanted = set(options.invoice_ids)
                items = [i for i in items if i["id"] in wanted]
            if options.limit:
                items = items[: options.limit]
            self.days.set_day_status(day_id, DayStatus.EN_CURSO)
            self.log.log("JORNADA_INICIADA",
                         f"{Mode.LABELS[options.mode]}: {len(items)} factura(s) a procesar.",
                         jornada=day)
            self._goto(State.VALIDATING, "Inicio")
            for inv in items:
                self._checkpoint()
                current = self.days.invoice(inv["id"])
                if current["estado"] != InvoiceStatus.PENDIENTE:
                    self.log.log("INFO", f"Omitida: ya está en estado {current['estado']}.",
                                 jornada=day, factura=current)
                    continue
                if options.confirm_each or options.mode == Mode.PRUEBA:
                    ans = self.ui.ask(
                        "Siguiente escuela",
                        f"Procesar {current['escuela_codigo']} — {current['escuela_nombre']}\n"
                        f"Producto: {day['producto_nombre']} ({day['producto_codigo']})",
                        ["Continuar", "Omitir", "Detener"])
                    if ans == "Omitir":
                        continue
                    if ans != "Continuar":
                        raise StopRequested()
                if self._process(current, options):
                    completed += 1
                else:
                    halted = 1
                    break
        except StopRequested:
            reason = "Detenido por el usuario."
            self.log.log("JORNADA_DETENIDA", reason, "AVISO", jornada=day)
        except FlowAbort as exc:
            reason = exc.message
            halted = 1
            self._enter_error(reason)
            self.log.log("ERROR", reason, "ERROR", jornada=day)
            self.ui.notify("ERROR", "No se puede iniciar", reason)
        finally:
            self._running = False
            counts = self.days.counts(day_id)
            if counts["pendientes"] == 0 and counts["en_proceso"] == 0 \
                    and counts["revision"] == 0 and counts["errores"] == 0:
                self.days.set_day_status(day_id, DayStatus.COMPLETADA)
                self.log.log("JORNADA_COMPLETADA", jornada=day)
                if self.sm.state in (State.VALIDATING, State.VERIFYING_PRINT):
                    self._goto(State.COMPLETED)
            else:
                self.days.set_day_status(day_id, DayStatus.DETENIDA)
                if not halted and self.sm.state not in (State.ERROR,):
                    if self.sm.state in (State.VALIDATING, State.VERIFYING_PRINT) and not reason:
                        self._goto(State.COMPLETED, "Grupo terminado")
                    elif self.sm.state != State.COMPLETED:
                        self.sm.reset()
        self.last_summary = (f"Facturas completadas en esta ejecución: {completed}. "
                             + (reason or ""))
        return self.last_summary

    def _enter_error(self, reason: str) -> None:
        if self.sm.state == State.PAUSED:
            self.sm.resume()
        if self.sm.state != State.ERROR:
            self._goto(State.ERROR, reason[:120])

    # ------------------------------------------------------------ preflight
    def _preflight(self) -> None:
        s = self.settings
        if not s["verificar_contador_lineas"] and not s["verificar_descripcion_producto"]:
            raise FlowAbort("Active al menos una verificación de producto "
                            "(contador de líneas o descripción).")
        if self.driver.simulated:
            return
        needed = ["codigo_centro", "celda_codigo_producto"]
        if s["verificar_contador_lineas"] and not self._counter_optional():
            needed.append("contador_lineas")
        if s["verificar_descripcion_producto"]:
            needed.append("descripcion_producto")
        if s["verificar_nombre_escuela"]:
            needed.append("nombre_centro")
        missing = [n for n in needed if not self.driver.is_calibrated(n)]
        if missing:
            raise FlowAbort("Falta calibrar: " + ", ".join(missing) +
                            ". Use Configuración > Calibración.")
        if not self.driver.find_main():
            raise FlowAbort("SisFaCon Express no está abierto en la pantalla "
                            "«Registro de Conduce a Centro Educativo».")
        pending = self.driver.capture_baseline()
        for w in pending:
            c = classify_window(w, s)
            if c.kind == WinKind.SEARCH:
                # Una búsqueda que quedó abierta se cierra con Esc (no elige nada).
                self._close_search(w, None)
            elif c.kind != WinKind.ACCESS_VIOLATION:
                raise FlowAbort(f"Cierre primero esta ventana de SisFaCon: {w.describe()}")
        # Una violación de acceso pendiente se atiende en la primera factura.

    # ======================================================== una factura
    def _process(self, inv: dict, options: RunOptions) -> bool:
        ctx = InvoiceContext(inv=inv, attempts=inv["intentos_recuperacion"])
        self._update(ctx, estado=InvoiceStatus.EN_PROCESO, iniciado_en=now_iso(),
                     mensaje="")
        phase = "select"
        try:
            while True:
                try:
                    if phase == "select":
                        if not ctx.recovering:
                            if self.sm.state != State.VALIDATING:
                                self._goto(State.VALIDATING)
                            self._validate_ready(ctx)
                        self._select_school(ctx)
                        self._product(ctx)
                        self._checkpoint(ctx)
                        self._confirm_before_save(ctx)
                        phase = "save"
                    if phase == "save":
                        self._save(ctx)
                        phase = "print"
                    if phase == "print":
                        self._print(ctx)
                        self._finish(ctx)
                        return True
                except AccessViolationDetected as av:
                    pending: AccessViolationDetected | None = av
                    while pending is not None:
                        try:
                            phase = self._recover(ctx, pending.win, phase)
                            pending = None
                        except AccessViolationDetected as again:
                            pending = again  # nuevo error durante la recuperación
        except StopRequested:
            self._abort(ctx, "Detenido por el usuario antes de grabar. El formulario de "
                        "SisFaCon puede tener datos: revíselo o use «Cancelar».",
                        notify=False)
            raise
        except FlowAbort as exc:
            self._abort(ctx, exc.message, exc.status, exc.print_status)
        except UnknownWindowDetected as exc:
            self.log.log("VENTANA_DESCONOCIDA", exc.win.describe(), "ERROR",
                         jornada=self._day, factura=ctx.inv)
            self._abort(ctx, "Apareció una ventana desconocida; no se pulsó nada. "
                        f"Ventana: {exc.win.describe()}")
        except Timeout as exc:
            self._abort(ctx, f"Tiempo de espera agotado: {exc}")
        except EmergencyStop as exc:
            self._abort(ctx, str(exc))
        except (DriverError, CalibrationError) as exc:
            self._abort(ctx, f"Problema al controlar SisFaCon: {exc}")
        except Exception as exc:  # error inesperado: parar sin suponer nada
            self._abort(ctx, f"Error interno inesperado: {exc!r}")
        return False

    # ---------------------------------------------------------- helpers
    def _update(self, ctx: InvoiceContext, **fields) -> None:
        fields.setdefault("etapa", self.sm.state.value)
        ctx.inv = self.days.update_invoice(ctx.inv["id"], **fields)
        self.ui.on_invoice(ctx.inv)

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.driver.emergency_requested():
                raise EmergencyStop("Parada de emergencia: ratón en la esquina superior izquierda.")
            time.sleep(min(0.05, max(0.0, end - time.monotonic())))

    def _poll(self) -> float:
        return 0.01 if self.driver.simulated else float(self.settings["intervalo_sondeo"])

    def _t(self, key: str) -> float:
        return float(self.settings[key])

    def _verify_timeout(self) -> float:
        """Tiempo para que un dato aparezca en pantalla (el OCR puede ser lento)."""
        return max(self._t("espera_estabilizacion") + 2, self._t("timeout_ventana") / 2)

    def _scan(self, ctx: InvoiceContext, allowed: set[WinKind]) -> list[Classified]:
        """Clasifica las ventanas abiertas. Lanza ante errores o desconocidas."""
        found = []
        for w in self.driver.list_windows():
            c = classify_window(w, self.settings)
            if c.kind == WinKind.ACCESS_VIOLATION:
                raise AccessViolationDetected(w)
            if c.kind == WinKind.INFO:
                self.log.log("INFO", f"Mensaje informativo aceptado: {w.describe()}",
                             jornada=self._day, factura=ctx.inv)
                self.driver.press_ok(w)
                continue
            if c.kind == WinKind.UNKNOWN or c.kind not in allowed:
                if c.kind == WinKind.UNKNOWN and self._mode == Mode.PRUEBA \
                        and self._learn_window(w):
                    continue
                raise UnknownWindowDetected(w)
            found.append(c)
        return found

    def _learn_window(self, w: WinInfo) -> bool:
        """En modo de prueba, el usuario puede declarar inofensiva una ventana."""
        ans = self.ui.ask(
            "Ventana desconocida",
            "SisFaCon mostró una ventana que el macro no conoce:\n\n"
            f"{w.describe()}\n\n¿Es un mensaje informativo que se puede aceptar "
            "con OK siempre que aparezca?",
            ["Aceptar y recordar", "Detener"])
        if ans != "Aceptar y recordar":
            return False
        rules = list(self.settings["reglas_dialogos"] or [])
        rules.append({"nombre": w.title or "Mensaje",
                      "titulo_contiene": w.title,
                      "texto_contiene": (w.text or "")[:60],
                      "accion": "OK"})
        self.settings.set("reglas_dialogos", rules)
        self.driver.press_ok(w)
        return True

    def _wait(self, ctx: InvoiceContext, what: str, cond: Callable[[list[Classified]], object],
              allowed: set[WinKind], timeout: float):
        """Espera hasta que ``cond(ventanas)`` devuelva algo verdadero."""
        end = time.monotonic() + timeout
        while True:
            if self.driver.emergency_requested():
                raise EmergencyStop("Parada de emergencia: ratón en la esquina superior izquierda.")
            wins = self._scan(ctx, allowed)
            result = cond(wins)
            if result:
                return result
            if time.monotonic() >= end:
                raise Timeout(what)
            time.sleep(self._poll())

    @staticmethod
    def _first(kind: WinKind):
        return lambda wins: next((c for c in wins if c.kind == kind), None)

    @staticmethod
    def _none_of(kind: WinKind):
        return lambda wins: all(c.kind != kind for c in wins)

    def _read(self, name: str) -> str | None:
        return self.driver.read_field(name)

    def _read_lines(self) -> int | None:
        # Si ya se comprobó en esta ejecución que es ilegible, no se pierde tiempo en OCR.
        if getattr(self, "_counter_warned", False) and self._counter_optional():
            self._last_lines = None
            return None
        self._last_lines = parse_line_count(self._read("contador_lineas"))
        return self._last_lines

    def _counter_optional(self) -> bool:
        """El contador puede omitirse si es ilegible y hay verificación por descripción."""
        s = self.settings
        return bool(s["contador_lineas_opcional"]) and bool(s["verificar_descripcion_producto"])

    def _warn_counter(self, ctx: InvoiceContext) -> None:
        if not getattr(self, "_counter_warned", False):
            self._counter_warned = True
            self.log.log("INFO", "No se puede leer el contador «Linea(s)»: se verifica el producto "
                         "solo por su descripción.", "AVISO", jornada=self._day, factura=ctx.inv)

    def _poll_until(self, ctx, what: str, check: Callable[[], bool], timeout: float,
                    allowed: set[WinKind] = frozenset()) -> bool:
        end = time.monotonic() + timeout
        while True:
            self._scan(ctx, set(allowed))
            if check():
                return True
            if time.monotonic() >= end:
                return False
            self._sleep(self._poll())

    def _uncertain_status(self, ctx: InvoiceContext) -> tuple[str, str]:
        """Estado más prudente según lo que se sabe de la factura."""
        if ctx.preview_seen:
            return InvoiceStatus.GUARDADA, (PrintStatus.PENDIENTE_VERIFICACION
                                            if ctx.print_confirmed else PrintStatus.PENDIENTE)
        if ctx.save_attempted:
            return InvoiceStatus.REVISION, PrintStatus.PENDIENTE
        return InvoiceStatus.ERROR, PrintStatus.PENDIENTE

    def _abort(self, ctx: InvoiceContext, message: str, status: str | None = None,
               print_status: str | None = None, notify: bool = True) -> None:
        st, pst = self._uncertain_status(ctx)
        status = status or st
        print_status = print_status or pst
        shot = self._screenshot(ctx)
        if shot:
            message += f" (captura: {shot})"
        self._update(ctx, estado=status, estado_impresion=print_status, mensaje=message)
        tipo = "REVISION" if status in (InvoiceStatus.REVISION, InvoiceStatus.GUARDADA) else "ERROR"
        self.log.log(tipo, message, "ERROR", jornada=self._day, factura=ctx.inv, estado=status)
        if self._stop.is_set() and not notify:
            self.sm.reset()
            return
        self._enter_error(message)
        if notify:
            saved_txt = {
                InvoiceStatus.GUARDADA: "GRABADA (la impresión debe revisarse)",
                InvoiceStatus.REVISION: "ESTADO INCIERTO: compruebe en SisFaCon si el conduce existe",
                InvoiceStatus.ERROR: "NO grabada",
                InvoiceStatus.PENDIENTE: "sin cambios",
            }.get(status, status)
            self.ui.notify("ERROR", "Automatización detenida",
                           f"Escuela: {ctx.inv['escuela_codigo']} — {ctx.inv['escuela_nombre']}\n"
                           f"Factura: {saved_txt}\n\n{message}\n\n"
                           "Revise SisFaCon antes de continuar.")

    def _screenshot(self, ctx: InvoiceContext) -> str:
        if not self.capture_dir or not self.settings["capturas_en_error"]:
            return ""
        name = f"{datetime.now():%Y%m%d_%H%M%S}_{ctx.inv['escuela_codigo']}.png"
        path = self.capture_dir / name
        return str(path) if self.driver.screenshot(path) else ""

    # ======================================================== pasos
    def _validate_ready(self, ctx: InvoiceContext) -> None:
        if not self.driver.find_main():
            raise FlowAbort("SisFaCon Express no está abierto.", InvoiceStatus.PENDIENTE)
        try:
            for c in self._scan(ctx, {WinKind.SEARCH}):
                self._close_search(c.win, ctx)
        except UnknownWindowDetected as exc:
            raise FlowAbort(f"Hay una ventana abierta en SisFaCon: {exc.win.describe()}",
                            InvoiceStatus.PENDIENTE)
        if self.settings["verificar_contador_lineas"]:
            n = self._read_lines()
            if n is None and self._counter_optional():
                self._warn_counter(ctx)
                self._require_new_form(ctx)
            elif n is None:
                raise FlowAbort("No se pudo leer el contador «Linea(s)». Revise la calibración "
                                "o la instalación de Tesseract.", InvoiceStatus.PENDIENTE)
            elif n != 0:
                raise FlowAbort(f"El formulario tiene {n} línea(s): no es una factura nueva. "
                                "Cancele o limpie el formulario en SisFaCon.",
                                InvoiceStatus.PENDIENTE)
        self.driver.focus_main()

    def _require_new_form(self, ctx: InvoiceContext) -> None:
        """Sin contador legible, se exige un formulario nuevo (cliente por defecto)
        para no añadir el producto a un conduce que ya tiene líneas."""
        expected = (self.settings["codigo_formulario_nuevo"] or "").strip()
        if not expected:
            return
        read = self._read("codigo_centro")
        if read is not None and read.strip() and not codes_match(expected, read):
            raise FlowAbort(f"El formulario de SisFaCon no es nuevo: muestra «{read.strip()}» en "
                            f"CODIGO y se esperaba «{expected}». Pulse «Nuevo» o «Cancelar» en "
                            "SisFaCon y vuelva a iniciar. (Si SisFaCon deja siempre la última "
                            "escuela tras grabar, vacíe «Código de un formulario nuevo» en "
                            "Configuración).", InvoiceStatus.PENDIENTE)

    def _select_school(self, ctx: InvoiceContext) -> None:
        """F7 -> búsqueda -> Enter -> verificar el código mostrado.

        Si la búsqueda no encuentra la escuela o selecciona otra, se reintenta
        UNA vez buscando por el otro dato (nombre/código). Es seguro porque en
        este punto el formulario todavía no tiene el producto.
        """
        inv = ctx.inv
        by_code = self.settings["buscar_escuela_por"] == "codigo"
        texts = [inv["escuela_codigo"] if by_code else inv["escuela_nombre"]]
        if self.settings["reintentar_busqueda_alternativa"]:
            texts.append(inv["escuela_nombre"] if by_code else inv["escuela_codigo"])
        problem = ""
        for attempt, text in enumerate(texts):
            if attempt:
                self.log.log("INFO", f"{problem} Se reintenta buscando «{text}».", "AVISO",
                             jornada=self._day, factura=inv)
                self._goto(State.RECOVERING, "Reintento de búsqueda")
            found, read = self._search_school(ctx, text)
            if found and codes_match(inv["escuela_codigo"], read):
                break
            problem = (f"«{text}» no aparece en «Seleccione un Cliente»." if not found else
                       f"Se esperaba {inv['escuela_codigo']} y SisFaCon muestra «{read or 'nada legible'}».")
        else:
            self.log.log("ESCUELA_INCORRECTA", problem, "ERROR", jornada=self._day, factura=inv)
            raise FlowAbort(f"Escuela no seleccionada: {problem} No se grabó nada.",
                            InvoiceStatus.ERROR)
        if self.settings["verificar_nombre_escuela"]:
            name = self._read("nombre_centro")
            if not text_matches(inv["escuela_nombre"], name,
                                float(self.settings["umbral_similitud_nombre"])):
                raise FlowAbort(f"El nombre mostrado «{name}» no coincide con "
                                f"«{inv['escuela_nombre']}».", InvoiceStatus.ERROR)
        self.log.log("ESCUELA_SELECCIONADA", jornada=self._day, factura=inv)

    def _close_search(self, win: WinInfo, ctx: InvoiceContext | None) -> None:
        """Cierra con Esc una «Seleccione un Cliente» abierta (no selecciona nada)."""
        self.log.log("INFO", "Había una «Seleccione un Cliente» abierta: se cierra con Esc.",
                     jornada=self._day, factura=ctx.inv if ctx else None)
        self.driver.send_keys("{ESC}", win.handle)
        end = time.monotonic() + self._t("timeout_ventana")
        while self.driver.window_exists(win.handle):
            if time.monotonic() > end:
                raise FlowAbort("No se pudo cerrar la ventana «Seleccione un Cliente» que estaba "
                                "abierta. Ciérrela a mano.", InvoiceStatus.PENDIENTE)
            self._sleep(self._poll())

    def _open_search(self, ctx: InvoiceContext) -> Classified:
        """F7 y, si SisFaCon no responde, botón «Buscar Centro» o un segundo F7."""
        total = self._t("timeout_ventana")
        first = min(total, 4.0)
        self.driver.send_keys(self.settings["tecla_buscar_cliente"])
        try:
            return self._wait(ctx, "abrir «Seleccione un Cliente»", self._first(WinKind.SEARCH),
                              {WinKind.SEARCH}, first)
        except Timeout:
            pass
        if self.driver.click_button(self.settings["boton_buscar_cliente"]):
            how = "el botón «Buscar Centro»"
        else:
            self.driver.send_keys(self.settings["tecla_buscar_cliente"])
            how = "un segundo F7"
        self.log.log("INFO", f"F7 no abrió la búsqueda; se reintenta con {how}.", "AVISO",
                     jornada=self._day, factura=ctx.inv)
        try:
            return self._wait(ctx, "abrir «Seleccione un Cliente»", self._first(WinKind.SEARCH),
                              {WinKind.SEARCH}, max(total - first, 4.0))
        except Timeout:
            raise FlowAbort("SisFaCon no abrió «Seleccione un Cliente» con F7 ni con " + how + ". "
                            + self.driver.input_hint() + " No se grabó nada.",
                            InvoiceStatus.ERROR)

    def _search_school(self, ctx: InvoiceContext, text: str) -> tuple[bool, str | None]:
        """Un intento de búsqueda. Devuelve (se cerró la búsqueda, código leído)."""
        self._goto(State.SELECTING_SCHOOL, text)
        self._update(ctx)
        search = self._open_search(ctx)
        self.driver.type_search_text(search.win.handle, text)
        self._sleep(self._t("espera_tras_tecla"))
        self._scan(ctx, {WinKind.SEARCH})
        self.driver.send_keys(self.settings["tecla_confirmar_busqueda"], search.win.handle)
        try:
            self._wait(ctx, "cerrar «Seleccione un Cliente»", self._none_of(WinKind.SEARCH),
                       {WinKind.SEARCH}, self._t("timeout_ventana"))
        except Timeout:
            # Sin resultados: la ventana sigue abierta. Esc la cierra sin elegir nada.
            if self.driver.window_exists(search.win.handle):
                self.driver.send_keys("{ESC}", search.win.handle)
            self._wait(ctx, "cerrar la búsqueda con Esc", self._none_of(WinKind.SEARCH),
                       {WinKind.SEARCH}, self._t("timeout_ventana"))
            self._goto(State.VERIFYING_SCHOOL, "Sin resultados")
            return False, None
        self._goto(State.VERIFYING_SCHOOL)
        self._update(ctx)
        last = {"code": None}

        def ok() -> bool:
            last["code"] = self._read("codigo_centro")
            return codes_match(ctx.inv["escuela_codigo"], last["code"])

        self._poll_until(ctx, "verificar escuela", ok, self._verify_timeout())
        return True, last["code"]

    def _desc_matches(self, desc: str | None) -> bool:
        """¿Lo leído es el producto de la jornada (y no otro parecido del catálogo)?
        Ej.: con «Pan» y «Pan de zanahoria», «PAN DE ZANAHORIA» solo vale para el segundo."""
        day = self._day
        expected = day["producto_texto_verificacion"] or day["producto_nombre"]
        if not text_matches(expected, desc, float(self.settings["umbral_similitud_producto"])):
            return False
        others = [p.get("texto_verificacion") or p.get("nombre") or ""
                  for p in self.products_catalog()]
        best = best_match(desc, [expected] + others)
        return best is None or normalize_text(best) == normalize_text(expected)

    def _product_ok(self, expect_lines: int = 1,
                    ctx: InvoiceContext | None = None) -> tuple[bool, str]:
        """¿Hay exactamente ``expect_lines`` líneas y es el producto esperado?

        La descripción puede estar calibrada sobre la fila azul de entrada, que
        SisFaCon vacía al añadir la línea: si ya se vio la descripción correcta
        tras escribir el código (``ctx.desc_seen``), basta con el contador.
        """
        s = self.settings
        detail = []
        good = True
        if s["verificar_contador_lineas"]:
            n = self._read_lines()
            detail.append(f"líneas={n if n is not None else 'ilegible'}")
            if n is not None or not self._counter_optional():
                good &= n == expect_lines
        if ctx is not None and self.driver.is_calibrated("cantidad_linea"):
            want = int(ctx.inv.get("cantidad") or 0)
            read = self._read("cantidad_linea")
            got = parse_quantity(read)
            detail.append(f"cantidad={got if got is not None else read}")
            good &= got == want
        if s["verificar_descripcion_producto"]:
            desc = self._read("descripcion_producto")
            detail.append(f"descripción=«{desc}»")
            if self._desc_on_entry_row() and ctx is not None and ctx.desc_seen:
                # Ya se vio el producto correcto en la fila azul; al añadir la línea
                # esa fila se vacía: vacía = línea añadida.
                cleared = not self._desc_matches(desc)
                if not cleared:
                    detail.append("la fila de entrada aún tiene el producto")
                good &= cleared
            else:
                good &= self._desc_matches(desc)
        return good, ", ".join(detail)

    def _looks_like_product(self, text: str | None) -> bool:
        """¿El texto leído es la descripción de algún producto del catálogo?
        (El OCR de una celda vacía devuelve ruido como «eC E EE — << A AAA».)"""
        if not text:
            return False
        names = {self._day["producto_texto_verificacion"] or self._day["producto_nombre"]}
        for p in self.products_catalog():
            names.add(p.get("texto_verificacion") or p.get("nombre") or "")
        thr = float(self.settings["umbral_similitud_producto"])
        return any(n and text_matches(n, text, thr) for n in names)

    def products_catalog(self) -> list[dict]:
        try:
            return self.days.db.query("SELECT nombre, texto_verificacion FROM productos "
                                      "WHERE eliminado = 0")
        except Exception:
            return []

    def _desc_on_entry_row(self) -> bool:
        return bool(self.settings["descripcion_en_fila_entrada"])

    def _read_lines_cached(self) -> int | None:
        return getattr(self, "_last_lines", None)

    def _product(self, ctx: InvoiceContext) -> None:
        day = self._day
        if self.settings["verificar_contador_lineas"]:
            n = self._read_lines()
            unsafe = ctx.recovering and ctx.product_typed
            if n is None and (unsafe or not self._counter_optional()):
                raise FlowAbort("No se pudo leer el contador de líneas"
                                + (" tras el error: revise si el formulario ya tiene el producto."
                                   if unsafe else "."), InvoiceStatus.ERROR)
            if n is not None and n > 0:
                ok, detail = self._product_ok(1)
                if ctx.recovering and n == 1 and ok:
                    # Tras la recuperación el producto correcto ya estaba cargado.
                    self._goto(State.VERIFYING_PRODUCT, "Producto ya presente")
                    self.log.log("INFO", f"El producto ya estaba en el formulario ({detail}).",
                                 jornada=day, factura=ctx.inv)
                    return
                raise FlowAbort(f"El formulario tiene líneas inesperadas ({detail}). "
                                "Límpielo en SisFaCon antes de reintentar.", InvoiceStatus.ERROR)
        if int(ctx.inv.get("cantidad") or 0) <= 0:
            raise FlowAbort("Esta escuela no tiene cantidad. Póngala en la pestaña Escuelas "
                            "(o importe el Excel). No se escribió nada.", InvoiceStatus.ERROR)
        self._checkpoint(ctx)
        self._goto(State.ENTERING_PRODUCT, day["producto_codigo"])
        self._update(ctx)
        self.driver.focus_main()
        self.driver.click_point("celda_codigo_producto")
        ctx.product_typed = True
        self.driver.type_text(day["producto_codigo"])
        self.driver.send_keys(self.settings["teclas_tras_codigo_producto"])
        self.log.log("PRODUCTO_INTRODUCIDO", jornada=day, factura=ctx.inv)
        self._goto(State.VERIFYING_PRODUCT)
        self._update(ctx)
        qty = int(ctx.inv.get("cantidad") or 0)
        if self.settings["verificar_descripcion_producto"] and self._desc_on_entry_row():
            # 1) SisFaCon reconoce el código: la descripción aparece en la fila de
            #    entrada y el cursor pasa a Cantidad (con el valor seleccionado).
            seen = {"desc": None}

            def recognised() -> bool:
                seen["desc"] = self._read("descripcion_producto")
                return self._desc_matches(seen["desc"])

            if not self._poll_until(ctx, "reconocer producto", recognised, self._verify_timeout()):
                self.log.log("PRODUCTO_INCORRECTO", f"descripción=«{seen['desc']}»", "ERROR",
                             jornada=day, factura=ctx.inv)
                raise FlowAbort(f"SisFaCon no reconoció el producto {day['producto_codigo']} "
                                f"«{day['producto_nombre']}» (descripción leída: «{seen['desc']}»). "
                                "No se grabó nada.", InvoiceStatus.ERROR)
            ctx.desc_seen = True
        else:
            self._sleep(self._t("espera_estabilizacion"))
        # 2) Cantidad: el valor ya viene seleccionado, se escribe encima y Enter.
        self._scan(ctx, set())
        self.driver.type_text(str(qty))
        self.driver.send_keys(self.settings["teclas_tras_cantidad"])
        self.log.log("INFO", f"Cantidad escrita: {qty}.", jornada=day, factura=ctx.inv)
        info = {"detail": ""}

        def ok() -> bool:
            good, info["detail"] = self._product_ok(1, ctx)
            return good

        if not self._poll_until(ctx, "verificar producto", ok,
                                self._verify_timeout()):
            self.log.log("PRODUCTO_INCORRECTO", info["detail"], "ERROR",
                         jornada=day, factura=ctx.inv)
            raise FlowAbort(f"SisFaCon no reconoció el producto {day['producto_codigo']} "
                            f"«{day['producto_nombre']}» o no coincide ({info['detail']}). "
                            "No se grabó nada.", InvoiceStatus.ERROR)

    def _confirm_before_save(self, ctx: InvoiceContext) -> None:
        if self._mode != Mode.PRUEBA:
            return
        ans = self.ui.ask(
            "Factura de prueba",
            f"Escuela {ctx.inv['escuela_codigo']} y producto {self._day['producto_codigo']} "
            "verificados.\n\n¿Grabar ahora esta factura REAL con Ctrl+G?",
            ["Grabar", "No grabar"])
        if ans != "Grabar":
            raise FlowAbort("Prueba terminada sin grabar (decisión del usuario). El formulario "
                            "de SisFaCon conserva la escuela y el producto: use «Cancelar».",
                            InvoiceStatus.ERROR)

    def _save(self, ctx: InvoiceContext) -> None:
        s, inv = self.settings, ctx.inv
        self._goto(State.SAVING_INVOICE)
        # Última comprobación justo antes de la operación irreversible.
        if not codes_match(inv["escuela_codigo"], self._read("codigo_centro")):
            raise FlowAbort("La escuela cambió antes de grabar.", InvoiceStatus.ERROR)
        good, detail = self._product_ok(1, ctx)
        if not good:
            raise FlowAbort(f"El producto cambió antes de grabar ({detail}).", InvoiceStatus.ERROR)
        if s["exigir_cambio_ultimo_conduce"] and self.driver.is_calibrated("ultimo_conduce"):
            ctx.conduce_before = parse_conduce(self._read("ultimo_conduce"))
            if not ctx.conduce_before and not getattr(self, "_conduce_warned", False):
                # La vista previa sigue siendo la prueba principal de grabación.
                self._conduce_warned = True
                self.log.log("INFO", "No se puede leer «ULTIMAS CONDUCE REGISTRADO»: la grabación "
                             "se confirma solo con la vista previa.", "AVISO",
                             jornada=self._day, factura=ctx.inv)
        # Se registra el intento ANTES de pulsar: si el programa se cierra
        # justo después, la factura quedará como «revisar», nunca se repetirá.
        ctx.save_attempted = True
        self._update(ctx, guardado_intentado=1, conduce_antes=ctx.conduce_before)
        self._scan(ctx, set())
        self.driver.send_keys(s["tecla_grabar"])
        self.log.log("GUARDADO_ENVIADO", jornada=self._day, factura=inv)
        self._goto(State.VERIFYING_SAVE)
        self._update(ctx)
        try:
            answered: set[int] = set()

            def preview_after_question(wins):
                # Ctrl+G → «¿Imprimir?» → Aceptar → vista previa.
                for c in wins:
                    if c.kind == WinKind.PRINT_QUESTION and c.win.handle not in answered:
                        answered.add(c.win.handle)
                        ctx.print_question_seen = True
                        self.log.log("INFO", f"Pregunta de impresión aceptada: {c.win.describe()}",
                                     jornada=self._day, factura=inv)
                        self.driver.press_ok(c.win)
                return next((c for c in wins if c.kind == WinKind.PREVIEW), None)

            preview = self._wait(ctx, "vista previa tras Ctrl+G", preview_after_question,
                                 {WinKind.PREVIEW, WinKind.PRINT_QUESTION},
                                 self._t("timeout_guardado"))
        except Timeout:
            now = parse_conduce(self._read("ultimo_conduce")) if s["exigir_cambio_ultimo_conduce"] else ""
            outcome = RecoveryPolicy.save_outcome(True, False, ctx.conduce_before, now)
            if ctx.print_question_seen:
                outcome = "GRABADA"   # la pregunta de imprimir solo sale tras grabar
            if outcome == "GRABADA":
                raise FlowAbort("El conduce se grabó (cambió el número) pero no apareció la "
                                "vista previa: imprímalo manualmente.", InvoiceStatus.GUARDADA,
                                PrintStatus.PENDIENTE_VERIFICACION)
            raise FlowAbort("No apareció la vista previa tras Ctrl+G y no se puede confirmar "
                            "si el conduce se grabó. NO se reintentará.", InvoiceStatus.REVISION)
        ctx.preview_seen = True
        ctx.preview_handle = preview.win.handle
        self._update(ctx, estado=InvoiceStatus.GUARDADA, guardado_en=now_iso())
        self.log.log("FACTURA_GUARDADA", "Vista previa del conduce abierta.",
                     jornada=self._day, factura=inv)

    def _print(self, ctx: InvoiceContext) -> None:
        s = self.settings
        if not ctx.preview_seen or not ctx.preview_handle \
                or not self.driver.window_exists(ctx.preview_handle):
            raise FlowAbort("No hay vista previa abierta: no se imprime sin confirmar el guardado.",
                            InvoiceStatus.GUARDADA if ctx.preview_seen else None,
                            PrintStatus.PENDIENTE_VERIFICACION)
        want_print = bool(s["imprimir"])
        if want_print and (s["confirmar_antes_de_imprimir"] or self._mode == Mode.PRUEBA):
            ans = self.ui.ask("Imprimir", f"Conduce de {ctx.inv['escuela_codigo']} grabado. "
                              "¿Imprimirlo ahora?", ["Imprimir", "No imprimir", "Detener"])
            if ans == "Detener":
                raise FlowAbort("Detenido antes de imprimir; la vista previa sigue abierta.",
                                InvoiceStatus.GUARDADA, PrintStatus.PENDIENTE)
            want_print = ans == "Imprimir"
        print_status = PrintStatus.NO_SOLICITADA
        if want_print:
            if self.sm.state != State.PRINTING:
                self._goto(State.PRINTING)
            self._update(ctx)
            if not ctx.print_confirmed:
                self.driver.send_keys(s["tecla_imprimir"], ctx.preview_handle)
                try:
                    dlg = self._wait(ctx, "diálogo «Print»", self._first(WinKind.PRINT),
                                     {WinKind.PREVIEW, WinKind.PRINT}, self._t("timeout_ventana"))
                except Timeout:
                    raise FlowAbort("No apareció el diálogo de impresión tras F9. La vista previa "
                                    "sigue abierta.", InvoiceStatus.GUARDADA, PrintStatus.PENDIENTE)
                ctx.print_confirmed = True  # a partir de aquí la impresión pudo salir
                self.driver.press_ok(dlg.win)
                self.log.log("IMPRESION_ENVIADA", jornada=self._day, factura=ctx.inv)
            self._goto(State.VERIFYING_PRINT)
            self._update(ctx)
            try:
                self._wait(ctx, "cierre del diálogo de impresión", self._none_of(WinKind.PRINT),
                           {WinKind.PREVIEW, WinKind.PRINT}, self._t("timeout_impresion"))
            except Timeout:
                raise FlowAbort("El diálogo de impresión no se cerró.", InvoiceStatus.GUARDADA,
                                PrintStatus.PENDIENTE_VERIFICACION)
            self._sleep(self._t("espera_tras_imprimir") if not self.driver.simulated else 0)
            self._scan(ctx, {WinKind.PREVIEW})
            print_status = PrintStatus.IMPRESA
        elif self.sm.state != State.VERIFYING_PRINT:
            self._goto(State.VERIFYING_PRINT, "Sin imprimir")
        # Cerrar la vista previa con Esc.
        self.driver.send_keys(s["tecla_cerrar_vista_previa"], ctx.preview_handle)
        try:
            self._wait(ctx, "cierre de la vista previa", self._none_of(WinKind.PREVIEW),
                       {WinKind.PREVIEW}, self._t("timeout_ventana"))
        except Timeout:
            raise FlowAbort("La vista previa no se cerró con Esc.", InvoiceStatus.GUARDADA,
                            print_status if print_status == PrintStatus.IMPRESA
                            else PrintStatus.PENDIENTE_VERIFICACION)
        self._update(ctx, estado_impresion=print_status)
        self.log.log("IMPRESION_COMPLETADA" if print_status == PrintStatus.IMPRESA else "INFO",
                     "" if print_status == PrintStatus.IMPRESA else "Guardada sin imprimir.",
                     jornada=self._day, factura=ctx.inv)

    def _finish(self, ctx: InvoiceContext) -> None:
        s = self.settings
        after = ""
        if s["exigir_cambio_ultimo_conduce"] and ctx.conduce_before:
            box = {"v": ""}

            def changed() -> bool:
                box["v"] = parse_conduce(self._read("ultimo_conduce"))
                return bool(box["v"]) and box["v"] != ctx.conduce_before

            if not self._poll_until(ctx, "número de conduce", changed,
                                    self._verify_timeout()):
                raise FlowAbort("Se vio la vista previa pero el rótulo «ULTIMAS CONDUCE "
                                "REGISTRADO» no cambió. Verifique el conduce en SisFaCon.",
                                InvoiceStatus.GUARDADA, ctx.inv["estado_impresion"])
            after = box["v"]
        self._update(ctx, estado=InvoiceStatus.COMPLETADA, completado_en=now_iso(),
                     conduce_despues=after, mensaje=f"Conduce {after}".strip())
        self.log.log("FACTURA_COMPLETADA", f"Conduce {after}".strip(),
                     jornada=self._day, factura=ctx.inv, estado=InvoiceStatus.COMPLETADA)
        if self._mode == Mode.PRUEBA:
            ans = self.ui.ask("Resultado de la prueba",
                              "¿El conduce aparece correcto en SisFaCon (escuela, producto) "
                              "y salió bien impreso?", ["Sí, todo correcto", "No"])
            if ans == "Sí, todo correcto":
                self.settings.set("prueba_superada", True)
                self.log.log("INFO", "Prueba superada: modo automático habilitado.",
                             jornada=self._day, factura=ctx.inv)
            else:
                self.settings.set("prueba_superada", False)
                self._update(ctx, estado=InvoiceStatus.REVISION,
                             mensaje="El usuario indicó que la prueba no fue correcta.")

    # ======================================================== recuperación
    def _recover(self, ctx: InvoiceContext, win: WinInfo, phase: str) -> str:
        """Atiende la violación de acceso. Devuelve la fase desde la que seguir."""
        ctx.attempts += 1
        self._update(ctx, intentos_recuperacion=ctx.attempts)
        self.log.log("ERROR_ACCESO", f"Intento {ctx.attempts}. Fase: {phase}. {win.describe()}",
                     "ERROR", jornada=self._day, factura=ctx.inv)
        self._screenshot(ctx)
        policy = RecoveryPolicy(self.settings["max_intentos_recuperacion"])
        if ctx.attempts > policy.max_attempts:
            self.log.log("RECUPERACION_FALLIDA", "Límite de intentos alcanzado.", "ERROR",
                         jornada=self._day, factura=ctx.inv)
            raise FlowAbort(f"La violación de acceso se repitió {ctx.attempts} veces. El mensaje "
                            "sigue en pantalla para que lo revise.")
        if self.sm.state == State.PAUSED:
            self.sm.resume()
        self._goto(State.RECOVERING, f"Intento {ctx.attempts}")
        self.log.log("RECUPERACION_INICIADA", jornada=self._day, factura=ctx.inv)
        # Solo se pulsa OK en ESTA ventana, ya identificada como el error conocido.
        self.driver.press_ok(win)
        end = time.monotonic() + self._t("timeout_ventana")
        while self.driver.window_exists(win.handle):
            if time.monotonic() > end:
                raise FlowAbort("El mensaje de error no se cerró al pulsar OK.")
            self._sleep(self._poll())
        self._sleep(self._t("espera_estabilizacion") if not self.driver.simulated else 0)
        if not self.driver.find_main():
            raise FlowAbort("La ventana principal de SisFaCon se cerró tras el error. "
                            "No se reiniciará automáticamente.")
        ctx.recovering = True

        if phase == "select":
            # Todavía no se pulsó Ctrl+G: es seguro volver a elegir la escuela.
            self._scan(ctx, set())
            self.log.log("RECUPERACION_EXITOSA", "Se vuelve a seleccionar la escuela con F7.",
                         jornada=self._day, factura=ctx.inv)
            return "select"

        if phase == "save":
            now = parse_conduce(self._read("ultimo_conduce")) \
                if self.settings["exigir_cambio_ultimo_conduce"] else ""
            if not ctx.preview_seen:
                wins = self._scan(ctx, {WinKind.PREVIEW})
                prev = next((c for c in wins if c.kind == WinKind.PREVIEW), None)
                if prev:
                    ctx.preview_seen, ctx.preview_handle = True, prev.win.handle
            outcome = RecoveryPolicy.save_outcome(ctx.save_attempted, ctx.preview_seen,
                                                  ctx.conduce_before, now)
            if outcome == "NO_GRABADA":
                self.log.log("RECUPERACION_EXITOSA", jornada=self._day, factura=ctx.inv)
                return "select"
            if outcome == "GRABADA" and ctx.preview_seen:
                self._update(ctx, estado=InvoiceStatus.GUARDADA, guardado_en=now_iso())
                self.log.log("RECUPERACION_EXITOSA", "El conduce se grabó; se continúa con la "
                             "impresión.", jornada=self._day, factura=ctx.inv)
                self._goto(State.PRINTING if self.settings["imprimir"] else State.VERIFYING_PRINT)
                return "print"
            if outcome == "GRABADA":
                raise FlowAbort("El conduce se grabó (cambió el número) pero la vista previa no "
                                "está abierta: imprímalo manualmente.", InvoiceStatus.GUARDADA,
                                PrintStatus.PENDIENTE_VERIFICACION)
            raise FlowAbort("Violación de acceso después de Ctrl+G: no se puede confirmar si el "
                            "conduce se grabó. NO se repetirá el guardado.", InvoiceStatus.REVISION)

        # phase == "print": la factura ya está grabada; nunca se vuelve a grabar.
        wins = self._scan(ctx, {WinKind.PREVIEW, WinKind.PRINT})
        preview_open = any(c.kind == WinKind.PREVIEW for c in wins)
        if not ctx.print_confirmed and preview_open \
                and not any(c.kind == WinKind.PRINT for c in wins):
            self.log.log("RECUPERACION_EXITOSA", "Se reintenta F9 (aún no se había impreso).",
                         jornada=self._day, factura=ctx.inv)
            self._goto(State.PRINTING)
            return "print"
        raise FlowAbort("Violación de acceso durante la impresión. El conduce está grabado; "
                        "compruebe si se imprimió.", InvoiceStatus.GUARDADA,
                        PrintStatus.PENDIENTE_VERIFICACION)
