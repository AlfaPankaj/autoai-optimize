"""Analysis layer: page-type classification, hint parsing, entity extraction."""

from __future__ import annotations

from autoai_optimize.analyze.classifier import Classification, PageType, classify
from autoai_optimize.analyze.extractors import extract_article, extract_product
from autoai_optimize.analyze.hints import PageHint, parse_hints

__all__ = [
    "Classification",
    "PageHint",
    "PageType",
    "classify",
    "extract_article",
    "extract_product",
    "parse_hints",
]
