"""Regression tests for the add-to-cart action scoping (finding #4).

The 'add to cart' matcher must be scoped to a product container (<main>,
offers, or the buy area), not the whole document — otherwise a nav link,
footer, or testimonial mentioning 'add to cart' gets the data-ai-action
attribute instead of the real buy button.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from autoai_optimize.analyze.extractors import extract_product
from autoai_optimize.analyze.hints import PageHint


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_nav_link_with_add_to_cart_is_not_tagged_instead_of_button():
    """The nav 'add to cart' link must NOT steal the data-ai-action."""
    html = """\
<html><body>
  <nav><a href="/cart">View your cart or add to cart</a></nav>
  <main>
    <h1>Super Widget</h1>
    <p class="price">$19.99</p>
    <button id="buy">Add to Cart</button>
  </main>
</body></html>"""
    soup = _soup(html)
    extract_product(soup, "/products/widget", PageHint(None, {}))

    nav_link = soup.find("a", href="/cart")
    buy_button = soup.find("button", id="buy")

    # The real buy button (inside <main>) should be tagged.
    assert buy_button.get("data-ai-action") == "add_to_cart"
    # The nav link must NOT be tagged — that was the bug.
    assert nav_link.get("data-ai-action") is None


def test_footer_testimonial_does_not_steal_tag():
    """A testimonial mentioning 'add to cart' in the footer must not be tagged."""
    html = """\
<html><body>
  <main>
    <h1>Widget</h1>
    <p>$9.99</p>
    <button id="buy">Add to Cart</button>
  </main>
  <footer><blockquote>I love that I can just add to cart and check out!</blockquote></footer>
</body></html>"""
    soup = _soup(html)
    extract_product(soup, "/p/1", PageHint(None, {}))

    buy_button = soup.find("button", id="buy")
    blockquote = soup.find("blockquote")

    assert buy_button.get("data-ai-action") == "add_to_cart"
    assert blockquote.get("data-ai-action") is None


def test_button_still_tagged_when_no_main():
    """When there's no <main>, fall back to body but still prefer a <button>."""
    html = """\
<html><body>
  <div class="product">
    <h1>Widget</h1>
    <p>$9.99</p>
    <button>Add to Cart</button>
  </div>
</body></html>"""
    soup = _soup(html)
    extract_product(soup, "/p/1", PageHint(None, {}))
    btn = soup.find("button")
    assert btn.get("data-ai-action") == "add_to_cart"


def test_prefer_button_element_over_text_match():
    """When 'add to cart' appears in both a <button> and a <div>, prefer the <button>."""
    html = """\
<html><body><main>
  <div class="banner">Click add to cart for 10% off!</div>
  <button>Add to Cart</button>
</main></body></html>"""
    soup = _soup(html)
    extract_product(soup, "/p/1", PageHint(None, {}))
    banner = soup.find("div", class_="banner")
    button = soup.find("button")
    assert button.get("data-ai-action") == "add_to_cart"
    assert banner.get("data-ai-action") is None


def test_no_add_to_cart_means_no_tag():
    """Sanity: page with no buy wording gets no data-ai-action anywhere."""
    html = '<html><body><main><h1>Widget</h1><p>$9.99</p></main></body></html>'
    soup = _soup(html)
    extract_product(soup, "/p/1", PageHint(None, {}))
    tagged = soup.find(attrs={"data-ai-action": True})
    assert tagged is None
