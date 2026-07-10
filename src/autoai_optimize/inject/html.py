"""Inject JSON-LD <script> blocks into HTML <head>, idempotently.

Design notes:
- We inject as the first child of <head> so search engines see it early.
- Idempotency: if a JSON-LD block with the same @type already exists, we do
  not add another (configurable). This prevents duplicates on cached pages or
  when a framework re-runs middleware.
- If the document has no <head>, we create one; if it has no <html>, we wrap it.
"""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

LD_SCRIPT_TYPE = "application/ld+json"


def existing_ld_types(soup: BeautifulSoup) -> set[str]:
    """Return the set of @type values already present in the document.

    Handles both dict-style ({..., "@type": "Article"}) and list-style
    (@graph) JSON-LD blocks. Unparseable blocks are ignored (never raise).
    """
    found: set[str] = set()
    for tag in soup.find_all("script", {"type": LD_SCRIPT_TYPE}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        found.update(_extract_types(parsed))
    return found


def existing_ld_nodes(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Parse and return all JSON-LD nodes found in the document as dicts.

    Unparseable blocks are ignored. Returns a flat list of node dicts — if a
    script contains an @graph array, each graph node is returned individually.
    """
    nodes: list[dict[str, Any]] = []
    for tag in soup.find_all("script", {"type": LD_SCRIPT_TYPE}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        _collect_nodes(parsed, nodes)
    return nodes


def _collect_nodes(parsed: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(parsed, dict):
        # If this dict itself looks like a node (has @type) add it.
        if "@type" in parsed and isinstance(parsed.get("@type"), (str, list)):
            out.append(parsed)
        # If there's an @graph, add its members.
        graph = parsed.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                _collect_nodes(node, out)
    elif isinstance(parsed, list):
        for node in parsed:
            _collect_nodes(node, out)


def _extract_types(parsed: Any) -> set[str]:
    types: set[str] = set()
    if isinstance(parsed, dict):
        t = parsed.get("@type")
        if isinstance(t, str):
            types.add(t)
        elif isinstance(t, list):
            types.update(x for x in t if isinstance(x, str))
        # @graph may hold multiple nodes.
        graph = parsed.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                types.update(_extract_types(node))
    elif isinstance(parsed, list):
        for node in parsed:
            types.update(_extract_types(node))
    return types


def inject_jsonld(html: str, node: dict[str, Any]) -> str:
    """Inject a single JSON-LD node into the HTML's <head>.

    Returns the (possibly unchanged) HTML string. Uses the 'html.parser' built
    into BeautifulSoup to avoid a hard lxml dependency; callers that want the
    faster lxml parser may pre-parse and pass results via core.py instead.
    """
    soup = BeautifulSoup(html, "html.parser")
    head = soup.head
    if head is None:
        # Ensure there's a <head> to inject into.
        if soup.html is None:
            soup = BeautifulSoup(f"<html><head></head><body>{html}</body></html>", "html.parser")
            head = soup.head
            assert head is not None  # we just created it
        else:
            head = soup.new_tag("head")
            soup.html.insert(0, head)

    script = soup.new_tag("script", type=LD_SCRIPT_TYPE)
    script.string = json.dumps(node, ensure_ascii=False, separators=(",", ":"))
    head.insert(0, script)
    return str(soup)
