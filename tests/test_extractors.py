"""Tests for entity extractors."""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.autoai_optimize.analyze.extractors import extract_article, extract_product
from src.autoai_optimize.analyze.hints import PageHint


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_extract_article_full():
    html = """
    <html><head>
        <meta property="og:title" content="My Post">
        <meta property="og:description" content="A description here.">
        <meta property="og:image" content="https://example.com/img.png">
        <meta property="article:author" content="Jane">
        <meta property="article:published_time" content="2026-06-15T10:00:00Z">
    </head><body></body></html>
    """
    data = extract_article(_soup(html), "https://example.com/blog/post", PageHint(None, {}))
    assert data["headline"] == "My Post"
    assert data["description"] == "A description here."
    assert data["image"] == "https://example.com/img.png"
    assert data["author"] == "Jane"
    assert data["datePublished"] == "2026-06-15T10:00:00Z"
    assert data["url"] == "https://example.com/blog/post"


def test_extract_article_fallback_h1():
    html = '<html><body><h1>Fallback Title</h1></body></html>'
    data = extract_article(_soup(html), "/post/1", PageHint(None, {}))
    assert data["headline"] == "Fallback Title"


def test_extract_article_hint_override():
    html = '<html><head><meta property="og:title" content="Original"></head><body></body></html>'
    data = extract_article(_soup(html), "/blog/x", PageHint(None, {"headline": "Override"}))
    assert data["headline"] == "Override"


def test_extract_product_full():
    html = """
    <html><head>
        <meta property="og:image" content="https://example.com/prod.png">
    </head><body>
        <h1>Super Widget</h1>
        <p class="description">Amazing widget.</p>
        <p class="price">$49.99</p>
    </body></html>
    """
    data = extract_product(_soup(html), "https://shop.com/product/x", PageHint(None, {}))
    assert data["name"] == "Super Widget"
    assert data["price"] == "49.99"


def test_extract_product_no_price():
    html = '<html><body><h1>No Price Item</h1></body></html>'
    data = extract_product(_soup(html), "/item/1", PageHint(None, {}))
    assert data["name"] == "No Price Item"
    assert "price" not in data


def test_extract_product_hint_override():
    html = '<html><body><h1>Widget</h1><p>$10</p></body></html>'
    data = extract_product(_soup(html), "/p/1", PageHint(None, {"price": "99.99", "currency": "EUR"}))
    assert data["price"] == "99.99"
