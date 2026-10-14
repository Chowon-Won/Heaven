"""Calibración con celdas arrastrables: conversión de coordenadas."""
import unittest

from tests.helpers import make_ctx  # noqa: F401  (ajusta sys.path)

from calibration import boxes_to_entries, entries_to_boxes, fields_for_window


class TestCeldas(unittest.TestCase):
    def test_campos_por_ventana(self):
        self.assertIn("codigo_centro", fields_for_window("principal"))
        self.assertEqual(fields_for_window("busqueda"), ["texto_busqueda"])

    def test_ida_y_vuelta_con_escala_125(self):
        cal = {"codigo_centro": {"ventana": "principal", "tipo": "region", "x": 750, "y": 250,
                                 "w": 175, "h": 30, "metodo": "ocr",
                                 "ancho_ventana": 1440, "alto_ventana": 1000}}
        boxes = entries_to_boxes(cal, "principal", 1.25)
        self.assertEqual(boxes["codigo_centro"], (600, 200, 140, 24))
        out = boxes_to_entries(boxes, cal, "principal", 1.25, (1440, 1000))
        e = out["codigo_centro"]
        self.assertEqual((e["x"], e["y"], e["w"], e["h"]), (750, 250, 175, 30))
        self.assertEqual(e["metodo"], "ocr")               # se conserva el método
        self.assertEqual((e["ancho_ventana"], e["alto_ventana"]), (1440, 1000))
        # Los campos sin calibrar reciben un recuadro inicial para arrastrar.
        self.assertIn("contador_lineas", boxes)

    def test_quitar_y_recortar(self):
        cal = {"nombre_centro": {"ventana": "principal", "tipo": "region", "x": 1, "y": 1,
                                 "w": 5, "h": 5}}
        boxes = {"codigo_centro": (1400, 990, 200, 50)}       # se sale de la ventana
        out = boxes_to_entries(boxes, cal, "principal", 1.0, (1440, 1000), {"nombre_centro"})
        self.assertNotIn("nombre_centro", out)
        e = out["codigo_centro"]
        self.assertLessEqual(e["x"] + e["w"], 1440)
        self.assertLessEqual(e["y"] + e["h"], 1000)

    def test_punto_antiguo_se_agranda(self):
        cal = {"celda_codigo_producto": {"ventana": "principal", "tipo": "punto", "x": 97,
                                         "y": 217, "w": 6, "h": 6}}
        x, y, w, h = entries_to_boxes(cal, "principal", 1.0)["celda_codigo_producto"]
        self.assertEqual((x + w / 2, y + h / 2), (100, 220))  # mismo centro de clic
        self.assertGreater(w, 6)


if __name__ == "__main__":
    unittest.main()
