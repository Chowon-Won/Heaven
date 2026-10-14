"""Prueba 9 (reconocer la excepción) y comparaciones de códigos/textos."""
import unittest

from tests.helpers import make_ctx  # noqa: F401  (ajusta sys.path)

from config import Settings
from error_recovery import RecoveryPolicy, WinKind, classify_window
from verification import (codes_match, is_access_violation, parse_conduce,
                          parse_line_count, text_matches)
from window_detection import WinInfo

MSG = ("[Violación de acceso en la dirección 00402DE1 en módulo 'sisfaconexpress.exe'. "
       "Leer de dirección 067F000E. Pulse Ok para continuar]")
TITLE = "SisFaCon Express - Menú Principal"


class TestExcepcionAcceso(unittest.TestCase):
    def test_09_reconoce_con_direcciones_variables(self):
        self.assertTrue(is_access_violation(TITLE, MSG))
        otra = MSG.replace("00402DE1", "0051AB22").replace("067F000E", "00000000")
        self.assertTrue(is_access_violation(TITLE, otra))

    def test_09_reconoce_texto_ocr_sin_acentos(self):
        ocr = "Violacion de acceso en la direccion 0O402DE1 en modulo sisfaconexpress.exe. Pulse Ok"
        self.assertTrue(is_access_violation(TITLE, ocr))

    def test_09_no_confunde_otros_mensajes(self):
        self.assertFalse(is_access_violation(TITLE, "Pulse Ok para continuar"))
        self.assertFalse(is_access_violation(TITLE, "Violación de acceso en módulo 'otro.exe'"))
        self.assertFalse(is_access_violation("Bloc de notas", MSG))
        self.assertFalse(is_access_violation(TITLE, "00402DE1 067F000E"))

    def test_clasificacion_de_ventanas(self):
        s = Settings()
        cases = [
            (WinInfo(1, TITLE, "#32770", MSG), WinKind.ACCESS_VIOLATION),
            (WinInfo(2, "Seleccione un Cliente"), WinKind.SEARCH),
            (WinInfo(3, "Preview - [No name]"), WinKind.PREVIEW),
            (WinInfo(4, "Print", "#32770"), WinKind.PRINT),
            (WinInfo(5, "Confirmar", "#32770", "¿Desea borrar?"), WinKind.UNKNOWN),
        ]
        for win, kind in cases:
            self.assertEqual(classify_window(win, s).kind, kind, win.title)


class TestComparaciones(unittest.TestCase):
    def test_codigos_estrictos(self):
        self.assertTrue(codes_match("02968", "02968"))
        self.assertTrue(codes_match("02968", " 02968 "))
        self.assertTrue(codes_match("02968", "CODIGO 02968"))
        self.assertTrue(codes_match("02968", "O2968"))      # ruido OCR
        self.assertFalse(codes_match("02968", "2968"))      # sin cero inicial
        self.assertFalse(codes_match("02968", "029680"))
        self.assertFalse(codes_match("02968", "07836"))
        self.assertFalse(codes_match("02968", None))

    def test_textos(self):
        self.assertTrue(text_matches("Pan de zanahoria", "PAN DE ZANAHORIA"))
        self.assertTrue(text_matches("PAN", "PAN SOBADO 50G"))
        self.assertFalse(text_matches("Pan de zanahoria", "LECHE ENTERA"))
        self.assertFalse(text_matches("Pan", ""))

    def test_contador_y_conduce(self):
        self.assertEqual(parse_line_count("0 Linea(s)"), 0)
        self.assertEqual(parse_line_count("1 Línea(s)"), 1)
        self.assertIsNone(parse_line_count("Lineas"))
        self.assertEqual(parse_conduce("CONDUCE: FCR 0083941"), "FCR0083941")
        self.assertEqual(parse_conduce("CONDUCE: FCR OO83942"), "FCR0083942")

    def test_politica_de_guardado(self):
        p = RecoveryPolicy
        self.assertEqual(p.save_outcome(False, False, "A", "A"), "NO_GRABADA")
        self.assertEqual(p.save_outcome(True, True, "A", "A"), "GRABADA")
        self.assertEqual(p.save_outcome(True, False, "FCR1", "FCR2"), "GRABADA")
        self.assertEqual(p.save_outcome(True, False, "FCR1", "FCR1"), "INCIERTA")
        self.assertEqual(p.save_outcome(True, False, "", ""), "INCIERTA")


if __name__ == "__main__":
    unittest.main()


class TestProductosParecidos(unittest.TestCase):
    def test_ruido_corto_no_es_producto(self):
        self.assertFalse(text_matches("Pan", "AN"))
        self.assertFalse(text_matches("Pan", "E | AN | EE"))
        self.assertFalse(text_matches("Pan de zanahoria", "AN"))

    def test_pan_no_es_pan_de_zanahoria(self):
        from verification import best_match
        names = ["Pan", "Pan de zanahoria"]
        self.assertEqual(best_match("PAN DE ZANAHORIA", names), "Pan de zanahoria")
        self.assertEqual(best_match("PAN", names), "Pan")
        self.assertEqual(best_match("PAN DE ZANAHORI", names), "Pan de zanahoria")
