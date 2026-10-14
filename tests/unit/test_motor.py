"""Pruebas del motor con SisFaCon simulado: 7, 8, 10, 11, 12, 13, 14 y flujo normal."""
import time
import unittest

from tests.helpers import RecordingUI, make_ctx, make_day, make_engine, run_in_thread

from automation import RunOptions
from day_manager import InvoiceStatus, PrintStatus
from state_machine import State


class Base(unittest.TestCase):
    n = 3

    def setUp(self):
        self.ctx = make_ctx(self.n)
        self.day = make_day(self.ctx)
        self.engine, self.drv, self.ui = make_engine(self.ctx)

    def invoices(self):
        return self.ctx.days.invoices(self.day)

    def states(self):
        return [i["estado"] for i in self.invoices()]


class TestFlujoNormal(Base):
    def test_jornada_completa(self):
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)
        self.assertEqual(len(self.drv.saved), 3)
        self.assertEqual(len(self.drv.printed), 3)
        self.assertEqual([s["productos"] for s in self.drv.saved], [["1000"]] * 3)
        self.assertEqual(self.ctx.days.get_day(self.day)["estado"], "COMPLETADA")
        self.assertEqual(self.engine.sm.state, State.COMPLETED)
        # Cada conduce queda registrado con su número.
        self.assertTrue(all(i["conduce_despues"].startswith("FCR") for i in self.invoices()))
        # Secuencia de teclas confirmada: F7, Enter, Enter, ^g, F9 (vista previa), Esc.
        kinds = [k for k in self.drv.keys_log]
        self.assertIn(("preview", "{F9}"), kinds)
        self.assertIn(("preview", "{ESC}"), kinds)

    def test_sin_imprimir(self):
        self.ctx.settings.set("imprimir", False)
        self.engine.run(self.day, RunOptions())
        self.assertEqual(len(self.drv.printed), 0)
        self.assertEqual({i["estado_impresion"] for i in self.invoices()},
                         {PrintStatus.NO_SOLICITADA})

    def test_ejecutar_una_y_grupo(self):
        first = self.invoices()[0]["id"]
        self.engine.run(self.day, RunOptions(invoice_ids=[first]))
        self.assertEqual(self.states().count(InvoiceStatus.COMPLETADA), 1)
        self.engine.run(self.day, RunOptions(limit=1))
        self.assertEqual(self.states().count(InvoiceStatus.COMPLETADA), 2)


class TestVerificaciones(Base):
    def test_07_escuela_incorrecta_una_vez_se_corrige(self):
        code = self.invoices()[1]["escuela_codigo"]
        self.drv.inject("wrong_school", code)          # solo la primera búsqueda falla
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)
        self.assertEqual([s["escuela"] for s in self.drv.saved],
                         [i["escuela_codigo"] for i in self.invoices()])

    def test_07_escuela_incorrecta_no_graba(self):
        code = self.invoices()[1]["escuela_codigo"]
        self.drv.inject("wrong_school", code, times=-1)
        self.drv.inject("wrong_school", self.invoices()[1]["escuela_nombre"], times=-1)
        self.engine.run(self.day, RunOptions())
        st = self.states()
        self.assertEqual(st[0], InvoiceStatus.COMPLETADA)
        self.assertEqual(st[1], InvoiceStatus.ERROR)
        self.assertEqual(st[2], InvoiceStatus.PENDIENTE)       # se detuvo
        self.assertEqual(self.drv.saved_count(code), 0)
        self.assertEqual(len(self.drv.saved), 1)
        self.assertEqual(self.engine.sm.state, State.ERROR)
        self.assertIn("Escuela no seleccionada", self.invoices()[1]["mensaje"])

    def test_08_producto_no_reconocido(self):
        self.drv.inject("unknown_product", "1000")
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states()[0], InvoiceStatus.ERROR)
        self.assertEqual(len(self.drv.saved), 0)

    def test_08_descripcion_distinta(self):
        self.drv.inject("wrong_product_desc", "1000")
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states()[0], InvoiceStatus.ERROR)
        self.assertEqual(len(self.drv.saved), 0)
        self.assertIn("no reconoció", self.invoices()[0]["mensaje"])

    def test_14_ventana_desconocida_detiene_sin_pulsar(self):
        code = self.invoices()[0]["escuela_codigo"]
        self.drv.inject("unknown_after_select", code)
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states()[0], InvoiceStatus.ERROR)
        self.assertEqual(self.drv.ok_presses, [])            # no pulsó OK
        self.assertEqual(len(self.drv.list_windows()), 1)    # la ventana sigue ahí
        self.assertEqual(len(self.drv.saved), 0)

    def test_14_ventana_desconocida_al_inicio(self):
        self.drv._open("other", "Confirmar", "¿Borrar?", "#32770", ["Sí", "No"])
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.PENDIENTE] * 3)
        self.assertEqual(self.drv.ok_presses, [])
        self.assertEqual(self.engine.sm.state, State.ERROR)


