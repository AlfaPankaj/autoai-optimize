from __future__ import annotations

from bs4 import BeautifulSoup

from src.autoai_optimize.analyze.extractors import _extract_price


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_us_format():
    html = '<p class="price">$29.99</p>'
    assert _extract_price(_soup(html)) == '29.99'


def test_eu_format():
    html = '<p class="price">€1.234,56</p>'
    assert _extract_price(_soup(html)) == '1234.56'


def test_inr_format():
    html = '<p class="price">₹ 1,234.56</p>'
    assert _extract_price(_soup(html)) == '1234.56'


def test_code_suffix():
    html = '<p>1.234,56 EUR</p>'
    assert _extract_price(_soup(html)) == '1234.56'


def test_plain_integer_with_code():
    html = '<p>1000 INR</p>'
    assert _extract_price(_soup(html)) == '1000'
