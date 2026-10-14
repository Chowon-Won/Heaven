"""Situaciones reales probables en SisFaCon (búsqueda, OCR, formulario)."""
import unittest

from tests.helpers import make_ctx, make_day, make_engine

from automation import RunOptions
from day_manager import InvoiceStatus
from verification import text_matches


class Base(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(3)
        self.day = make_day(self.ctx)
        self.engine, self.drv, self.ui = make_engine(self.ctx)

    def states(self):
        return [i["estado"] for i in self.ctx.days.invoices(self.day)]


class TestBusqueda(Base):
    def test_busqueda_solo_por_nombre_sin_resultados(self):
        """El código no filtra nada: Esc cierra la búsqueda y reintenta por nombre."""
        self.drv.search_names_only = True
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)
        self.assertIn(("search", "{ESC}"), self.drv.keys_log)
        self.assertEqual(len(self.drv.saved), 3)

    def test_busqueda_que_elige_la_primera_fila(self):
        """Enter sin resultados elige otra escuela: se detecta y se corrige por nombre."""
        self.drv.search_names_only = True
        self.drv.no_match_selects_first = True
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)
        codes = [i["escuela_codigo"] for i in self.ctx.days.invoices(self.day)]
        self.assertEqual([s["escuela"] for s in self.drv.saved], codes)

    def test_sin_reintento_se_detiene(self):
        self.ctx.settings.set("reintentar_busqueda_alternativa", False)
        self.drv.search_names_only = True
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states()[0], InvoiceStatus.ERROR)
        self.assertEqual(self.drv.list_windows(), [])   # la búsqueda quedó cerrada
        self.assertEqual(len(self.drv.saved), 0)

    def test_escuela_inexistente_en_sisfacon(self):
        inv = self.ctx.days.invoices(self.day)[0]
        del self.drv.clients[inv["escuela_codigo"]]
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states()[0], InvoiceStatus.ERROR)
        self.assertIn("no aparece", self.ctx.days.invoices(self.day)[0]["mensaje"])
        self.assertEqual(len(self.drv.saved), 0)


class TestLecturasOCR(Base):
    def test_ultimo_conduce_ilegible_no_detiene(self):
        self.drv.conduce_unreadable = True
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)

    def test_formulario_no_nuevo_sin_contador(self):
        """Si SisFaCon dejara la escuela anterior tras grabar y el contador es ilegible,
        el macro no añade el producto encima: se detiene sin grabar."""
        self.drv.counter_unreadable = True
        self.drv.keeps_school_after_save = True
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA, InvoiceStatus.PENDIENTE,
                                         InvoiceStatus.PENDIENTE])
        self.assertIn("no es nuevo", self.ctx.days.invoices(self.day)[1]["mensaje"])
        self.assertEqual(len(self.drv.saved), 1)

    def test_varias_lecturas_ocr(self):
        self.assertTrue(text_matches("Pan de zanahoria", "P4N DE Z@N | PAN DE ZANAHORIA"))
        self.assertFalse(text_matches("Pan de zanahoria", "LECHE | AGUA"))


if __name__ == "__main__":
    unittest.main()


class TestReintentarErrores(Base):
    def test_solo_reintenta_las_no_grabadas(self):
        invs = self.ctx.days.invoices(self.day)
        self.ctx.days.update_invoice(invs[0]["id"], estado=InvoiceStatus.ERROR)
        self.ctx.days.update_invoice(invs[1]["id"], estado=InvoiceStatus.REVISION,
                                     guardado_intentado=1)
        self.assertEqual(self.ctx.days.reset_errors(self.day), 1)
        estados = [i["estado"] for i in self.ctx.days.invoices(self.day)]
        self.assertEqual(estados[:2], [InvoiceStatus.PENDIENTE, InvoiceStatus.REVISION])


class TestAbrirBusqueda(Base):
    def test_f7_perdido_se_reintenta(self):
        self.ctx.settings.set("timeout_ventana", 0.2)
        self.drv.inject("f7_ignored")
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)
        self.assertGreaterEqual(sum(1 for k in self.drv.keys_log if k == ("main", "{F7}")), 4)

    def test_f7_perdido_usa_el_boton(self):
        self.drv.has_search_button = True
        self.drv.inject("f7_ignored")
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)
        self.assertIn(("main", "[botón Buscar Centro]"), self.drv.keys_log)

    def test_sisfacon_no_responde_nunca(self):
        self.drv.inject("f7_ignored", times=-1)
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states()[0], InvoiceStatus.ERROR)
        self.assertIn("no abrió", self.ctx.days.invoices(self.day)[0]["mensaje"])
        self.assertEqual(len(self.drv.saved), 0)

    def test_busqueda_olvidada_se_cierra_sola(self):
        self.drv._open("search", "Seleccione un Cliente", "Texto búsqueda")
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)
        self.assertIn(("search", "{ESC}"), self.drv.keys_log)


class TestEnterCantidad(Base):
    """SisFaCon real: el producto queda en la fila azul hasta un Enter en Cantidad."""

    def test_segundo_enter_automatico(self):
        self.drv.needs_qty_enter = True
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)
        self.assertEqual([s["productos"] for s in self.drv.saved], [["1000"]] * 3)

    def test_descripcion_calibrada_en_fila_de_entrada(self):
        self.drv.needs_qty_enter = True
        self.drv.desc_region_on_entry_row = True    # tras añadir la línea queda vacía
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)

    def test_producto_equivocado_no_recibe_enter_extra(self):
        self.drv.needs_qty_enter = True
        self.drv.inject("wrong_product_desc", "1000")
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states()[0], InvoiceStatus.ERROR)
        self.assertEqual(self.drv.lines, [])        # no se añadió la línea equivocada
        self.assertEqual(len(self.drv.saved), 0)

