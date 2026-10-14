"""Base de datos SQLite local del macro.

Solo guarda datos del propio AutoFacturador. Nunca se conecta a la base de
datos interna de SisFaCon Express.

La conexión es compartida entre el hilo de la interfaz y el hilo de la
automatización; todas las operaciones pasan por un candado.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS escuelas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo      TEXT NOT NULL,
    nombre      TEXT NOT NULL,
    activo      INTEGER NOT NULL DEFAULT 1,
    notas       TEXT NOT NULL DEFAULT '',
    orden       INTEGER NOT NULL DEFAULT 0,
    cantidad    INTEGER NOT NULL DEFAULT 0,
    eliminado   INTEGER NOT NULL DEFAULT 0,
    creado      TEXT NOT NULL,
    actualizado TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_escuelas_codigo_vigente
    ON escuelas(codigo) WHERE eliminado = 0;

CREATE TABLE IF NOT EXISTS productos (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre             TEXT NOT NULL,
    codigo             TEXT NOT NULL,
    texto_verificacion TEXT NOT NULL DEFAULT '',
    descripcion        TEXT NOT NULL DEFAULT '',
    activo             INTEGER NOT NULL DEFAULT 1,
    eliminado          INTEGER NOT NULL DEFAULT 0,
    creado             TEXT NOT NULL,
    actualizado        TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_productos_codigo_vigente
    ON productos(codigo) WHERE eliminado = 0;

-- Una jornada guarda una COPIA del producto elegido: cambiar el catálogo
-- después de iniciarla no altera las facturas en proceso.
CREATE TABLE IF NOT EXISTS jornadas (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha                       TEXT NOT NULL,
    producto_id                 INTEGER,
    producto_nombre             TEXT NOT NULL,
    producto_codigo             TEXT NOT NULL,
    producto_texto_verificacion TEXT NOT NULL DEFAULT '',
    modo                        TEXT NOT NULL,
    estado                      TEXT NOT NULL,
    creada                      TEXT NOT NULL,
    iniciada                    TEXT,
    finalizada                  TEXT,
    notas                       TEXT NOT NULL DEFAULT ''
);

-- Una fila por escuela de la jornada. Nombre y código se copian para que
-- el historial sobreviva a la edición o eliminación de la escuela.
CREATE TABLE IF NOT EXISTS facturas (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada_id             INTEGER NOT NULL REFERENCES jornadas(id),
    orden                  INTEGER NOT NULL,
    escuela_id             INTEGER,
    escuela_codigo         TEXT NOT NULL,
    escuela_nombre         TEXT NOT NULL,
    cantidad               INTEGER NOT NULL DEFAULT 0,
    estado                 TEXT NOT NULL,
    estado_impresion       TEXT NOT NULL,
    etapa                  TEXT NOT NULL DEFAULT 'IDLE',
    intentos_recuperacion  INTEGER NOT NULL DEFAULT 0,
    guardado_intentado     INTEGER NOT NULL DEFAULT 0,
    conduce_antes          TEXT NOT NULL DEFAULT '',
    conduce_despues        TEXT NOT NULL DEFAULT '',
    mensaje                TEXT NOT NULL DEFAULT '',
    iniciado_en            TEXT,
    guardado_en            TEXT,
    completado_en          TEXT,
    actualizado            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_facturas_jornada ON facturas(jornada_id);

CREATE TABLE IF NOT EXISTS eventos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora      TEXT NOT NULL,
    nivel           TEXT NOT NULL,
    tipo            TEXT NOT NULL,
    mensaje         TEXT NOT NULL,
    jornada_id      INTEGER,
    factura_id      INTEGER,
    escuela_codigo  TEXT NOT NULL DEFAULT '',
    escuela_nombre  TEXT NOT NULL DEFAULT '',
    producto_codigo TEXT NOT NULL DEFAULT '',
    producto_nombre TEXT NOT NULL DEFAULT '',
    estado          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_eventos_fecha ON eventos(fecha_hora);

CREATE TABLE IF NOT EXISTS configuraciones_frecuentes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       TEXT NOT NULL UNIQUE,
    producto_id  INTEGER,
    escuelas_ids TEXT NOT NULL DEFAULT '[]',
    creada       TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    """Envoltorio fino y seguro entre hilos sobre sqlite3."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False,
                                     isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            if self.path != ":memory:":
                self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(clave, valor) VALUES('schema', ?)",
                (str(SCHEMA_VERSION),))

    def _migrate(self) -> None:
        """Añade columnas nuevas a bases de datos creadas por versiones anteriores."""
        for table, column in (("escuelas", "orden"), ("escuelas", "cantidad"),
                              ("facturas", "cantidad")):
            cols = {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} "
                                   "INTEGER NOT NULL DEFAULT 0")

    # ------------------------------------------------------------------
    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Ejecuta una sentencia y devuelve el último id insertado."""
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return cur.lastrowid

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, [tuple(p) for p in seq])

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def transaction(self):
        """Uso: ``with db.transaction(): ...``"""
        return _Transaction(self)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class _Transaction:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self):
        self.db._lock.acquire()
        self.db._conn.execute("BEGIN")
        return self.db

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.db._conn.execute("COMMIT")
            else:
                self.db._conn.execute("ROLLBACK")
        finally:
            self.db._lock.release()
        return False
