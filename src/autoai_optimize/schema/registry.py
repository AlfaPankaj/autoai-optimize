"""PageType → SchemaBuilder registry."""

from __future__ import annotations

from typing import Any

from autoai_optimize.analyze.classifier import PageType
from autoai_optimize.schema.article import ArticleBuilder
from autoai_optimize.schema.base import SchemaBuilder
from autoai_optimize.schema.product import ProductBuilder
from autoai_optimize.schema.profile import ProfileBuilder

_BUILDERS: dict[PageType, SchemaBuilder] = {
    PageType.ARTICLE: ArticleBuilder(),
    PageType.PRODUCT: ProductBuilder(),
    PageType.PROFILE: ProfileBuilder(),
}


def has_required_fields(page_type: PageType, data: dict[str, Any]) -> bool:
    """True if `data` contains all required fields for this page type."""
    builder = _BUILDERS.get(page_type)
    if builder is None:
        return False
    return all(data.get(f) for f in builder.required_fields())


def build_for(page_type: PageType, data: dict[str, Any]) -> dict[str, Any] | None:
    """Build the JSON-LD node for `page_type`, or None if data is insufficient."""
    builder = _BUILDERS.get(page_type)
    if builder is None:
        return None
    return builder.build(data)
