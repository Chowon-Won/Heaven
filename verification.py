"""Comparaciones tolerantes a OCR entre lo esperado y lo leído en pantalla.

Los códigos se comparan de forma ESTRICTA (mismos dígitos, incluidos los
ceros iniciales). Los nombres y descripciones admiten pequeñas diferencias.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Confusiones típicas del OCR cuando se espera un dígito.
_OCR_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0",
                                "I": "1", "l": "1", "|": "1", "i": "1",
                                "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2"})


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def normalize_text(text: str | None) -> str:
    """Mayúsculas, sin acentos, sin puntuación y espacios simples."""
    t = strip_accents(str(text or "")).upper()
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_code(text: str | None, digits_expected: bool = False) -> str:
    t = str(text or "").strip()
    if digits_expected:
        t = t.translate(_OCR_DIGIT_FIX)
    return re.sub(r"[^0-9A-Za-z]", "", t).upper()


def codes_match(expected: str, read: str | None) -> bool:
    """Coincidencia exacta de código (se permite ruido de OCR en dígitos)."""
    if read is None:
        return False
    exp = normalize_code(expected)
    if not exp:
        return False
    digits = exp.isdigit()
    got = normalize_code(read, digits_expected=digits)
    if got == exp:
        return True
    # El OCR de una región puede capturar texto alrededor: se acepta si el
    # código aparece como «palabra» completa, nunca como parte de otro número.
    tokens = re.split(r"[^0-9A-Za-z]+", str(read))
    return any(normalize_code(tok, digits) == exp for tok in tokens if tok)


def similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def text_matches(expected: str, read: str | None, threshold: float = 0.8) -> bool:
    """Nombre o descripción: contenido o similitud suficiente."""
    if not read:
        return False
    parts = [p for p in str(read).split("|") if p.strip()]
    if len(parts) > 1:  # varias lecturas OCR: basta con que una coincida
        return any(text_matches(expected, p, threshold) for p in parts)
    ne, nr = normalize_text(expected), normalize_text(read)
    if not ne:
        return False
    if ne == nr or (len(ne) >= 3 and ne in nr):
        return True
    # Las columnas estrechas pueden recortar la descripción.
    if len(nr) >= 6 and ne.startswith(nr):
        return True
    return similarity(ne, nr) >= threshold


def parse_line_count(text: str | None) -> int | None:
    """Extrae N de «N Linea(s)»."""
    if not text:
        return None
    # Puede venir con varias lecturas OCR separadas por « | »: vale la primera legible.
    for part in str(text).split("|"):
        t = strip_accents(part)
        # El OCR confunde a menudo 0 con O/o/D/Q y 1 con l/I/|.
        m = re.search(r"([0-9OoDQIl]{1,3})\s*[_.,:]?\s*[LI1l|][i1l!|][nm][eéc][a@]", t)
        if m:
            digits = m.group(1).translate(_OCR_DIGIT_FIX)
            if digits.isdigit():
                return int(digits)
        m = re.fullmatch(r"\s*(\d+)\s*", t)
        if m:
            return int(m.group(1))
    return None


def parse_conduce(text: str | None) -> str:
    """Normaliza «CONDUCE: FCR 0083941» a «FCR0083941» (o '' si no hay)."""
    if not text:
        return ""
    t = normalize_text(text)
    m = re.search(r"([A-Z]{1,4})\s*([0-9OIl]{4,})", t)
    if m:
        return m.group(1) + normalize_code(m.group(2), digits_expected=True)
    m = re.search(r"(\d{4,})", t)
    return m.group(1) if m else ""


def is_access_violation(title: str | None, text: str | None,
                        module: str = "sisfaconexpress.exe") -> bool:
    """Reconoce la excepción conocida sin depender de las direcciones.

    Requiere el texto «Violación de acceso» (o la variante en inglés) Y el
    nombre del módulo. El título se usa como apoyo: si está disponible debe
    pertenecer a SisFaCon.
    """
    body = normalize_text(text)
    head = normalize_text(title)
    mod = normalize_text(module)  # "SISFACONEXPRESS EXE"
    has_av = ("VIOLACION DE ACCESO" in body or "ACCESS VIOLATION" in body
              or "VIOLACION DE ACCESO" in head)
    has_module = mod in body or mod.replace(" ", "") in body.replace(" ", "")
    title_ok = (not head) or "SISFACON" in head.replace(" ", "")
    return has_av and has_module and title_ok
