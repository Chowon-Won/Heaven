"""Menú de 5 semanas, jornada anterior y eliminación de jornadas."""
import unittest
from datetime import date

from tests.helpers import make_ctx, make_day

from day_manager import Mode
from menu_manager import menu_day, week_of_month


class TestSemanas(unittest.TestCase):
    def test_semana_del_mes(self):
        # Noviembre 2026 empieza en domingo: ese domingo no cuenta.
        self.assertEqual(week_of_month(date(2026, 11, 2)), 1)    # lunes
        self.assertEqual(week_of_month(date(2026, 11, 7)), 1)    # sábado
        self.assertEqual(week_of_month(date(2026, 11, 9)), 2)
        self.assertEqual(week_of_month(date(2026, 11, 30)), 5)
        # Octubre 2026 empieza en jueves.
        self.assertEqual(week_of_month(date(2026, 10, 1)), 1)
        self.assertEqual(week_of_month(date(2026, 10, 5)), 2)
        self.assertEqual(week_of_month(date(2026, 10, 14)), 3)
        # Agosto 2026 empieza en sábado y tiene 6 semanas: la 6.ª vuelve a la 1.
        self.assertEqual(week_of_month(date(2026, 8, 31)), 1)

    def test_dia(self):
        self.assertEqual(menu_day(date(2026, 11, 7)), 5)         # sábado
        self.assertIsNone(menu_day(date(2026, 11, 8)))           # domingo


class TestMenu(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(2)
        self.pan = self.ctx.products.get_by_code("1000")
        self.zan = self.ctx.products.get_by_code("1005")

    def test_producto_segun_fecha(self):
        m = self.ctx.menu
        m.set(1, 0, self.pan["id"])          # semana 1, lunes
        m.set(1, 5, self.zan["id"])          # semana 1, sábado
        self.assertEqual(m.product_for_date(date(2026, 11, 2))[0], self.pan["id"])
        self.assertEqual(m.product_for_date(date(2026, 11, 7))[0], self.zan["id"])
        self.assertIsNone(m.product_for_date(date(2026, 11, 3))[0])   # sin menú
        m.set(1, 0, None)
        self.assertIsNone(m.product_for_date(date(2026, 11, 2))[0])

    def test_producto_desactivado_no_se_propone(self):
        self.ctx.menu.set(1, 0, self.pan["id"])
        self.ctx.products.set_active(self.pan["id"], False)
        self.assertIsNone(self.ctx.menu.product_for_date(date(2026, 11, 2))[0])


class TestJornadas(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(2)

    def test_jornada_anterior_mismo_tipo(self):
        make_day(self.ctx, "1000", "2026-11-02", Mode.AUTOMATICO)
        make_day(self.ctx, "1005", "2026-11-03", Mode.SIMULADO)
        prev = self.ctx.days.previous_day("2026-11-04", real=True)
        self.assertEqual((prev["fecha"], prev["producto_codigo"]), ("2026-11-02", "1000"))
        prev = self.ctx.days.previous_day("2026-11-04", real=False)
        self.assertEqual(prev["producto_codigo"], "1005")
        self.assertIsNone(self.ctx.days.previous_day("2026-11-01", real=True))

    def test_eliminar_jornada(self):
        d1 = make_day(self.ctx, "1000", "2026-11-02")
        d2 = make_day(self.ctx, "1005", "2026-11-03")
        self.ctx.logger.log("INFO", "evento de prueba", jornada=self.ctx.days.get_day(d1))
        self.assertEqual(self.ctx.days.delete_day(d1), 2)
        self.assertIsNone(self.ctx.days.get_day(d1))
        self.assertEqual(self.ctx.days.invoices(d1), [])
        self.assertEqual(len(self.ctx.days.invoices(d2)), 2)      # las demás intactas
        self.assertTrue(self.ctx.logger.search(tipo="INFO"))       # el historial se conserva


if __name__ == "__main__":
    unittest.main()


class TestImportarMenu(unittest.TestCase):
    def test_importa_por_nombre_y_avisa_de_los_que_faltan(self):
        from menu_manager import import_menu, parse_week
        ctx = make_ctx(0)
        rows = [{"semana": "I", "lunes": "Pan", "martes": "Muffin de zanahoria",
                 "miercoles": "PAN", "jueves": "", "viernes": "Pan de zanahoria", "sabado": ""},
                {"semana": "Menú PAE-Urbano V2 2025", "lunes": "", "martes": ""}]
        r = import_menu(ctx.menu, rows, ctx.products.list())
        self.assertEqual(r["asignadas"], 3)
        self.assertEqual(list(r["faltan"]), ["Muffin de zanahoria"])
        pan = ctx.products.get_by_code("1000")["id"]
        zan = ctx.products.get_by_code("1005")["id"]
        self.assertEqual(ctx.menu.get(1, 0), pan)
        self.assertEqual(ctx.menu.get(1, 4), zan)        # «Pan de zanahoria» ≠ «Pan»
        self.assertIsNone(ctx.menu.get(1, 3))            # casilla vacía no cambia
        self.assertEqual([parse_week(x) for x in ("III", "Semana 5", "2", "6", "V2 2025")],
                         [3, 5, 2, None, None])
