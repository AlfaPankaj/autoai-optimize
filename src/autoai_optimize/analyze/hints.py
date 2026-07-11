"""Developer hints — the explicit override path.

When heuristics can't tell (or the developer knows better), the host app can
pass an explicit hint. Hints always win over heuristics and bypass the
confidence threshold.

Hints can be supplied via:
  - Framework adapter API (view attribute / decorator / response header)
  - A context dict passed to optimize_html()

All roads converge on a PageHint here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.autoai_optimize.analyze.classifier import PageType

# Canonical header a framework adapter may set on a response.
HINT_HEADER = "X-AutoAI-Type"

# Fields a developer can supply to pre-populate a schema, e.g.
#   hints={"type": "Product", "name": "Widget", "price": "29.99"}
_HINT_TYPE_KEY = "type"
_HINT_FIELD_KEY = "fields"


@dataclass(frozen=True)
class PageHint:
    """An explicit developer-supplied page classification / field override."""

    page_type: PageType | None
    fields: dict[str, Any]


def _coerce_type(value: Any) -> PageType | None:
    if value is None:
        return None
    if isinstance(value, PageType):
        return value
    name = str(value).strip().capitalize()
    try:
        return PageType(name)
    except ValueError:
        return None


def parse_hints(raw: dict[str, Any] | None, html_content: str = "") -> PageHint:
    """Normalize a raw hints dict (from adapter or context) into a PageHint.
    Also parses the HTML string for explicit frontend developer comments (e.g., <!-- @ai-entity:product -->).
    """
    if not raw:
        raw = {}
        
    import re
    if html_content:
        hint_match = re.search(r'<!--\s*@ai-entity:(\w+)\s*-->', html_content)
        if hint_match and _HINT_TYPE_KEY not in raw:
            raw[_HINT_TYPE_KEY] = hint_match.group(1).lower()

    if not raw:
        return PageHint(page_type=None, fields={})
    raw_type = raw.get(_HINT_TYPE_KEY)
    nested_fields = raw.get(_HINT_FIELD_KEY, {})
    fields: dict[str, Any] = dict(nested_fields) if isinstance(nested_fields, dict) else {}
    # Flat extras (everything that isn't "type"/"fields") become fields.
    for k, v in raw.items():
        if k in (_HINT_TYPE_KEY, _HINT_FIELD_KEY):
            continue
        fields.setdefault(k, v)
    return PageHint(page_type=_coerce_type(raw_type), fields=fields)