class TestRecuperacion(Base):
    def test_recuperacion_tras_seleccionar_escuela(self):
        """Caso de la captura: error justo después de elegir la escuela."""
        code = self.invoices()[0]["escuela_codigo"]
        self.drv.inject("av_after_select", code)
        self.engine.run(self.day, RunOptions())
        inv = self.invoices()[0]
        self.assertEqual(inv["estado"], InvoiceStatus.COMPLETADA)
        self.assertEqual(inv["intentos_recuperacion"], 1)
        self.assertEqual(self.drv.saved_count(code), 1)
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 3)
        tipos = [e["tipo"] for e in self.ctx.logger.search()]
        self.assertIn("ERROR_ACCESO", tipos)
        self.assertIn("RECUPERACION_EXITOSA", tipos)
        # Volvió a pulsar F7 para la misma escuela.
        self.assertEqual(sum(1 for k in self.drv.keys_log if k == ("main", "{F7}")), 4)

    def test_10_limite_de_intentos(self):
        code = self.invoices()[0]["escuela_codigo"]
        self.drv.inject("av_on_select", code, times=-1)        # error permanente
        self.engine.run(self.day, RunOptions())
        inv = self.invoices()[0]
        self.assertEqual(inv["intentos_recuperacion"], 4)       # 3 recuperaciones + el límite
        self.assertEqual(inv["estado"], InvoiceStatus.ERROR)    # nunca se pulsó Ctrl+G
        self.assertEqual(self.drv.ok_presses.count("SisFaCon Express - Menú Principal"), 3)
        self.assertEqual(len(self.drv.list_windows()), 1)       # último error queda visible
        self.assertEqual(self.engine.sm.state, State.ERROR)
        self.assertTrue(any("Automatización detenida" in n[1] for n in self.ui.notifications))

    def test_11_guardado_incierto_no_se_repite(self):
        code = self.invoices()[0]["escuela_codigo"]
        self.drv.inject("av_on_save_saved", code)   # se grabó pero no hay prueba visible
        self.engine.run(self.day, RunOptions())
        inv = self.invoices()[0]
        self.assertEqual(inv["estado"], InvoiceStatus.REVISION)
        self.assertEqual(self.drv.saved_count(code), 1)          # nunca 2
        self.assertEqual(sum(1 for k in self.drv.keys_log if k[1] == "^g"), 1)
        self.assertEqual(self.states()[1:], [InvoiceStatus.PENDIENTE] * 2)

    def test_11_error_al_grabar_sin_grabar_tampoco_reintenta(self):
        code = self.invoices()[0]["escuela_codigo"]
        self.drv.inject("av_on_save_not_saved", code)
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.invoices()[0]["estado"], InvoiceStatus.REVISION)
        self.assertEqual(sum(1 for k in self.drv.keys_log if k[1] == "^g"), 1)

    def test_11_reejecutar_no_duplica(self):
        code = self.invoices()[0]["escuela_codigo"]
        self.drv.inject("av_on_save_saved", code)
        self.engine.run(self.day, RunOptions())
        self.engine.run(self.day, RunOptions())    # el usuario vuelve a pulsar Iniciar
        self.assertEqual(self.drv.saved_count(code), 1)
        self.assertEqual(self.invoices()[0]["estado"], InvoiceStatus.REVISION)
        self.assertEqual(self.states()[1:], [InvoiceStatus.COMPLETADA] * 2)

    def test_error_en_impresion_no_regraba(self):
        self.drv.inject("av_on_print")
        self.engine.run(self.day, RunOptions())
        inv = self.invoices()[0]
        # F9 aún no había abierto el diálogo: se reintenta solo la impresión.
        self.assertEqual(inv["estado"], InvoiceStatus.COMPLETADA)
        self.assertEqual(sum(1 for k in self.drv.keys_log if k[1] == "^g"), 3)
        self.assertEqual(len(self.drv.saved), 3)


class TestImpresion(Base):
    def test_12_no_imprime_antes_de_grabar(self):
        self.drv.inject("save_ignored")          # Ctrl+G no hace nada
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.invoices()[0]["estado"], InvoiceStatus.REVISION)
        self.assertEqual(self.drv.printed, [])
        self.assertEqual(self.drv.print_without_preview, 0)
        self.assertNotIn(("main", "{F9}"), self.drv.keys_log)


class TestPausa(Base):
    n = 4

    def test_13_pausar_y_reanudar(self):
        done = []

        def hook(inv):
            if inv["estado"] == InvoiceStatus.COMPLETADA:
                done.append(inv["id"])
                if len(done) == 1:
                    self.engine.pause()

        self.ui.on_invoice_hook = hook
        t, _ = run_in_thread(self.engine, self.day)
        deadline = time.time() + 5
        while self.engine.sm.state != State.PAUSED and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.engine.sm.state, State.PAUSED)
        time.sleep(0.2)
        self.assertEqual(len(self.drv.saved), 1)     # nada avanza en pausa
        self.assertEqual(self.ctx.days.get_day(self.day)["estado"], "PAUSADA")
        self.engine.resume()
        t.join(10)
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] * 4)
        self.assertEqual(len(self.drv.saved), 4)

    def test_detener(self):
        def hook(inv):
            if inv["estado"] == InvoiceStatus.COMPLETADA:
                self.engine.stop()

        self.ui.on_invoice_hook = hook
        self.engine.run(self.day, RunOptions())
        self.assertEqual(self.states(), [InvoiceStatus.COMPLETADA] + [InvoiceStatus.PENDIENTE] * 3)
        self.assertEqual(self.ctx.days.get_day(self.day)["estado"], "DETENIDA")


if __name__ == "__main__":
    unittest.main()
