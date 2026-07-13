"""Tests for the heuristic page-type classifier."""

from __future__ import annotations

from bs4 import BeautifulSoup

from autoai_optimize.analyze.classifier import PageType, classify


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class TestArticleClassification:
    def test_blog_url_pattern(self):
        c = classify("/blog/my-post", _soup("<html><body><h1>Hi</h1></body></html>"))
        assert c.page_type == PageType.ARTICLE
        assert c.confidence >= 0.4

    def test_post_url_pattern(self):
        c = classify("/post/123", _soup("<html><body></body></html>"))
        assert c.page_type == PageType.ARTICLE

    def test_article_url_pattern(self):
        c = classify("/article/ai-future", _soup("<html><body></body></html>"))
        assert c.page_type == PageType.ARTICLE

    def test_article_tag_boost(self):
        c = classify("/", _soup("<html><body><article><h1>Hi</h1></article></body></html>"))
        assert c.page_type == PageType.ARTICLE
        assert c.confidence >= 0.25

    def test_og_type_article_strong(self):
        html = '<meta property="og:type" content="article">'
        c = classify("/", _soup(html))
        assert c.page_type == PageType.ARTICLE
        assert c.confidence >= 0.3

    def test_article_beats_product(self):
        html = '<meta property="og:type" content="article">'
        c = classify("/blog/post", _soup(html))
        assert c.page_type == PageType.ARTICLE


class TestProductClassification:
    def test_product_url_pattern(self):
        c = classify("/product/widget", _soup("<html><body><h1>Hi</h1></body></html>"))
        assert c.page_type == PageType.PRODUCT

    def test_shop_url_pattern(self):
        c = classify("/shop/item-1", _soup("<html><body></body></html>"))
        assert c.page_type == PageType.PRODUCT

    def test_price_text_signal(self):
        html = '<html><body><p class="price">$29.99</p></body></html>'
        c = classify("/", _soup(html))
        assert c.page_type == PageType.PRODUCT
        assert c.confidence >= 0.25

    def test_og_type_product_strong(self):
        html = '<meta property="og:type" content="product">'
        c = classify("/", _soup(html))
        assert c.page_type == PageType.PRODUCT

    def test_product_beats_article(self):
        html = '<meta property="og:type" content="product"><p>$49.99</p>'
        c = classify("/product/x", _soup(html))
        assert c.page_type == PageType.PRODUCT


class TestUnknownClassification:
    def test_no_signals(self):
        c = classify("/", _soup("<html><body><h1>Welcome</h1></body></html>"))
        assert c.page_type == PageType.UNKNOWN
        assert c.confidence == 0.0

    def test_empty_html(self):
        c = classify("/", _soup(""))
        assert c.page_type == PageType.UNKNOWN
