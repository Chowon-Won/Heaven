"""Gestión de escuelas (centros educativos)."""
from __future__ import annotations

from catalog_base import CatalogManager


class SchoolManager(CatalogManager):
    table = "escuelas"
    entity = "escuela"
    text_fields = ("nombre", "notas")
    required_fields = ("codigo", "nombre")
    int_fields = ("orden", "cantidad")

    def without_quantity(self, schools: list[dict]) -> list[dict]:
        return [s for s in schools if int(s.get("cantidad") or 0) <= 0]

    def _order_by(self) -> str:
        # Orden de ruta primero (0 = sin orden, al final), luego por código.
        return "CASE WHEN orden > 0 THEN 0 ELSE 1 END, orden, codigo"

    def active_ids(self) -> list[int]:
        return [r["id"] for r in self.list(only_active=True)]
