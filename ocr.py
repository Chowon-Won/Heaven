"""OCR opcional con Tesseract (solo para datos que no son controles de Windows).

Si Tesseract no está instalado, ``read_rect`` devuelve None y el motor se
detiene en lugar de suponer un resultado.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent


def bundled_tessdata() -> Path | None:
    """Idiomas OCR (español e inglés) incluidos por el instalador."""
    folder = app_dir() / "tessdata"
    return folder if (folder / "spa.traineddata").exists() else None


def tesseract_candidates(settings) -> list[str]:
    """Dónde buscar tesseract.exe, por orden de preferencia."""
    out = []
    custom = (settings.get("ruta_tesseract") or "").strip().strip('"')
    if custom:
        out.append(custom)
    out.append(str(app_dir() / "tesseract" / "tesseract.exe"))      # incluido en el programa
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        out.append(os.path.join(base, "Tesseract-OCR", "tesseract.exe"))
    found = shutil.which("tesseract")
    if found:
        out.append(found)
    return out


class OcrEngine:
    def __init__(self, settings):
        self.settings = settings
        self._ready: bool | None = None
        self.path = ""
        self.version = ""
        self.last_error = ""

    def available(self) -> bool:
        # Un resultado positivo se recuerda; uno negativo se vuelve a comprobar
        # (por si el usuario instala Tesseract sin cerrar el programa).
        if self._ready:
            return True
        self.last_error = ""
        try:
            import pytesseract
        except Exception as exc:
            self.last_error = f"falta el módulo pytesseract ({exc})"
            self._ready = False
            return False
        tried = []
        for cand in tesseract_candidates(self.settings):
            if not cand or cand in tried:
                continue
            tried.append(cand)
            if not os.path.isfile(cand) and cand != shutil.which("tesseract"):
                continue
            pytesseract.pytesseract.tesseract_cmd = cand
            data = bundled_tessdata()
            if data:
                # Siempre los idiomas incluidos (spa + eng), aunque Windows tenga
                # otro TESSDATA_PREFIX de una instalación anterior.
                os.environ["TESSDATA_PREFIX"] = str(data)
            try:
                self.version = str(pytesseract.get_tesseract_version())
                self.path = cand
                self._ready = True
                return True
            except Exception as exc:
                self.last_error = f"{cand}: {exc}"
        if not self.last_error:
            self.last_error = ("no se encontró tesseract.exe (buscado en: "
                               + "; ".join(tried) + ")")
        self._ready = False
        return False

    def status(self) -> str:
        """Texto de diagnóstico para la pantalla de Configuración."""
        if self.available():
            data = os.environ.get("TESSDATA_PREFIX", "(predeterminado)")
            return f"OCR listo: Tesseract {self.version} en {self.path} · idiomas: {data}"
        return f"OCR NO disponible: {self.last_error}"

    def read_rect(self, rect, digits: bool = False, variants: bool = False,
                  accept=None) -> str | None:
        """Lee el texto de una región de pantalla.

        Con ``variants=True`` prueba varios tratamientos de imagen (útil para
        rótulos pequeños, en cursiva o de color, como «0 Linea(s)») y devuelve
        los resultados separados por « | » para que el llamador elija.
        ``accept(texto)`` permite parar en cuanto una lectura es válida (rápido).
        """
        if not self.available():
            return None
        try:
            from PIL import ImageGrab, ImageOps
            import pytesseract
            x, y, w, h = rect
            shot = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
            gray = ImageOps.grayscale(shot)
            big = gray.resize((gray.width * 4, gray.height * 4))
            images = [ImageOps.autocontrast(big)]
            if variants:
                for limit in (110, 150, 190):
                    images.append(big.point(lambda p, t=limit: 255 if p > t else 0))
                images.append(ImageOps.invert(ImageOps.autocontrast(big)))
            lang = self.settings.get("idioma_ocr") or "spa+eng"
            config = "--psm 7" if h < 60 else "--psm 6"
            texts = []
            for img in images:
                try:
                    text = pytesseract.image_to_string(img, lang=lang, config=config)
                except pytesseract.TesseractError:
                    text = pytesseract.image_to_string(img, lang="eng", config=config)
                text = " ".join(text.split())
                if text and accept is not None and accept(text):
                    return text
                if text and text not in texts:
                    texts.append(text)
            return " | ".join(texts) or None
        except Exception as exc:
            self.last_error = f"error al leer la pantalla: {exc}"
            return None
