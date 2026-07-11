from __future__ import annotations

from typing import Any

from src.autoai_optimize.schema.base import LD_CONTEXT, LD_TYPE_KEY, SchemaBuilder, _clean


class ProfileBuilder(SchemaBuilder):
    handles = "Person"

    @staticmethod
    def required_fields() -> tuple[str, ...]:
        return ("name",)

    def build(self, data: dict[str, Any]) -> dict[str, Any] | None:
        if not data.get("name"):
            return None

        node: dict[str, Any] = {
            "@context": LD_CONTEXT,
            LD_TYPE_KEY: "Person",
            "name": data["name"],
        }
        if data.get("jobTitle"):
            node["jobTitle"] = data["jobTitle"]
        if data.get("url"):
            node["url"] = data["url"]
        return _clean(node)
