"""Jornadas de facturación y estado de cada factura."""
from __future__ import annotations

import json

from database import Database, now_iso


class InvoiceStatus:
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    GUARDADA = "GUARDADA"          # grabada; la impresión requiere revisión
    COMPLETADA = "COMPLETADA"
    ERROR = "ERROR"                # se sabe que NO se grabó
    REVISION = "REVISION"          # estado incierto: revisar en SisFaCon
    OMITIDA = "OMITIDA"

    LABELS = {
        "PENDIENTE": "Pendiente", "EN_PROCESO": "En proceso",
        "GUARDADA": "Guardada (revisar impresión)", "COMPLETADA": "Completada",
        "ERROR": "Error (no grabada)", "REVISION": "Necesita revisión",
        "OMITIDA": "Omitida",
    }
    # Estados que indican que la factura PUEDE existir en SisFaCon.
    POSSIBLY_SAVED = ("EN_PROCESO", "GUARDADA", "COMPLETADA", "REVISION")


class PrintStatus:
    PENDIENTE = "PENDIENTE"
    IMPRESA = "IMPRESA"
    NO_SOLICITADA = "NO_SOLICITADA"
    PENDIENTE_VERIFICACION = "PENDIENTE_VERIFICACION"
    ERROR = "ERROR"

    LABELS = {
        "PENDIENTE": "Pendiente", "IMPRESA": "Impresa",
        "NO_SOLICITADA": "No solicitada",
        "PENDIENTE_VERIFICACION": "Impresión pendiente de verificación",
        "ERROR": "Error de impresión",
    }


class DayStatus:
    PREPARADA = "PREPARADA"
    EN_CURSO = "EN_CURSO"
    PAUSADA = "PAUSADA"
    DETENIDA = "DETENIDA"
    COMPLETADA = "COMPLETADA"
    INTERRUMPIDA = "INTERRUMPIDA"


class Mode:
    SIMULADO = "SIMULADO"
    PRUEBA = "PRUEBA"
    AUTOMATICO = "AUTOMATICO"
    LABELS = {"SIMULADO": "Modo simulado", "PRUEBA": "Modo de prueba",
              "AUTOMATICO": "Modo automático"}


