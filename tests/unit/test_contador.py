"""Contador «Linea(s)» leído por OCR: lecturas imperfectas o ilegibles."""
import unittest

from tests.helpers import make_ctx, make_day, make_engine

from automation import RunOptions
from day_manager import InvoiceStatus
from verification import parse_line_count


class TestLecturaContador(unittest.TestCase):
    def test_confusiones_ocr(self):
        for text, n in [("0 Linea(s)", 0), ("O Linea(s)", 0), ("o Linea(s)", 0),
                        ("OLinea(s)", 0), ("0 Línea(s)", 0), ("1 Linea(s)", 1),
                        ("l Linea(s)", 1), ("0 L1nea(s)", 0), ("basura | 0 Linea(s)", 0),
                        ("12 Linea(s)", 12)]:
            self.assertEqual(parse_line_count(text), n, text)
        for text in ("", None, "Linea(s)", "sin texto"):
            self.assertIsNone(parse_line_count(text), text)


class TestContadorIlegible(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(3)
        self.day = make_day(self.ctx)
        self.engine, self.drv, _ = make_engine(self.ctx)
        self.drv.counter_unreadable = True

    def test_sigue_verificando_por_descripcion(self):
        self.engine.run(self.day, RunOptions())
        estados = [i["estado"] for i in self.ctx.days.invoices(self.day)]
        self.assertEqual(estados, [InvoiceStatus.COMPLETADA] * 3)
        avisos = [e for e in self.ctx.logger.search() if "solo por su descripción" in e["mensaje"]]
        self.assertEqual(len(avisos), 1)          # se avisa una sola vez

    def test_producto_incorrecto_se_detecta_igual(self):
        self.drv.inject("wrong_product_desc", "1000")
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.ctx.days.invoices(self.day)[0]["estado"], InvoiceStatus.ERROR)
        self.assertEqual(len(self.drv.saved), 0)

    def test_si_no_es_opcional_se_detiene(self):
        self.ctx.settings.set("contador_lineas_opcional", False)
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.ctx.days.invoices(self.day)[0]["estado"], InvoiceStatus.PENDIENTE)
        self.assertEqual(len(self.drv.saved), 0)

    def test_error_antes_del_producto_se_recupera(self):
        """Caso de la captura: error justo tras elegir la escuela, aún sin producto."""
        code = self.ctx.days.invoices(self.day)[0]["escuela_codigo"]
        self.drv.inject("av_after_select", code)
        self.engine.run(self.day, RunOptions())
        self.assertEqual([i["estado"] for i in self.ctx.days.invoices(self.day)],
                         [InvoiceStatus.COMPLETADA] * 3)
        self.assertEqual(self.drv.saved_count(code), 1)

    def test_error_despues_del_producto_no_duplica_lineas(self):
        """Si el producto ya se había escrito y el contador es ilegible, no reescribirlo."""
        ctx_inv = self.ctx.days.invoices(self.day)[0]
        from automation import InvoiceContext
        ic = InvoiceContext(inv=ctx_inv, recovering=True, product_typed=True)
        self.engine._day = self.ctx.days.get_day(self.day)
        from automation import FlowAbort
        with self.assertRaises(FlowAbort):
            self.engine._product(ic)
        self.assertEqual(self.drv.lines, [])


if __name__ == "__main__":
    unittest.main()
