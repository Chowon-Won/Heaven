"""Pruebas contra SisFaCon Express REAL (solo lectura, no graban ni imprimen).

No se ejecutan por defecto. Para ejecutarlas en el equipo con SisFaCon:

    set SISFACON_REAL=1
    python -m unittest tests.real.test_sisfacon_real -v

Requisitos: SisFaCon abierto en «Registro de Conduce a Centro Educativo» y la
calibración hecha desde la aplicación. La factura de prueba real se hace desde
la pestaña Automatización en «Modo de prueba» (ver docs/PRUEBA_UNA_FACTURA.md).

Estas pruebas NO se han ejecutado durante el desarrollo: no había acceso a
SisFaCon. Solo su resultado en su equipo indica si pasan.
"""
import os
import sys
import time
import unittest

from tests.helpers import ROOT  # noqa: F401  (ajusta sys.path)

REAL = os.environ.get("SISFACON_REAL") == "1" and sys.platform.startswith("win")


@unittest.skipUnless(REAL, "Requiere Windows, SisFaCon abierto y SISFACON_REAL=1")
class TestSisFaConReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app_context import AppContext
        from window_detection import RealDriver
        cls.ctx = AppContext.create()
        cls.drv = RealDriver(cls.ctx.settings)

    def test_r1_ventana_principal(self):
        self.assertTrue(self.drv.find_main(), "No se encontró la ventana principal")

    def test_r2_sin_dialogos_pendientes(self):
        self.drv.find_main()
        pending = self.drv.capture_baseline()
        self.assertEqual(pending, [], [w.describe() for w in pending])

    def test_r3_lectura_campos_calibrados(self):
        self.drv.find_main()
        for name in ("codigo_centro", "ultimo_conduce", "contador_lineas"):
            if self.drv.is_calibrated(name):
                value = self.drv.read_field(name)
                print(f"{name}: {value!r}")
                self.assertTrue(value, f"No se pudo leer {name}")

    def test_r4_abrir_y_cerrar_busqueda(self):
        """Abre F7 y lo cierra con Esc (no selecciona ninguna escuela)."""
        from error_recovery import WinKind, classify_window
        self.drv.find_main()
        self.drv.capture_baseline()
        self.drv.send_keys(self.ctx.settings["tecla_buscar_cliente"])
        found = None
        for _ in range(40):
            for w in self.drv.list_windows():
                if classify_window(w, self.ctx.settings).kind == WinKind.SEARCH:
                    found = w
            if found:
                break
            time.sleep(0.25)
        self.assertIsNotNone(found, "No apareció «Seleccione un Cliente» con F7")
        self.drv.send_keys("{ESC}", found.handle)


if __name__ == "__main__":
    unittest.main()
