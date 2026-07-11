"""Schema layer: turns extracted entity data into Schema.org JSON-LD dicts."""

from __future__ import annotations

from src.autoai_optimize.schema.article import ArticleBuilder
from src.autoai_optimize.schema.base import SchemaBuilder
from src.autoai_optimize.schema.product import ProductBuilder
from src.autoai_optimize.schema.profile import ProfileBuilder
from src.autoai_optimize.schema.registry import build_for, has_required_fields

__all__ = [
    "ArticleBuilder",
    "ProductBuilder",
    "ProfileBuilder",
    "SchemaBuilder",
    "build_for",
    "has_required_fields",
]
