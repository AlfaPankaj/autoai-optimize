"""Schema.org Product JSON-LD builder.

Google's Product rich results require `name` plus an `offers` containing a
`price`. Without a price we can't build a valid offer, so we decline — but we
keep a graceful path: if only the name is present we still emit a minimal
Product node (name-only is valid Schema.org, just without a price snippet).
"""

from __future__ import annotations

from typing import Any

from src.autoai_optimize.schema.base import LD_CONTEXT, LD_TYPE_KEY, SchemaBuilder, _clean


class ProductBuilder(SchemaBuilder):
    handles = "Product"

    @staticmethod
    def required_fields() -> tuple[str, ...]:
        return ("name",)

    def build(self, data: dict[str, Any]) -> dict[str, Any] | None:
        if not data.get("name"):
            return None

        node: dict[str, Any] = {
            "@context": LD_CONTEXT,
            LD_TYPE_KEY: "Product",
            "name": data["name"],
        }
        if data.get("description"):
            node["description"] = data["description"]
        if data.get("image"):
            node["image"] = data["image"]
        if data.get("url"):
            node["url"] = data["url"]

        price = data.get("price")
        if price:
            currency = data.get("currency", "USD")
            node["offers"] = {
                "@type": "Offer",
                "price": price,
                "priceCurrency": currency,
            }
            if data.get("availability"):
                node["offers"]["availability"] = data["availability"]

        return _clean(node)
