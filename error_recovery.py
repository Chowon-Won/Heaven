"""Clasificación de ventanas y política de recuperación.

Toda ventana nueva de SisFaCon se clasifica en una de estas clases:

* ACCESS_VIOLATION: la excepción conocida «Violación de acceso ...».
* SEARCH: «Seleccione un Cliente».
* PREVIEW: «Preview - [No name]» (aparece tras Ctrl+G).
* PRINT: diálogo «Print» de Windows (aparece con F9 en la vista previa).
* INFO: mensaje que el usuario declaró inofensivo (regla aprendida).
* UNKNOWN: cualquier otra cosa -> el macro se detiene y NO pulsa nada.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from verification import is_access_violation, normalize_text
from window_detection import WinInfo


class WinKind(str, Enum):
    ACCESS_VIOLATION = "ACCESS_VIOLATION"
    SEARCH = "SEARCH"
    PREVIEW = "PREVIEW"
    PRINT = "PRINT"
    PRINT_QUESTION = "PRINT_QUESTION"   # «¿Desea imprimir…?» tras Ctrl+G
    INFO = "INFO"
    UNKNOWN = "UNKNOWN"


@dataclass
class Classified:
    win: WinInfo
    kind: WinKind
    rule: dict | None = None


def classify_window(win: WinInfo, settings) -> Classified:
    title = win.title or ""
    if is_access_violation(title, win.text, settings["ejecutable"]):
        return Classified(win, WinKind.ACCESS_VIOLATION)
    t = title.lower()
    if settings["titulo_busqueda_cliente"].lower() in t:
        return Classified(win, WinKind.SEARCH)
    preview = (settings["titulo_vista_previa"] or "").lower()
    if preview and t.startswith(preview):
        return Classified(win, WinKind.PREVIEW)
    for p in settings["titulos_dialogo_impresion"] or []:
        if p and t.strip() == p.lower():
            return Classified(win, WinKind.PRINT)
    body = normalize_text(f"{win.title} {win.text}")
    for word in settings["textos_pregunta_imprimir"] or []:
        if word and normalize_text(word) in body:
            return Classified(win, WinKind.PRINT_QUESTION)
    for rule in settings["reglas_dialogos"] or []:
        if _rule_matches(rule, win):
            return Classified(win, WinKind.INFO, rule)
    return Classified(win, WinKind.UNKNOWN)


def _rule_matches(rule: dict, win: WinInfo) -> bool:
    tt = normalize_text(rule.get("titulo_contiene", ""))
    tx = normalize_text(rule.get("texto_contiene", ""))
    if not tt and not tx:
        return False  # una regla vacía aceptaría cualquier ventana
    if tt and tt not in normalize_text(win.title):
        return False
    if tx and tx not in normalize_text(win.text):
        return False
    return True


class RecoveryPolicy:
    """Cuenta los intentos de recuperación de una factura."""

    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max(1, int(max_attempts))

    def can_retry(self, attempts_done: int) -> bool:
        return attempts_done < self.max_attempts

    @staticmethod
    def save_outcome(save_attempted: bool, preview_seen: bool,
                     conduce_before: str, conduce_now: str) -> str:
        """Decide qué se sabe de la grabación tras un error.

        Devuelve "NO_GRABADA" (es seguro reintentar), "GRABADA" o "INCIERTA".
        Nunca deduce que no se grabó a partir del mensaje de error.
        """
        if not save_attempted:
            return "NO_GRABADA"
        if preview_seen:
            return "GRABADA"
        if conduce_before and conduce_now and conduce_now != conduce_before:
            return "GRABADA"
        return "INCIERTA"
