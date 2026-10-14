"""OCR opcional con Tesseract (solo para datos que no son controles de Windows).

Si Tesseract no está instalado, ``read_rect`` devuelve None y el motor se
detiene en lugar de suponer un resultado.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def bundled_tessdata() -> Path | None:
    """Idiomas OCR (español e inglés) incluidos por el instalador."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent
    folder = base / "tessdata"
    return folder if (folder / "spa.traineddata").exists() else None


class OcrEngine:
    def __init__(self, settings):
        self.settings = settings
        self._ready: bool | None = None

    def available(self) -> bool:
        if self._ready is not None:
            return self._ready
        try:
            import pytesseract
            path = self.settings.get("ruta_tesseract") or ""
            if not path:
                for cand in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                             r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
                    if os.path.exists(cand):
                        path = cand
                        break
            if path:
                pytesseract.pytesseract.tesseract_cmd = path
            data = bundled_tessdata()
            if data and not os.environ.get("TESSDATA_PREFIX"):
                os.environ["TESSDATA_PREFIX"] = str(data)
            elif not shutil.which("tesseract"):
                self._ready = False
                return False
            pytesseract.get_tesseract_version()
            self._ready = True
        except Exception:
            self._ready = False
        return self._ready

    def read_rect(self, rect, digits: bool = False) -> str | None:
        if not self.available():
            return None
        try:
            from PIL import ImageGrab, ImageOps
            import pytesseract
            x, y, w, h = rect
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
            img = ImageOps.grayscale(img)
            img = img.resize((img.width * 3, img.height * 3))
            img = ImageOps.autocontrast(img)
            lang = self.settings.get("idioma_ocr") or "spa+eng"
            config = "--psm 7" if h < 60 else "--psm 6"
            try:
                text = pytesseract.image_to_string(img, lang=lang, config=config)
            except pytesseract.TesseractError:
                text = pytesseract.image_to_string(img, lang="eng", config=config)
            return text.strip() or None
        except Exception:
            return None
