"""Tests for Schema.org JSON-LD builders."""

from __future__ import annotations

from src.autoai_optimize.analyze.classifier import PageType
from src.autoai_optimize.schema.article import ArticleBuilder
from src.autoai_optimize.schema.product import ProductBuilder
from src.autoai_optimize.schema.registry import build_for, has_required_fields


class TestArticleBuilder:
    def test_full_article(self):
        node = ArticleBuilder().build({
            "headline": "Test",
            "description": "Desc",
            "author": "Jane",
            "datePublished": "2026-07-01",
            "image": "https://example.com/img.png",
            "url": "/blog/test",
        })
        assert node is not None
        assert node["@type"] == "Article"
        assert node["headline"] == "Test"
        assert node["author"]["name"] == "Jane"

    def test_missing_headline_returns_none(self):
        node = ArticleBuilder().build({"description": "only desc"})
        assert node is None

    def test_empty_strings_removed(self):
        node = ArticleBuilder().build({"headline": "Hi", "description": ""})
        assert node is not None
        assert "description" not in node


class TestProductBuilder:
    def test_full_product(self):
        node = ProductBuilder().build({
            "name": "Widget",
            "price": "29.99",
            "currency": "USD",
            "description": "A widget.",
            "url": "/product/widget",
        })
        assert node is not None
        assert node["@type"] == "Product"
        assert node["offers"]["price"] == "29.99"
        assert node["offers"]["priceCurrency"] == "USD"

    def test_product_without_price(self):
        node = ProductBuilder().build({"name": "Nameless"})
        assert node is not None
        assert "offers" not in node

    def test_missing_name_returns_none(self):
        node = ProductBuilder().build({"price": "10"})
        assert node is None


class TestRegistry:
    def test_build_for_article(self):
        node = build_for(PageType.ARTICLE, {"headline": "Test"})
        assert node is not None
        assert node["@type"] == "Article"

    def test_build_for_product(self):
        node = build_for(PageType.PRODUCT, {"name": "X", "price": "5"})
        assert node is not None
        assert node["@type"] == "Product"

    def test_build_for_unknown(self):
        assert build_for(PageType.UNKNOWN, {}) is None

    def test_has_required_fields(self):
        assert has_required_fields(PageType.ARTICLE, {"headline": "X"})
        assert not has_required_fields(PageType.ARTICLE, {"description": "X"})
        assert has_required_fields(PageType.PRODUCT, {"name": "X"})
