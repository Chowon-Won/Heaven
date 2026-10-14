"""Diagnóstico del OCR cuando Tesseract no está disponible."""
import os
import unittest
from unittest import mock

from tests.helpers import make_ctx  # noqa: F401  (ajusta sys.path)

import ocr
from config import Settings


class TestOcrDiagnostico(unittest.TestCase):
    def test_sin_tesseract_explica_donde_busco(self):
        s = Settings()
        s.set("ruta_tesseract", "C:/no/existe/tesseract.exe")
        engine = ocr.OcrEngine(s)
        with mock.patch.object(ocr.shutil, "which", return_value=None), \
                mock.patch.object(ocr.os.path, "isfile", return_value=False):
            self.assertFalse(engine.available())
            status = engine.status()
        self.assertIn("NO disponible", status)
        self.assertIn("C:/no/existe/tesseract.exe", status)
        self.assertIsNone(engine.read_rect((0, 0, 10, 10)))

    def test_busca_primero_el_tesseract_incluido(self):
        cands = ocr.tesseract_candidates(Settings())
        self.assertTrue(cands[0].endswith(os.path.join("tesseract", "tesseract.exe")))


if __name__ == "__main__":
    unittest.main()
