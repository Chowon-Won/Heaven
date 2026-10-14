"""Pruebas 4, 15, 16 y 17: jornadas, recuperación tras cierre, historial y exportación."""
import csv
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_ctx, make_day, make_engine

from automation import RunOptions
from day_manager import DayStatus, InvoiceStatus, Mode
from state_machine import InvalidTransition, State, StateMachine


class TestJornadas(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(3)

    def test_04_producto_distinto_por_jornada(self):
        d1 = make_day(self.ctx, "1000", "2026-10-14")
        d2 = make_day(self.ctx, "1005", "2026-10-15")
        self.assertEqual(self.ctx.days.get_day(d1)["producto_codigo"], "1000")
        self.assertEqual(self.ctx.days.get_day(d2)["producto_codigo"], "1005")
        e, drv, _ = make_engine(self.ctx)
        e.run(d2, RunOptions())
        self.assertEqual({tuple(s["productos"]) for s in drv.saved}, {("1005",)})

    def test_04_copia_del_producto_no_cambia_con_el_catalogo(self):
        d = make_day(self.ctx, "1000")
        p = self.ctx.products.get_by_code("1000")
        self.ctx.products.update(p["id"], codigo="1001", nombre="Pan sobado")
        day = self.ctx.days.get_day(d)
        self.assertEqual((day["producto_codigo"], day["producto_nombre"]), ("1000", "Pan"))

    def test_lista_sin_duplicados(self):
        s = self.ctx.schools.list()
        with self.assertRaises(ValueError):
            self.ctx.days.create_day("2026-10-14", self.ctx.products.get_by_code("1000"),
                                     [s[0], s[0]], Mode.SIMULADO)

    def test_aviso_escuela_ya_facturada_hoy(self):
        d = make_day(self.ctx, mode=Mode.AUTOMATICO)
        inv = self.ctx.days.invoices(d)[0]
        self.ctx.days.update_invoice(inv["id"], estado=InvoiceStatus.COMPLETADA)
        codes = [s["codigo"] for s in self.ctx.schools.list()]
        found = self.ctx.days.schools_already_processed("2026-10-14", codes)
        self.assertEqual([f["escuela_codigo"] for f in found], [inv["escuela_codigo"]])
        self.assertEqual(self.ctx.days.schools_already_processed("2026-10-15", codes), [])

    def test_15_jornada_interrumpida_sin_repetir(self):
        d = make_day(self.ctx)
        invs = self.ctx.days.invoices(d)
        # Simula un cierre inesperado: 1 completada, 1 tras Ctrl+G, 1 pendiente.
        self.ctx.days.set_day_status(d, DayStatus.EN_CURSO)
        self.ctx.days.update_invoice(invs[0]["id"], estado=InvoiceStatus.COMPLETADA)
        self.ctx.days.update_invoice(invs[1]["id"], estado=InvoiceStatus.EN_PROCESO,
                                     guardado_intentado=1)
        found = self.ctx.days.find_interrupted()
        self.assertEqual([j["id"] for j in found], [d])
        affected = self.ctx.days.mark_interrupted(d)
        self.assertEqual(len(affected), 1)
        self.assertEqual(self.ctx.days.invoice(invs[1]["id"])["estado"], InvoiceStatus.REVISION)
        self.assertEqual(self.ctx.days.find_interrupted(), [])
        e, drv, _ = make_engine(self.ctx)
        e.run(d, RunOptions())
        self.assertEqual([s["escuela"] for s in drv.saved], [invs[2]["escuela_codigo"]])
        estados = [i["estado"] for i in self.ctx.days.invoices(d)]
        self.assertEqual(estados, [InvoiceStatus.COMPLETADA, InvoiceStatus.REVISION,
                                   InvoiceStatus.COMPLETADA])
        # El usuario confirma en SisFaCon que no existe y la reactiva.
        self.ctx.days.reset_to_pending(invs[1]["id"])
        e.run(d, RunOptions())
        self.assertEqual(len(drv.saved), 2)

    def test_16_historial_tras_eliminar(self):
        d = make_day(self.ctx)
        e, _, _ = make_engine(self.ctx)
        e.run(d, RunOptions())
        inv = self.ctx.days.invoices(d)[0]
        self.ctx.schools.delete(inv["escuela_id"])
        self.ctx.products.delete(self.ctx.products.get_by_code("1000")["id"])
        inv2 = self.ctx.days.invoices(d)[0]
        self.assertEqual(inv2["escuela_nombre"], inv["escuela_nombre"])
        self.assertEqual(inv2["estado"], InvoiceStatus.COMPLETADA)
        self.assertEqual(self.ctx.days.get_day(d)["producto_codigo"], "1000")
        ev = self.ctx.logger.search(escuela=inv["escuela_codigo"])
        self.assertTrue(ev)
        self.assertTrue(self.ctx.logger.search(producto="1000"))

    def test_17_exportar_registros(self):
        d = make_day(self.ctx)
        e, _, _ = make_engine(self.ctx)
        e.run(d, RunOptions())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "historial.csv"
            n = self.ctx.logger.export_csv(path, self.ctx.logger.search(tipo="FACTURA_COMPLETADA"))
            self.assertEqual(n, 3)
            with open(path, encoding="utf-8-sig") as fh:
                rows = list(csv.reader(fh, delimiter=";"))
        self.assertEqual(rows[0][0], "fecha_hora")
        self.assertEqual(len(rows), 4)
        self.assertTrue(rows[1][5].startswith("0"))   # código con cero inicial


class TestMaquinaEstados(unittest.TestCase):
    def test_transiciones(self):
        sm = StateMachine()
        sm.transition(State.VALIDATING)
        sm.transition(State.SELECTING_SCHOOL)
        with self.assertRaises(InvalidTransition):
            sm.transition(State.SAVING_INVOICE)       # no se puede saltar la verificación
        sm.pause()
        self.assertEqual(sm.state, State.PAUSED)
        sm.resume()
        self.assertEqual(sm.state, State.SELECTING_SCHOOL)
        sm.transition(State.RECOVERING)
        sm.transition(State.SELECTING_SCHOOL)
        sm.transition(State.ERROR)
        with self.assertRaises(InvalidTransition):
            sm.transition(State.SAVING_INVOICE)


if __name__ == "__main__":
    unittest.main()
