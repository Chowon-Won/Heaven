"""Lógica común para catálogos (escuelas y productos).

- Los códigos se tratan SIEMPRE como texto (se conservan los ceros iniciales).
- Eliminar es un borrado lógico: el registro queda marcado como eliminado e
  inactivo, y el historial de facturas conserva sus copias de nombre/código.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from database import Database, now_iso


class CatalogError(ValueError):
    """Error de validación mostrado al usuario."""


class DuplicateCodeError(CatalogError):
    pass


def clean_code(value) -> str:
    """Normaliza un código a texto sin perder ceros iniciales."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    # Excel/CSV a veces exporta "02968.0" o con comillas.
    text = text.strip('"').strip("'").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


@dataclass
class ImportReport:
    agregados: int = 0
    actualizados: int = 0
    omitidos: int = 0
    duplicados_en_archivo: list[str] = field(default_factory=list)
    ya_existentes: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    def resumen(self) -> str:
        partes = [f"Añadidos: {self.agregados}",
                  f"Actualizados: {self.actualizados}",
                  f"Omitidos: {self.omitidos}"]
        if self.duplicados_en_archivo:
            partes.append("Códigos repetidos en el archivo: "
                          + ", ".join(self.duplicados_en_archivo[:20]))
        if self.ya_existentes:
            partes.append("Ya existían (no modificados): "
                          + ", ".join(self.ya_existentes[:20]))
        if self.errores:
            partes.append("Errores:\n- " + "\n- ".join(self.errores[:20]))
        return "\n".join(partes)


class CatalogManager:
    """CRUD genérico. Las subclases definen la tabla y los campos."""

    table: str = ""
    entity: str = "registro"
    # Campos editables además de codigo/activo.
    text_fields: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ("codigo",)
    # Campos numéricos opcionales (p. ej. orden de ruta).
    int_fields: tuple[str, ...] = ()

    def __init__(self, db: Database):
        self.db = db

    # ---------------------------------------------------------- lectura
    def get(self, item_id: int) -> dict | None:
        return self.db.query_one(f"SELECT * FROM {self.table} WHERE id = ?",
                                 (item_id,))

    def get_by_code(self, codigo: str, include_deleted: bool = False) -> dict | None:
        sql = f"SELECT * FROM {self.table} WHERE codigo = ?"
        if not include_deleted:
            sql += " AND eliminado = 0"
        return self.db.query_one(sql, (clean_code(codigo),))

    def list(self, search: str = "", only_active: bool = False,
             include_deleted: bool = False) -> list[dict]:
        sql = f"SELECT * FROM {self.table} WHERE 1 = 1"
        params: list = []
        if not include_deleted:
            sql += " AND eliminado = 0"
        if only_active:
            sql += " AND activo = 1"
        if search.strip():
            like = f"%{search.strip()}%"
            cols = ("codigo",) + tuple(f for f in self.text_fields
                                       if f in ("nombre", "descripcion", "notas"))
            sql += " AND (" + " OR ".join(f"{c} LIKE ?" for c in cols) + ")"
            params += [like] * len(cols)
        sql += " ORDER BY " + self._order_by()
        return self.db.query(sql, params)

    def _order_by(self) -> str:
        return "nombre COLLATE NOCASE"

    def count(self, only_active: bool = False) -> int:
        sql = f"SELECT COUNT(*) AS n FROM {self.table} WHERE eliminado = 0"
        if only_active:
            sql += " AND activo = 1"
        return self.db.query_one(sql)["n"]

    # ---------------------------------------------------------- escritura
    def _validate(self, data: dict, exclude_id: int | None = None) -> dict:
        clean = {"codigo": clean_code(data.get("codigo"))}
        for f in self.text_fields:
            clean[f] = str(data.get(f) or "").strip()
        clean["activo"] = 1 if data.get("activo", True) else 0
        for f in self.int_fields:
            try:
                clean[f] = max(0, int(float(str(data.get(f) or 0).strip() or 0)))
            except ValueError:
                raise CatalogError(f"«{f}» debe ser un número entero.")
        for f in self.required_fields:
            if not clean.get(f):
                raise CatalogError(f"El campo «{f}» es obligatorio.")
        existing = self.get_by_code(clean["codigo"])
        if existing and existing["id"] != exclude_id:
            raise DuplicateCodeError(
                f"Ya existe un {self.entity} con el código {clean['codigo']} "
                f"({existing.get('nombre', '')}).")
        return clean

    def add(self, **data) -> int:
        clean = self._validate(data)
        ts = now_iso()
        cols = list(clean) + ["creado", "actualizado"]
        vals = list(clean.values()) + [ts, ts]
        return self.db.execute(
            f"INSERT INTO {self.table}({', '.join(cols)}) "
            f"VALUES({', '.join('?' for _ in cols)})", vals)

    def update(self, item_id: int, **data) -> None:
        current = self.get(item_id)
        if not current or current["eliminado"]:
            raise CatalogError(f"El {self.entity} no existe o fue eliminado.")
        merged = {**current, **data}
        clean = self._validate(merged, exclude_id=item_id)
        sets = ", ".join(f"{c} = ?" for c in clean)
        self.db.execute(
            f"UPDATE {self.table} SET {sets}, actualizado = ? WHERE id = ?",
            list(clean.values()) + [now_iso(), item_id])

    def set_active(self, item_id: int, active: bool) -> None:
        self.db.execute(
            f"UPDATE {self.table} SET activo = ?, actualizado = ? WHERE id = ?",
            (1 if active else 0, now_iso(), item_id))

    def delete(self, item_id: int) -> None:
        """Borrado lógico: el historial de facturas no se toca."""
        self.db.execute(
            f"UPDATE {self.table} SET eliminado = 1, activo = 0, actualizado = ? "
            f"WHERE id = ?", (now_iso(), item_id))

    def find_duplicate_codes(self) -> list[str]:
        rows = self.db.query(
            f"SELECT codigo, COUNT(*) n FROM {self.table} WHERE eliminado = 0 "
            f"GROUP BY codigo HAVING n > 1")
        return [r["codigo"] for r in rows]

    # ---------------------------------------------------------- importación
    def import_rows(self, rows: list[dict], update_existing: bool = False) -> ImportReport:
        """Importa filas ya leídas (dict con claves en minúscula)."""
        report = ImportReport()
        seen: set[str] = set()
        for n, raw in enumerate(rows, start=2):  # fila 1 = encabezado
            row = {k: v for k, v in raw.items()}
            code = clean_code(row.get("codigo"))
            if not code:
                if any(str(v or "").strip() for v in row.values()):
                    report.errores.append(f"Fila {n}: falta el código.")
                continue
            if code in seen:
                report.duplicados_en_archivo.append(code)
                report.omitidos += 1
                continue
            seen.add(code)
            row["codigo"] = code
            row["activo"] = _parse_bool(row.get("activo", True))
            try:
                existing = self.get_by_code(code)
                if existing:
                    if update_existing:
                        self.update(existing["id"], **{k: v for k, v in row.items()
                                                       if k in self.text_fields
                                                       or k in self.int_fields
                                                       or k in ("codigo", "activo")})
                        report.actualizados += 1
                    else:
                        report.ya_existentes.append(code)
                        report.omitidos += 1
                    continue
                self.add(**row)
                report.agregados += 1
            except CatalogError as exc:
                report.errores.append(f"Fila {n} ({code}): {exc}")
        return report


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    if text in ("", "1", "si", "sí", "s", "true", "activo", "activa", "x", "yes"):
        return True
    return text not in ("0", "no", "n", "false", "inactivo", "inactiva")
