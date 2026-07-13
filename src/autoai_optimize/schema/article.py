"""Schema.org Article JSON-LD builder.

Google's Rich Results for Articles requires at least `headline`. Author,
datePublished, and image unlock richer snippets. We emit what we can find and
decline (return None) when headline is missing.
"""

from __future__ import annotations

from typing import Any

from autoai_optimize.schema.base import LD_CONTEXT, LD_TYPE_KEY, SchemaBuilder, _clean


class ArticleBuilder(SchemaBuilder):
    handles = "Article"

    @staticmethod
    def required_fields() -> tuple[str, ...]:
        return ("headline",)

    def build(self, data: dict[str, Any]) -> dict[str, Any] | None:
        if not data.get("headline"):
            return None

        node: dict[str, Any] = {
            "@context": LD_CONTEXT,
            LD_TYPE_KEY: "Article",
            "headline": data["headline"],
        }
        if data.get("description"):
            node["description"] = data["description"]
        if data.get("image"):
            node["image"] = data["image"]
        if data.get("url"):
            node["url"] = data["url"]
        if data.get("datePublished"):
            node["datePublished"] = data["datePublished"]
        if data.get("author"):
            node["author"] = {"@type": "Person", "name": data["author"]}
        return _clean(node)