class DayManager:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------ jornadas
    def create_day(self, fecha: str, product: dict, schools: list[dict],
                   modo: str, notas: str = "") -> int:
        """Crea la jornada copiando producto y escuelas (instantánea)."""
        if not schools:
            raise ValueError("Seleccione al menos una escuela.")
        codes = [s["codigo"] for s in schools]
        if len(set(codes)) != len(codes):
            raise ValueError("La lista contiene escuelas repetidas.")
        ts = now_iso()
        from product_manager import ProductManager
        with self.db.transaction():
            day_id = self.db._conn.execute(
                "INSERT INTO jornadas(fecha, producto_id, producto_nombre, "
                "producto_codigo, producto_texto_verificacion, modo, estado, creada, notas) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (fecha, product.get("id"), product["nombre"], str(product["codigo"]),
                 ProductManager.verification_text(product), modo,
                 DayStatus.PREPARADA, ts, notas)).lastrowid
            for orden, s in enumerate(schools, start=1):
                self.db._conn.execute(
                    "INSERT INTO facturas(jornada_id, orden, escuela_id, escuela_codigo, "
                    "escuela_nombre, estado, estado_impresion, actualizado) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (day_id, orden, s.get("id"), str(s["codigo"]), s["nombre"],
                     InvoiceStatus.PENDIENTE, PrintStatus.PENDIENTE, ts))
        return day_id

    def get_day(self, day_id: int) -> dict | None:
        return self.db.query_one("SELECT * FROM jornadas WHERE id = ?", (day_id,))

    def list_days(self, limit: int = 200) -> list[dict]:
        return self.db.query("SELECT * FROM jornadas ORDER BY id DESC LIMIT ?", (limit,))

    def latest_day(self) -> dict | None:
        return self.db.query_one("SELECT * FROM jornadas ORDER BY id DESC LIMIT 1")

    def set_day_status(self, day_id: int, estado: str) -> None:
        extra = ""
        if estado == DayStatus.EN_CURSO:
            extra = ", iniciada = COALESCE(iniciada, ?)"
        elif estado in (DayStatus.COMPLETADA, DayStatus.DETENIDA):
            extra = ", finalizada = ?"
        params = [estado] + ([now_iso()] if extra else []) + [day_id]
        self.db.execute(f"UPDATE jornadas SET estado = ?{extra} WHERE id = ?", params)

    # ------------------------------------------------------------ facturas
    def invoices(self, day_id: int) -> list[dict]:
        return self.db.query(
            "SELECT * FROM facturas WHERE jornada_id = ? ORDER BY orden", (day_id,))

    def invoice(self, invoice_id: int) -> dict | None:
        return self.db.query_one("SELECT * FROM facturas WHERE id = ?", (invoice_id,))

    def pending_invoices(self, day_id: int) -> list[dict]:
        return self.db.query(
            "SELECT * FROM facturas WHERE jornada_id = ? AND estado = ? ORDER BY orden",
            (day_id, InvoiceStatus.PENDIENTE))

    def range_ids(self, day_id: int, desde_orden: int, hasta_orden: int) -> list[int]:
        """Ids de las facturas con número de orden entre «desde» y «hasta»
        (ambos incluidos; el orden de los extremos no importa)."""
        lo, hi = sorted((int(desde_orden), int(hasta_orden)))
        rows = self.db.query(
            "SELECT id FROM facturas WHERE jornada_id = ? AND orden BETWEEN ? AND ? "
            "ORDER BY orden", (day_id, lo, hi))
        return [r["id"] for r in rows]

    def update_invoice(self, invoice_id: int, **fields) -> dict:
        fields["actualizado"] = now_iso()
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE facturas SET {sets} WHERE id = ?",
                        list(fields.values()) + [invoice_id])
        return self.invoice(invoice_id)

    def counts(self, day_id: int) -> dict:
        rows = self.db.query(
            "SELECT estado, estado_impresion FROM facturas WHERE jornada_id = ?", (day_id,))
        c = {"total": len(rows), "completadas": 0, "pendientes": 0,
             "errores": 0, "revision": 0, "omitidas": 0, "en_proceso": 0}
        for r in rows:
            e = r["estado"]
            if e == InvoiceStatus.COMPLETADA:
                c["completadas"] += 1
            elif e == InvoiceStatus.PENDIENTE:
                c["pendientes"] += 1
            elif e == InvoiceStatus.ERROR:
                c["errores"] += 1
            elif e in (InvoiceStatus.REVISION, InvoiceStatus.GUARDADA):
                c["revision"] += 1
            elif e == InvoiceStatus.OMITIDA:
                c["omitidas"] += 1
            elif e == InvoiceStatus.EN_PROCESO:
                c["en_proceso"] += 1
        c["procesadas"] = c["total"] - c["pendientes"] - c["en_proceso"]
        return c

    # ------------------------------------------------------ duplicados
    def schools_already_processed(self, fecha: str, school_codes: list[str],
                                  exclude_day: int | None = None) -> list[dict]:
        """Facturas reales (no simuladas) de la misma fecha que pueden existir."""
        if not school_codes:
            return []
        marks = ",".join("?" for _ in school_codes)
        status_marks = ",".join("?" for _ in InvoiceStatus.POSSIBLY_SAVED)
        sql = (f"SELECT f.*, j.fecha, j.modo FROM facturas f JOIN jornadas j "
               f"ON j.id = f.jornada_id WHERE j.fecha = ? AND j.modo != 'SIMULADO' "
               f"AND f.escuela_codigo IN ({marks}) AND f.estado IN ({status_marks})")
        params = [fecha, *school_codes, *InvoiceStatus.POSSIBLY_SAVED]
        if exclude_day:
            sql += " AND j.id != ?"
            params.append(exclude_day)
        return self.db.query(sql, params)

    # ------------------------------------------------ jornadas interrumpidas
    def find_interrupted(self) -> list[dict]:
        """Jornadas que quedaron en curso/pausadas (cierre inesperado)."""
        return self.db.query(
            "SELECT * FROM jornadas WHERE estado IN (?, ?) ORDER BY id",
            (DayStatus.EN_CURSO, DayStatus.PAUSADA))

    def mark_interrupted(self, day_id: int) -> list[dict]:
        """Marca la jornada como interrumpida.

        Las facturas que estaban EN_PROCESO pasan a REVISION: nunca se
        reanudan automáticamente porque su estado real es desconocido.
        Devuelve las facturas afectadas.
        """
        affected = self.db.query(
            "SELECT * FROM facturas WHERE jornada_id = ? AND estado = ?",
            (day_id, InvoiceStatus.EN_PROCESO))
        for f in affected:
            if f["guardado_intentado"]:
                msg = ("El programa se cerró después de enviar Ctrl+G. "
                       "Compruebe en SisFaCon si el conduce existe.")
            else:
                msg = ("El programa se cerró durante la preparación (sin grabar). "
                       "Revise el formulario de SisFaCon antes de reintentar.")
            self.update_invoice(f["id"], estado=InvoiceStatus.REVISION, mensaje=msg)
        self.set_day_status(day_id, DayStatus.INTERRUMPIDA)
        return affected

    # ------------------------------------------------- acciones manuales
    def reset_to_pending(self, invoice_id: int) -> None:
        """El usuario confirmó en SisFaCon que la factura NO existe."""
        self.update_invoice(invoice_id, estado=InvoiceStatus.PENDIENTE,
                            estado_impresion=PrintStatus.PENDIENTE,
                            guardado_intentado=0, intentos_recuperacion=0,
                            etapa="IDLE", mensaje="Restablecida manualmente a pendiente.")

    def reset_errors(self, day_id: int) -> int:
        """Vuelve a PENDIENTE las facturas en ERROR (se sabe que no se grabaron:
        el error ocurrió antes de pulsar Ctrl+G). Las de REVISION no se tocan."""
        rows = self.db.query("SELECT id FROM facturas WHERE jornada_id = ? AND estado = ? "
                             "AND guardado_intentado = 0", (day_id, InvoiceStatus.ERROR))
        for r in rows:
            self.update_invoice(r["id"], estado=InvoiceStatus.PENDIENTE, etapa="IDLE",
                                intentos_recuperacion=0,
                                mensaje="Reintento tras error sin grabar.")
        return len(rows)

    def mark_completed_manually(self, invoice_id: int, printed: bool) -> None:
        self.update_invoice(invoice_id, estado=InvoiceStatus.COMPLETADA,
                            estado_impresion=PrintStatus.IMPRESA if printed
                            else PrintStatus.NO_SOLICITADA,
                            completado_en=now_iso(),
                            mensaje="Marcada como completada por el usuario.")

    def skip(self, invoice_id: int) -> None:
        self.update_invoice(invoice_id, estado=InvoiceStatus.OMITIDA,
                            mensaje="Omitida por el usuario.")

    # ---------------------------------------- configuraciones frecuentes
    def save_preset(self, nombre: str, producto_id: int | None, school_ids: list[int]) -> None:
        self.db.execute(
            "INSERT INTO configuraciones_frecuentes(nombre, producto_id, escuelas_ids, creada) "
            "VALUES(?,?,?,?) ON CONFLICT(nombre) DO UPDATE SET producto_id = excluded.producto_id, "
            "escuelas_ids = excluded.escuelas_ids",
            (nombre, producto_id, json.dumps(school_ids), now_iso()))

    def list_presets(self) -> list[dict]:
        rows = self.db.query("SELECT * FROM configuraciones_frecuentes ORDER BY nombre")
        for r in rows:
            r["escuelas_ids"] = json.loads(r["escuelas_ids"] or "[]")
        return rows

    def delete_preset(self, preset_id: int) -> None:
        self.db.execute("DELETE FROM configuraciones_frecuentes WHERE id = ?", (preset_id,))
