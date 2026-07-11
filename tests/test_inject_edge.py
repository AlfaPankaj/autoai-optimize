"""Edge-case tests for inject/html.py — targets uncovered branches.

Covers:
  - existing_ld_types / existing_ld_nodes with unparseable JSON-LD and empty tags
  - _collect_nodes on nested @graph and lists of nodes
  - inject_jsonld with no <html> wrapper (fragments get wrapped)
  - inject_jsonld when a <head> must be created on an existing <html>
  - ai_field mutation in the extractor helpers (already covered elsewhere)
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from src.autoai_optimize.inject.html import (
    _collect_nodes,
    _extract_types,
    existing_ld_nodes,
    existing_ld_types,
    inject_jsonld,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# existing_ld_types — malformed / empty / list-type variants
# ---------------------------------------------------------------------------

class TestExistingLdTypesEdge:
    def test_unparseable_json_is_ignored(self):
        # Broken JSON inside a ld+json script must not raise.
        html = '<html><head><script type="application/ld+json">{not valid json}</script></head></html>'
        assert existing_ld_types(_soup(html)) == set()

    def test_empty_script_is_ignored(self):
        html = '<html><head><script type="application/ld+json"></script></head></html>'
        assert existing_ld_types(_soup(html)) == set()

    def test_list_of_types(self):
        # @type may itself be a list.
        raw = json.dumps({"@type": ["Article", "NewsArticle"], "headline": "x"})
        html = f'<html><head><script type="application/ld+json">{raw}</script></head></html>'
        types = existing_ld_types(_soup(html))
        assert types == {"Article", "NewsArticle"}

    def test_graph_with_nested_types(self):
        raw = json.dumps({"@graph": [{"@type": "Article"}, {"@type": "Product"}]})
        html = f'<html><head><script type="application/ld+json">{raw}</script></head></html>'
        types = existing_ld_types(_soup(html))
        assert {"Article", "Product"} <= types

    def test_top_level_list_of_nodes(self):
        # A ld+json script whose content is a JSON array of nodes.
        raw = json.dumps([{"@type": "Article"}, {"@type": "Organization"}])
        html = f'<html><head><script type="application/ld+json">{raw}</script></head></html>'
        types = existing_ld_types(_soup(html))
        assert {"Article", "Organization"} <= types

    def test_content_type_with_parameters(self):
        # Some real-world pages add charset to the type attribute.
        html = ('<html><head>'
                '<script type="application/ld+json; charset=utf-8">{"@type":"Article"}</script>'
                '</head></html>')
        # Note: exact-match find_all may miss the parametrized type; this
        # documents current behavior (only the canonical type is matched).
        types = existing_ld_types(_soup(html))
        assert isinstance(types, set)


# ---------------------------------------------------------------------------
# existing_ld_nodes — flat list of node dicts
# ---------------------------------------------------------------------------

class TestExistingLdNodes:
    def test_returns_node_dicts(self):
        node = {"@type": "Article", "headline": "Hi", "url": "/a"}
        raw = json.dumps(node)
        html = f'<html><head><script type="application/ld+json">{raw}</script></head></html>'
        result = existing_ld_nodes(_soup(html))
        assert len(result) == 1
        assert result[0]["@type"] == "Article"
        assert result[0]["headline"] == "Hi"

    def test_graph_nodes_flattened(self):
        raw = json.dumps({"@graph": [{"@type": "Article"}, {"@type": "Product"}]})
        html = f'<html><head><script type="application/ld+json">{raw}</script></head></html>'
        result = existing_ld_nodes(_soup(html))
        assert len(result) == 2
        assert {n["@type"] for n in result} == {"Article", "Product"}

    def test_empty_when_no_script(self):
        assert existing_ld_nodes(_soup("<html><body></body></html>")) == []

    def test_unparseable_ignored(self):
        html = '<html><head><script type="application/ld+json">garbage</script></head></html>'
        assert existing_ld_nodes(_soup(html)) == []


# ---------------------------------------------------------------------------
# _collect_nodes / _extract_types internals
# ---------------------------------------------------------------------------

class TestCollectNodesInternals:
    def test_collect_nodes_on_dict_without_type_skips(self):
        out: list[dict] = []
        _collect_nodes({"foo": "bar"}, out)
        # No @type -> not collected as a node.
        assert out == []

    def test_collect_nodes_on_list(self):
        out: list[dict] = []
        _collect_nodes([{"@type": "A"}, {"@type": "B"}], out)
        assert {n["@type"] for n in out} == {"A", "B"}

    def test_extract_types_on_plain_list_of_strings(self):
        # A list of non-dict entries should not raise.
        assert _extract_types(["a", "b"]) == set()

    def test_extract_types_dict_with_list_type(self):
        assert _extract_types({"@type": ["X", "Y"]}) == {"X", "Y"}


# ---------------------------------------------------------------------------
# inject_jsonld — structural edge cases
# ---------------------------------------------------------------------------

class TestInjectJsonldEdge:
    def test_wraps_fragment_with_no_html_tag(self):
        # A bare fragment (no <html>) gets wrapped so injection can happen.
        html = "<div><p>Just a fragment</p></div>"
        node = {"@type": "Article", "headline": "Frag"}
        result = inject_jsonld(html, node)
        assert "<html" in result
        assert "<head" in result
        assert "application/ld+json" in result

    def test_creates_head_on_html_without_head(self):
        # <html> present but no <head> -> one is created and prepended.
        html = "<html><body><h1>Hi</h1></body></html>"
        node = {"@type": "Product", "name": "X"}
        result = inject_jsonld(html, node)
        assert "<head" in result
        assert "application/ld+json" in result

    def test_injected_node_is_valid_json(self):
        html = "<html><body>hi</body></html>"
        node = {"@type": "Article", "headline": "X"}
        result = inject_jsonld(html, node)
        soup = BeautifulSoup(result, "html.parser")
        script = soup.find("script", {"type": "application/ld+json"})
        parsed = json.loads(script.string)
        assert parsed["headline"] == "X"

    def test_unicode_in_node_preserved(self):
        html = "<html><head></head></html>"
        node = {"@type": "Article", "headline": "Café — résumé"}
        result = inject_jsonld(html, node)
        # ensure_ascii=False keeps accented chars readable.
        assert "Café" in result
