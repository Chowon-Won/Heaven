"""Gestión de escuelas (centros educativos)."""
from __future__ import annotations

from catalog_base import CatalogManager


class SchoolManager(CatalogManager):
    table = "escuelas"
    entity = "escuela"
    text_fields = ("nombre", "notas")
    required_fields = ("codigo", "nombre")

    def _order_by(self) -> str:
        return "codigo"

    def active_ids(self) -> list[int]:
        return [r["id"] for r in self.list(only_active=True)]
