"""Facturar solo un rango de escuelas (desde la escuela X hasta la escuela Y)."""
import unittest

from tests.helpers import make_ctx, make_day, make_engine

from automation import RunOptions
from day_manager import InvoiceStatus


class TestRango(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(6)
        self.day = make_day(self.ctx)

    def test_ids_del_rango_incluye_extremos_y_admite_orden_inverso(self):
        invs = self.ctx.days.invoices(self.day)
        ids = self.ctx.days.range_ids(self.day, 2, 4)
        self.assertEqual(ids, [i["id"] for i in invs[1:4]])
        self.assertEqual(self.ctx.days.range_ids(self.day, 4, 2), ids)

    def test_ejecutar_solo_el_rango(self):
        engine, drv, _ = make_engine(self.ctx)
        ids = self.ctx.days.range_ids(self.day, 3, 5)
        engine.run(self.day, RunOptions(invoice_ids=ids))
        estados = [i["estado"] for i in self.ctx.days.invoices(self.day)]
        self.assertEqual(estados, [InvoiceStatus.PENDIENTE] * 2 + [InvoiceStatus.COMPLETADA] * 3
                         + [InvoiceStatus.PENDIENTE])
        codes = [i["escuela_codigo"] for i in self.ctx.days.invoices(self.day)[2:5]]
        self.assertEqual([s["escuela"] for s in drv.saved], codes)

    def test_rango_salta_las_ya_completadas(self):
        engine, drv, _ = make_engine(self.ctx)
        engine.run(self.day, RunOptions(invoice_ids=self.ctx.days.range_ids(self.day, 1, 3)))
        engine.run(self.day, RunOptions(invoice_ids=self.ctx.days.range_ids(self.day, 2, 6)))
        self.assertEqual(len(drv.saved), 6)          # ninguna repetida
        self.assertEqual(len({s["escuela"] for s in drv.saved}), 6)


if __name__ == "__main__":
    unittest.main()
