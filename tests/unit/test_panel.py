"""Zonas de SisFaCon que el panel pequeño no debe tapar."""
import unittest

from tests.helpers import make_ctx  # noqa: F401  (ajusta sys.path)

from config import Settings
from window_detection import calibrated_screen_rects


class TestZonas(unittest.TestCase):
    def test_zonas_absolutas_de_la_ventana_principal(self):
        s = Settings()
        s.set("calibracion", {
            "codigo_centro": {"ventana": "principal", "x": 100, "y": 50, "w": 80, "h": 20},
            "texto_busqueda": {"ventana": "busqueda", "x": 5, "y": 5, "w": 6, "h": 6},
        })
        rects = calibrated_screen_rects(s, (1000, 200, 2000, 900))
        self.assertEqual(rects, [(1090, 240, 1190, 280)])     # margen de 10 px
        self.assertEqual(calibrated_screen_rects(s, None), [])


if __name__ == "__main__":
    unittest.main()
