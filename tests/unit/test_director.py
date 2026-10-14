"""Casilla DIRECTOR en «-»: se repite F7 + escuela. El nombre nunca se guarda."""
import unittest

from tests.helpers import make_ctx, make_day, make_engine

from automation import RunOptions
from day_manager import InvoiceStatus
from verification import is_blank_name, mask_private


class TestDirector(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(3)
        self.day = make_day(self.ctx)
        self.engine, self.drv, _ = make_engine(self.ctx)
        self.code = self.ctx.days.invoices(self.day)[0]["escuela_codigo"]

    def f7_count(self):
        return sum(1 for k in self.drv.keys_log if k == ("main", "{F7}"))

    def test_director_en_guion_repite_la_seleccion(self):
        self.drv.inject("director_blank", self.code)          # solo la 1.ª vez
        self.engine.run(self.day, RunOptions())
        self.assertEqual([i["estado"] for i in self.ctx.days.invoices(self.day)],
                         [InvoiceStatus.COMPLETADA] * 3)
        self.assertEqual(self.f7_count(), 4)                  # 2 para la 1.ª escuela
        self.assertEqual(self.drv.saved_count(self.code), 1)

    def test_director_siempre_en_guion_se_detiene_sin_grabar(self):
        self.drv.inject("director_blank", self.code, times=-1)
        self.engine.run(self.day, RunOptions())
        inv = self.ctx.days.invoices(self.day)[0]
        self.assertEqual(inv["estado"], InvoiceStatus.ERROR)
        self.assertIn("DIRECTOR", inv["mensaje"])
        self.assertEqual(self.f7_count(), 4)                  # 1 + 3 reintentos
        self.assertEqual(len(self.drv.saved), 0)
        self.assertEqual(self.drv.lines, [])                  # no se escribió el producto

    def test_director_en_guion_antes_de_grabar(self):
        self.drv.inject("director_blank_later")               # tras escribir la cantidad
        self.engine.run(self.day, RunOptions())
        self.assertEqual([i["estado"] for i in self.ctx.days.invoices(self.day)],
                         [InvoiceStatus.COMPLETADA] * 3)
        self.assertEqual(self.drv.saved[0]["cantidades"], [100])   # sin línea duplicada
        self.assertEqual(self.f7_count(), 4)

    def test_tras_violacion_de_acceso_tambien_se_comprueba(self):
        self.drv.inject("av_after_select", self.code)
        self.drv.inject("director_blank", self.code, times=2)
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.ctx.days.invoices(self.day)[0]["estado"], InvoiceStatus.COMPLETADA)
        self.assertEqual(self.drv.saved_count(self.code), 1)

    def test_el_nombre_no_se_guarda_en_el_historial(self):
        self.engine.run(self.day, RunOptions())
        textos = " ".join(e["mensaje"] for e in self.ctx.logger.search())
        self.assertNotIn("DIRECTOR DE PRUEBA", textos)
        facturas = " ".join(str(v) for i in self.ctx.days.invoices(self.day) for v in i.values())
        self.assertNotIn("DIRECTOR DE PRUEBA", facturas)

    def test_desactivado(self):
        self.ctx.settings.set("verificar_director", False)
        self.drv.inject("director_blank", self.code, times=-1)
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.ctx.days.invoices(self.day)[0]["estado"], InvoiceStatus.COMPLETADA)


class TestDeteccion(unittest.TestCase):
    def test_guion_y_vacios(self):
        for t in (" -", "-", "—", "", None, " - ", "|", "-."):
            self.assertTrue(is_blank_name(t), repr(t))
        for t in ("IGNACIA SANDOVAL VARGAS", "ANA"):
            self.assertFalse(is_blank_name(t), t)

    def test_nunca_se_muestra_el_nombre(self):
        self.assertNotIn("IGNACIA", mask_private("director_centro", "IGNACIA SANDOVAL"))
        self.assertIn("vacío", mask_private("director_centro", " -"))
        self.assertEqual(mask_private("codigo_centro", "02970"), "02970")


if __name__ == "__main__":
    unittest.main()
