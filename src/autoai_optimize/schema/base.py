"""Schema builder interface and shared helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

# The JSON-LD node type each builder emits (e.g. "Article", "Product").
LD_TYPE_KEY = "@type"

# Top-level JSON-LD context — identical for every node we emit.
LD_CONTEXT = "https://schema.org"


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None/empty, recursively. Keeps JSON-LD tight."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            cleaned = _clean(v)
            if cleaned:
                out[k] = cleaned
        elif isinstance(v, (list, tuple)):
            cleaned_list = [item for item in v if item is not None]
            if cleaned_list:
                out[k] = cleaned_list
        elif v != "":
            out[k] = v
    return out


class SchemaBuilder(ABC):
    """Converts an extracted-entity dict into a Schema.org JSON-LD node dict.

    A builder must validate required fields and return None when the data is
    insufficient to emit a *valid* node. Emitting partial/invalid markup is
    worse than emitting none (Google may flag it).
    """

    #: Which PageType value (str) this builder handles.
    handles: str = ""

    @staticmethod
    @abstractmethod
    def required_fields() -> tuple[str, ...]:
        """Fields that MUST be present (after extraction) to emit this schema."""

    @abstractmethod
    def build(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Return a JSON-LD node dict, or None if required fields are missing."""
