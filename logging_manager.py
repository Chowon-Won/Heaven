"""Registro de operaciones: base de datos + archivo de texto rotativo.

No se guardan contraseñas ni datos sensibles; solo códigos, nombres de
escuela/producto, estados y mensajes técnicos.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from database import Database, now_iso
from import_export import write_table

# Tipos de evento (texto mostrado en el historial).
EV = {
    "JORNADA_CREADA": "Jornada creada",
    "JORNADA_INICIADA": "Jornada iniciada",
    "JORNADA_PAUSADA": "Jornada pausada",
    "JORNADA_REANUDADA": "Jornada reanudada",
    "JORNADA_DETENIDA": "Jornada detenida",
    "JORNADA_COMPLETADA": "Jornada completada",
    "JORNADA_INTERRUMPIDA": "Jornada interrumpida detectada",
    "PRODUCTO_SELECCIONADO": "Producto seleccionado",
    "ESCUELA_SELECCIONADA": "Escuela seleccionada",
    "ESCUELA_INCORRECTA": "Escuela incorrecta",
    "PRODUCTO_INTRODUCIDO": "Producto introducido",
    "PRODUCTO_INCORRECTO": "Producto incorrecto",
    "GUARDADO_ENVIADO": "Grabación enviada (Ctrl+G)",
    "FACTURA_GUARDADA": "Factura guardada",
    "IMPRESION_ENVIADA": "Impresión enviada",
    "IMPRESION_COMPLETADA": "Impresión completada",
    "IMPRESION_PENDIENTE": "Impresión pendiente de verificación",
    "FACTURA_COMPLETADA": "Factura completada",
    "ERROR_ACCESO": "Error de acceso detectado",
    "RECUPERACION_INICIADA": "Recuperación iniciada",
    "RECUPERACION_EXITOSA": "Recuperación exitosa",
    "RECUPERACION_FALLIDA": "Recuperación fallida",
    "VENTANA_DESCONOCIDA": "Ventana desconocida",
    "REVISION": "Factura pendiente de revisión",
    "ERROR": "Error",
    "INFO": "Información",
    "ESTADO": "Cambio de estado",
}


class OperationLogger:
    def __init__(self, db: Database, log_dir: str | Path | None = None):
        self.db = db
        self.listeners: list[Callable[[dict], None]] = []
        self._py = logging.getLogger("autofacturador")
        if log_dir and not self._py.handlers:
            handler = RotatingFileHandler(Path(log_dir) / "autofacturador.log",
                                          maxBytes=2_000_000, backupCount=5,
                                          encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s"))
            self._py.addHandler(handler)
            self._py.setLevel(logging.INFO)
        if not self._py.handlers:
            self._py.addHandler(logging.NullHandler())
        self._py.propagate = False

    def log(self, tipo: str, mensaje: str = "", nivel: str = "INFO", *,
            jornada: dict | None = None, factura: dict | None = None,
            estado: str = "") -> dict:
        event = {
            "fecha_hora": now_iso(),
            "nivel": nivel,
            "tipo": tipo,
            "mensaje": mensaje or EV.get(tipo, tipo),
            "jornada_id": (jornada or {}).get("id") or (factura or {}).get("jornada_id"),
            "factura_id": (factura or {}).get("id"),
            "escuela_codigo": (factura or {}).get("escuela_codigo", ""),
            "escuela_nombre": (factura or {}).get("escuela_nombre", ""),
            "producto_codigo": (jornada or {}).get("producto_codigo", ""),
            "producto_nombre": (jornada or {}).get("producto_nombre", ""),
            "estado": estado,
        }
        cols = list(event)
        self.db.execute(
            f"INSERT INTO eventos({', '.join(cols)}) VALUES({', '.join('?' for _ in cols)})",
            list(event.values()))
        self._py.log(logging.ERROR if nivel == "ERROR" else
                     logging.WARNING if nivel == "AVISO" else logging.INFO,
                     "[%s] %s %s %s", tipo, event["escuela_codigo"],
                     event["mensaje"], estado)
        for listener in list(self.listeners):
            try:
                listener(event)
            except Exception:  # un oyente defectuoso no detiene el macro
                pass
        return event

    # ------------------------------------------------------------------
    def search(self, desde: str = "", hasta: str = "", escuela: str = "",
               producto: str = "", estado: str = "", tipo: str = "",
               limit: int = 5000) -> list[dict]:
        sql = "SELECT * FROM eventos WHERE 1 = 1"
        p: list = []
        if desde:
            sql += " AND fecha_hora >= ?"
            p.append(desde)
        if hasta:
            sql += " AND fecha_hora <= ?"
            p.append(hasta + "T23:59:59" if len(hasta) == 10 else hasta)
        if escuela:
            sql += " AND (escuela_codigo LIKE ? OR escuela_nombre LIKE ?)"
            p += [f"%{escuela}%"] * 2
        if producto:
            sql += " AND (producto_codigo LIKE ? OR producto_nombre LIKE ?)"
            p += [f"%{producto}%"] * 2
        if estado:
            sql += " AND (estado = ? OR nivel = ?)"
            p += [estado, estado]
        if tipo:
            sql += " AND tipo = ?"
            p.append(tipo)
        sql += " ORDER BY id DESC LIMIT ?"
        p.append(limit)
        return self.db.query(sql, p)

    EXPORT_COLS = ["fecha_hora", "nivel", "tipo", "mensaje", "jornada_id",
                   "escuela_codigo", "escuela_nombre", "producto_codigo",
                   "producto_nombre", "estado"]

    def export_csv(self, path: str | Path, events: list[dict] | None = None) -> int:
        events = events if events is not None else self.search()
        write_table(path, self.EXPORT_COLS,
                    [[e.get(c, "") for c in self.EXPORT_COLS] for e in events])
        return len(events)
