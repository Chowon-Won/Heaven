"""Pruebas 1, 2, 3, 5 y 6: escuelas, productos, ceros iniciales, importación."""
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_ctx

from catalog_base import DuplicateCodeError
from import_export import read_table, write_table


class TestEscuelas(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(0)
        self.sm = self.ctx.schools

    def test_01_crear_editar_eliminar_escuela(self):
        sid = self.sm.add(codigo="02968", nombre="RAMON MARIA PERALTA- LAGUNA GRANDE")
        self.assertEqual(self.sm.get(sid)["nombre"], "RAMON MARIA PERALTA- LAGUNA GRANDE")
        self.sm.update(sid, nombre="RAMON MARIA PERALTA", notas="Ruta norte")
        e = self.sm.get(sid)
        self.assertEqual(e["nombre"], "RAMON MARIA PERALTA")
        self.assertEqual(e["notas"], "Ruta norte")
        self.sm.delete(sid)
        self.assertEqual(self.sm.list(), [])
        borrada = self.sm.get(sid)
        self.assertEqual(borrada["eliminado"], 1)   # borrado lógico
        self.assertEqual(borrada["activo"], 0)

    def test_03_conserva_ceros_iniciales(self):
        sid = self.sm.add(codigo="02968", nombre="X")
        self.assertEqual(self.sm.get(sid)["codigo"], "02968")
        self.assertIsNotNone(self.sm.get_by_code("02968"))
        self.assertIsNone(self.sm.get_by_code("2968"))

    def test_06_codigo_duplicado_rechazado(self):
        self.sm.add(codigo="07836", nombre="PEDRO MIR")
        with self.assertRaises(DuplicateCodeError):
            self.sm.add(codigo="07836", nombre="OTRA")
        # Tras eliminar, el código puede reutilizarse.
        self.sm.delete(self.sm.get_by_code("07836")["id"])
        self.sm.add(codigo="07836", nombre="PEDRO MIR (nueva)")

    def test_busqueda_y_activas(self):
        a = self.sm.add(codigo="02950", nombre="ADOLFO ALEJANDRO MALOON")
        self.sm.add(codigo="02959", nombre="ARROYO HIGUERO")
        self.sm.set_active(a, False)
        self.assertEqual(len(self.sm.list(search="arroyo")), 1)
        self.assertEqual(len(self.sm.list(search="0295")), 2)
        self.assertEqual(len(self.sm.list(only_active=True)), 1)

    def test_05_importar_48_escuelas_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escuelas.csv"
            rows = [[f"0{2900 + i}", f"ESCUELA {i}", "si"] for i in range(48)]
            rows.append(["02900", "REPETIDA", "si"])     # duplicada en el archivo
            write_table(path, ["codigo", "nombre", "activo"], rows)
            report = self.sm.import_rows(read_table(path))
        self.assertEqual(report.agregados, 48)
        self.assertEqual(report.duplicados_en_archivo, ["02900"])
        self.assertEqual(self.sm.count(), 48)
        self.assertEqual(self.sm.get_by_code("02900")["nombre"], "ESCUELA 0")
        # Reimportar no duplica.
        again = self.sm.import_rows([{"codigo": "02900", "nombre": "ESCUELA 0"}])
        self.assertEqual(again.agregados, 0)
        self.assertEqual(self.sm.count(), 48)

    def test_importar_excel_con_formato_de_ceros(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escuelas.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Código", "Nombre"])
            ws.append([2968, "RAMON MARIA PERALTA"])
            ws["A2"].number_format = "00000"
            ws.append(["07836", "PEDRO MIR"])
            wb.save(path)
            report = self.sm.import_rows(read_table(path))
        self.assertEqual(report.agregados, 2)
        self.assertIsNotNone(self.sm.get_by_code("02968"))
        self.assertIsNotNone(self.sm.get_by_code("07836"))


class TestProductos(unittest.TestCase):
    def setUp(self):
        self.ctx = make_ctx(0)
        self.pm = self.ctx.products

    def test_ejemplos_iniciales_editables(self):
        codes = {p["codigo"]: p["nombre"] for p in self.pm.list()}
        self.assertEqual(codes, {"1000": "Pan", "1005": "Pan de zanahoria"})

    def test_02_crear_editar_eliminar_producto(self):
        pid = self.pm.add(codigo="1010", nombre="Galletas", texto_verificacion="GALLETA DULCE")
        self.pm.update(pid, nombre="Galleta integral", codigo="1011")
        p = self.pm.get(pid)
        self.assertEqual((p["nombre"], p["codigo"]), ("Galleta integral", "1011"))
        self.pm.set_active(pid, False)
        self.assertNotIn(pid, [x["id"] for x in self.pm.list(only_active=True)])
        self.pm.delete(pid)
        self.assertIsNone(self.pm.get_by_code("1011"))
        with self.assertRaises(DuplicateCodeError):
            self.pm.add(codigo="1000", nombre="Pan duplicado")

    def test_03_codigo_producto_con_cero(self):
        pid = self.pm.add(codigo="0100", nombre="Leche")
        self.assertEqual(self.pm.get(pid)["codigo"], "0100")


if __name__ == "__main__":
    unittest.main()
