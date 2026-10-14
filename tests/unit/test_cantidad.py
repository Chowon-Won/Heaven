"""Cantidad fija por escuela: se escribe tras el código del producto."""
import unittest

from tests.helpers import make_ctx, make_day, make_engine

from automation import RunOptions
from day_manager import InvoiceStatus, Mode
from import_export import read_table, write_table
from verification import parse_quantity


class TestCantidad(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(3)
        self.day = make_day(self.ctx)
        self.engine, self.drv, _ = make_engine(self.ctx)

    def test_escribe_la_cantidad_de_cada_escuela(self):
        self.engine.run(self.day, RunOptions())
        self.assertEqual([s["cantidades"] for s in self.drv.saved], [[100], [110], [120]])
        self.assertEqual([i["cantidad"] for i in self.ctx.days.invoices(self.day)],
                         [100, 110, 120])

    def test_cantidad_mal_escrita_no_se_graba(self):
        self.drv.inject("qty_ignored")
        self.engine.run(self.day, RunOptions())
        inv = self.ctx.days.invoices(self.day)[0]
        self.assertEqual(inv["estado"], InvoiceStatus.ERROR)
        self.assertIn("cantidad=1", inv["mensaje"])
        self.assertEqual(len(self.drv.saved), 0)

    def test_escuela_sin_cantidad_no_entra_en_la_jornada(self):
        sid = self.ctx.schools.add(codigo="07836", nombre="PEDRO MIR")
        with self.assertRaises(ValueError) as err:
            self.ctx.days.create_day("2026-10-16", self.ctx.products.get_by_code("1000"),
                                     [self.ctx.schools.get(sid)], Mode.SIMULADO)
        self.assertIn("07836", str(err.exception))
        self.assertEqual(len(self.ctx.schools.without_quantity(self.ctx.schools.list())), 1)

    def test_cambiar_cantidad_no_altera_jornada_creada(self):
        s = self.ctx.schools.list()[0]
        self.ctx.schools.update(s["id"], cantidad=999)
        self.assertEqual(self.ctx.days.invoices(self.day)[0]["cantidad"], 100)

    def test_importar_cantidad_desde_excel(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "e.xlsx"
            write_table(p, ["Orden", "Escuela", "Código", "Cantidad"],
                        [[1, "PEDRO MIR", "07836", "304"]])
            rep = self.ctx.schools.import_rows(read_table(p))
        self.assertEqual(rep.agregados, 1)
        self.assertEqual(self.ctx.schools.get_by_code("07836")["cantidad"], 304)

    def test_lectura_de_cantidad(self):
        for text, n in [("304", 304), ("304.00", 304), ("3O4", 304), ("1,250", 1250),
                        (" | 66", 66)]:
            self.assertEqual(parse_quantity(text), n, text)
        self.assertIsNone(parse_quantity("—"))


if __name__ == "__main__":
    unittest.main()
