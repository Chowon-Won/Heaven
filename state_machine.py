"""Máquina de estados explícita del flujo de facturación."""
from __future__ import annotations

import threading
from enum import Enum
from typing import Callable


class State(str, Enum):
    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    SELECTING_SCHOOL = "SELECTING_SCHOOL"
    VERIFYING_SCHOOL = "VERIFYING_SCHOOL"
    ENTERING_PRODUCT = "ENTERING_PRODUCT"
    VERIFYING_PRODUCT = "VERIFYING_PRODUCT"
    SAVING_INVOICE = "SAVING_INVOICE"
    VERIFYING_SAVE = "VERIFYING_SAVE"
    PRINTING = "PRINTING"
    VERIFYING_PRINT = "VERIFYING_PRINT"
    RECOVERING = "RECOVERING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    COMPLETED = "COMPLETED"


STATE_LABELS = {
    State.IDLE: "En espera",
    State.VALIDATING: "Validando SisFaCon",
    State.SELECTING_SCHOOL: "Seleccionando escuela",
    State.VERIFYING_SCHOOL: "Verificando escuela",
    State.ENTERING_PRODUCT: "Introduciendo producto",
    State.VERIFYING_PRODUCT: "Verificando producto",
    State.SAVING_INVOICE: "Grabando factura",
    State.VERIFYING_SAVE: "Verificando grabación",
    State.PRINTING: "Imprimiendo",
    State.VERIFYING_PRINT: "Verificando impresión",
    State.RECOVERING: "Recuperando tras error",
    State.PAUSED: "En pausa",
    State.ERROR: "Detenido por error",
    State.COMPLETED: "Completado",
}

S = State
# Transiciones permitidas. PAUSED, RECOVERING y ERROR se tratan aparte.
TRANSITIONS: dict[State, set[State]] = {
    S.IDLE: {S.VALIDATING},
    S.VALIDATING: {S.SELECTING_SCHOOL, S.COMPLETED, S.VALIDATING},
    S.SELECTING_SCHOOL: {S.VERIFYING_SCHOOL},
    S.VERIFYING_SCHOOL: {S.ENTERING_PRODUCT, S.VERIFYING_PRODUCT},
    S.ENTERING_PRODUCT: {S.VERIFYING_PRODUCT},
    S.VERIFYING_PRODUCT: {S.SAVING_INVOICE},
    S.SAVING_INVOICE: {S.VERIFYING_SAVE},
    S.VERIFYING_SAVE: {S.PRINTING, S.VERIFYING_PRINT},
    S.PRINTING: {S.VERIFYING_PRINT},
    # Tras imprimir: siguiente escuela (VALIDATING) o fin.
    S.VERIFYING_PRINT: {S.VALIDATING, S.COMPLETED},
    # La recuperación reanuda en el paso seguro que corresponda.
    S.RECOVERING: {S.SELECTING_SCHOOL, S.VERIFYING_SAVE, S.VERIFYING_PRINT,
                   S.PRINTING, S.RECOVERING},
    S.ERROR: {S.IDLE},
    S.COMPLETED: {S.IDLE},
    S.PAUSED: set(),  # vuelve siempre al estado previo
}
ACTIVE_STATES = set(State) - {S.IDLE, S.ERROR, S.COMPLETED, S.PAUSED}


class InvalidTransition(RuntimeError):
    pass


class StateMachine:
    def __init__(self, on_change: Callable[[State, State, str], None] | None = None):
        self._state = State.IDLE
        self._before_pause: State | None = None
        self._lock = threading.Lock()
        self.on_change = on_change
        self.history: list[tuple[State, State, str]] = []

    @property
    def state(self) -> State:
        return self._state

    def can(self, new: State) -> bool:
        cur = self._state
        if new in (S.ERROR,) and cur != S.ERROR:
            return True
        if new == S.RECOVERING and cur in ACTIVE_STATES:
            return True
        if new == S.PAUSED and cur in ACTIVE_STATES:
            return True
        if cur == S.PAUSED:
            return new == self._before_pause or new == S.ERROR
        return new in TRANSITIONS.get(cur, set())

    def transition(self, new: State, reason: str = "") -> None:
        with self._lock:
            if not self.can(new):
                raise InvalidTransition(f"Transición no permitida: {self._state.value} -> {new.value}")
            old = self._state
            if new == S.PAUSED:
                self._before_pause = old
            self._state = new
            self.history.append((old, new, reason))
        if self.on_change:
            self.on_change(old, new, reason)

    def pause(self, reason: str = "") -> None:
        self.transition(S.PAUSED, reason)

    def resume(self, reason: str = "") -> None:
        if self._state != S.PAUSED or self._before_pause is None:
            raise InvalidTransition("No hay una pausa activa.")
        self.transition(self._before_pause, reason or "Reanudado")
        self._before_pause = None

    def reset(self) -> None:
        with self._lock:
            old = self._state
            self._state = State.IDLE
            self._before_pause = None
            self.history.append((old, State.IDLE, "reinicio"))
        if self.on_change:
            self.on_change(old, State.IDLE, "reinicio")
