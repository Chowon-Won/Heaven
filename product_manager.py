"""Gestión del catálogo de productos.

``texto_verificacion`` es el texto que SisFaCon muestra en la columna
Descripción al introducir el código (por ejemplo «PAN DE ZANAHORIA»). Si se
deja vacío se usa el nombre del producto.
"""
from __future__ import annotations

from catalog_base import CatalogManager

EXAMPLE_PRODUCTS = [
    {"nombre": "Pan", "codigo": "1000"},
    {"nombre": "Pan de zanahoria", "codigo": "1005"},
]


class ProductManager(CatalogManager):
    table = "productos"
    entity = "producto"
    text_fields = ("nombre", "texto_verificacion", "descripcion")
    required_fields = ("codigo", "nombre")

    def seed_examples_if_empty(self) -> None:
        """Carga los ejemplos editables solo la primera vez."""
        total = self.db.query_one("SELECT COUNT(*) n FROM productos")["n"]
        if total == 0:
            for p in EXAMPLE_PRODUCTS:
                self.add(**p)

    @staticmethod
    def verification_text(product: dict) -> str:
        return (product.get("texto_verificacion") or product.get("nombre") or "").strip()

    @staticmethod
    def label(product: dict) -> str:
        return f"{product['nombre']} — {product['codigo']}"
