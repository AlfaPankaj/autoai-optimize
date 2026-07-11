"""Analysis layer: page-type classification, hint parsing, entity extraction."""

from __future__ import annotations

from src.autoai_optimize.analyze.classifier import Classification, PageType, classify
from src.autoai_optimize.analyze.extractors import extract_article, extract_product
from src.autoai_optimize.analyze.hints import PageHint, parse_hints

__all__ = [
    "Classification",
    "PageHint",
    "PageType",
    "classify",
    "extract_article",
    "extract_product",
    "parse_hints",
]
