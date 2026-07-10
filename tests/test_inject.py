"""Tests for the HTML JSON-LD injector."""

from __future__ import annotations

import json

from autoai_optimize.inject.html import existing_ld_types, inject_jsonld


class TestExistingLdTypes:
    def test_detects_article_type(self):
        html = '<html><head><script type="application/ld+json">{"@type":"Article"}</script></head></html>'
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        types = existing_ld_types(soup)
        assert "Article" in types

    def test_detects_product_type(self):
        html = '<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"X"}</script></head></html>'
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        types = existing_ld_types(soup)
        assert "Product" in types

    def test_empty_page(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<html></html>", "html.parser")
        assert existing_ld_types(soup) == set()

    def test_handles_graph(self):
        html = '<html><head><script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Article"},{"@type":"Organization"}]}</script></head></html>'
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        types = existing_ld_types(soup)
        assert "Article" in types
        assert "Organization" in types


class TestInjectJsonld:
    def test_injects_into_head(self):
        html = "<html><head><title>Test</title></head><body></body></html>"
        node = {"@context": "https://schema.org", "@type": "Article", "headline": "Test"}
        result = inject_jsonld(html, node)
        assert "application/ld+json" in result
        assert "Article" in result

    def test_creates_head_if_missing(self):
        html = "<html><body><h1>Hi</h1></body></html>"
        node = {"@context": "https://schema.org", "@type": "Product", "name": "X"}
        result = inject_jsonld(html, node)
        assert "<head>" in result

    def test_script_is_valid_json(self):
        html = "<html><head></head></html>"
        node = {"@context": "https://schema.org", "@type": "Article", "headline": "Test"}
        result = inject_jsonld(html, node)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(result, "html.parser")
        script = soup.find("script", {"type": "application/ld+json"})
        parsed = json.loads(script.string)
        assert parsed["headline"] == "Test"

    def test_injects_as_first_head_child(self):
        html = "<html><head><title>After</title></head></html>"
        node = {"@context": "https://schema.org", "@type": "Article", "headline": "X"}
        result = inject_jsonld(html, node)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(result, "html.parser")
        first = soup.head.contents[0] if soup.head.contents else None
        assert first is not None
        assert first.name == "script"
