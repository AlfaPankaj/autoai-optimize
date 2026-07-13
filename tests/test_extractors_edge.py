"""Edge-case tests for extractors — targets uncovered branches.

Covers the locale price-parser branches (EUR decimal separator, currency-code
suffix, generic decimal fallback), the itemprop price path, and the profile
extractor, which were previously untested.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from autoai_optimize.analyze.extractors import (
    _extract_price,
    extract_article,
    extract_product,
    extract_profile,
)
from autoai_optimize.analyze.hints import PageHint


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# Price parsing: locale variants (extractors.py ~179-226)
# ---------------------------------------------------------------------------

class TestPriceLocaleParsing:
    def test_usd_symbol_prefix(self):
        soup = _soup('<html><body><span>$1,299.99</span></body></html>')
        assert _extract_price(soup) == "1299.99"

    def test_eur_decimal_comma(self):
        # EU format: '1.234,56' -> decimal comma, dot is thousands sep.
        soup = _soup('<html><body><span>1.234,56 €</span></body></html>')
        assert _extract_price(soup) == "1234.56"

    def test_inr_currency_symbol(self):
        soup = _soup('<html><body><span>₹2,500</span></body></html>')
        assert _extract_price(soup) == "2500"

    def test_gbp_symbol_suffix(self):
        soup = _soup('<html><body><span>49.99£</span></body></html>')
        assert _extract_price(soup) == "49.99"

    def test_currency_code_suffix_usd(self):
        # '199.99 USD' -> code pattern path.
        soup = _soup('<html><body><span>199.99 USD</span></body></html>')
        assert _extract_price(soup) == "199.99"

    def test_currency_code_prefix_eur(self):
        soup = _soup('<html><body><span>EUR 1.234,56</span></body></html>')
        assert _extract_price(soup) == "1234.56"

    def test_itemprop_price_via_content(self):
        soup = _soup('<html><body><span itemprop="price" content="42.50">$42.50</span></body></html>')
        assert _extract_price(soup) == "42.50"

    def test_itemprop_price_via_text(self):
        soup = _soup('<html><body><span itemprop="price">77.77</span></body></html>')
        assert _extract_price(soup) == "77.77"

    def test_no_price_returns_none(self):
        soup = _soup('<html><body><p>no prices here at all</p></body></html>')
        assert _extract_price(soup) is None

    def test_comma_thousands_without_decimal(self):
        # '1,999' with no decimal -> thousands separator, not decimal comma.
        soup = _soup('<html><body><span>$1,999</span></body></html>')
        assert _extract_price(soup) == "1999"

    def test_generic_decimal_with_currency_word(self):
        # Hits the generic '\d+[.,]\d{2}' fallback with a currency word nearby.
        soup = _soup('<html><body><p>Price 19.99 in USD</p></body></html>')
        assert _extract_price(soup) == "19.99"


# ---------------------------------------------------------------------------
# extract_product: add-to-cart action mutation + description fallbacks
# ---------------------------------------------------------------------------

class TestProductExtractor:
    def test_add_to_cart_button_gets_action_attribute(self):
        html = '<html><body><h1>Widget</h1><button>Add to Cart</button><p>$9.99</p></body></html>'
        soup = _soup(html)
        extract_product(soup, "/p/1", PageHint(None, {}))
        btn = soup.find("button")
        assert btn is not None
        assert btn.get("data-ai-action") == "add_to_cart"

    def test_description_from_meta(self):
        html = ('<html><head><meta name="description" content="A nice widget.">'
                '</head><body><h1>Widget</h1></body></html>')
        data = extract_product(_soup(html), "/p/1", PageHint(None, {}))
        assert data["description"] == "A nice widget."

    def test_extract_product_no_body_is_safe(self):
        # No <body> tag at all -> should not raise.
        html = '<html><head><title>X</title></head></html>'
        data = extract_product(_soup(html), "/p/1", PageHint(None, {}))
        assert data["url"] == "/p/1"


# ---------------------------------------------------------------------------
# extract_profile (extractors.py 230-241) — previously uncovered
# ---------------------------------------------------------------------------

class TestProfileExtractor:
    def test_profile_extracts_name_and_job_title(self):
        html = ('<html><body>'
                '<h1>Jane Doe</h1>'
                '<meta name="job_title" content="Principal Engineer">'
                '</body></html>')
        data = extract_profile(_soup(html), "/author/jane", PageHint(None, {}))
        assert data["name"] == "Jane Doe"
        assert data["jobTitle"] == "Principal Engineer"
        assert data["url"] == "/author/jane"

    def test_profile_hint_overrides_name(self):
        html = '<html><body><h1>Original</h1></body></html>'
        data = extract_profile(_soup(html), "/author/x", PageHint(None, {"name": "Override"}))
        assert data["name"] == "Override"

    def test_profile_falls_back_to_h2(self):
        html = '<html><body><h2>Second-Level Name</h2></body></html>'
        data = extract_profile(_soup(html), "/profile/y", PageHint(None, {}))
        assert data["name"] == "Second-Level Name"

    def test_profile_no_name_omits_field(self):
        html = '<html><body><p>just some text</p></body></html>'
        data = extract_profile(_soup(html), "/profile/z", PageHint(None, {}))
        assert "name" not in data


# ---------------------------------------------------------------------------
# extract_article: time-element + description fallback + body-less safety
# ---------------------------------------------------------------------------

class TestArticleExtractorEdgeCases:
    def test_date_from_time_datetime_attribute(self):
        html = ('<html><body>'
                '<time datetime="2026-03-01T12:00:00Z">March 1</time>'
                '</body></html>')
        data = extract_article(_soup(html), "/blog/x", PageHint(None, {}))
        assert data["datePublished"] == "2026-03-01T12:00:00Z"

    def test_description_from_og_description(self):
        html = ('<html><head><meta property="og:description" content="OG desc">'
                '</head><body></body></html>')
        data = extract_article(_soup(html), "/blog/x", PageHint(None, {}))
        assert data["description"] == "OG desc"
