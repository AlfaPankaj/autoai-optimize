"""Regression tests for partial/fragment HTML injection (finding #3).

When the input is a fragment (no <html> tag), the injector must NOT wrap it
in a synthetic full document — that breaks HTMX/AJAX/template-fragment
responses. Instead it should prepend the JSON-LD inline.
"""

from __future__ import annotations

import json

from autoai_optimize.inject.html import inject_jsonld

NODE = {"@type": "Product", "name": "Widget", "url": "/p/1"}
LD_MARKER = '<script type="application/ld+json">'


class TestFragmentInjection:
    def test_fragment_not_wrapped_in_full_html_document(self):
        """A bare fragment must not gain a synthetic <html>/<body> wrapper."""
        fragment = '<div class="product"><h1>Widget</h1><p>$9.99</p></div>'
        result = inject_jsonld(fragment, NODE)

        # The JSON-LD must be injected...
        assert LD_MARKER in result
        # ...but the original fragment content must survive unchanged...
        assert '<div class="product">' in result
        assert '<h1>Widget</h1>' in result
        # ...and NO synthetic <html>/<body> structure must be added.
        assert "<html" not in result
        assert "<body" not in result

    def test_htmx_response_fragment_preserved(self):
        """Typical HTMX swap response must stay a fragment, not become a page."""
        fragment = '<div id="cart-count">3 items</div>'
        result = inject_jsonld(fragment, NODE)
        assert LD_MARKER in result
        assert '<div id="cart-count">3 items</div>' in result
        assert "<html" not in result

    def test_full_document_still_works(self):
        """Full HTML documents still inject into <head> as before."""
        html = '<html><head><title>X</title></head><body><h1>Hi</h1></body></html>'
        result = inject_jsonld(html, NODE)
        assert LD_MARKER in result
        # The script lands inside <head>.
        assert result.index(LD_MARKER) < result.index("</head>")

    def test_document_with_html_but_no_head(self):
        """<html> present but no <head> -> one is created (existing behavior)."""
        html = '<html><body><h1>Hi</h1></body></html>'
        result = inject_jsonld(html, NODE)
        assert LD_MARKER in result
        assert "<head" in result

    def test_injected_node_is_valid_json_in_fragment(self):
        """The injected script in a fragment must still be valid JSON."""
        fragment = '<div>fragment</div>'
        result = inject_jsonld(fragment, NODE)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(result, "html.parser")
        script = soup.find("script", {"type": "application/ld+json"})
        parsed = json.loads(script.string)
        assert parsed["name"] == "Widget"

    def test_fragment_round_trip_is_stable(self):
        """Injecting twice into the same fragment should not nest documents."""
        fragment = '<div>frag</div>'
        once = inject_jsonld(fragment, NODE)
        twice = inject_jsonld(once, NODE)
        # No synthetic <html> introduced either time.
        assert once.count("<html") == 0
        assert twice.count("<html") == 0
