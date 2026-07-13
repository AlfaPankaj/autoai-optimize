"""Entity extraction per page type.

Extractors read candidate fields out of the parsed HTML. They never raise on
missing data — they simply omit the field. The schema builders decide whether
enough was found to emit valid JSON-LD.

A developer's explicit hint fields always override extracted values.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from autoai_optimize.analyze.hints import PageHint


def _first_text(
    soup: BeautifulSoup,
    selectors: list[tuple[str, dict[str, Any]]],
    ai_field: str | None = None,
) -> str | None:
    """Return the stripped text of the first matching selector, or None."""
    for name, attrs in selectors:
        tag = soup.find(name, attrs=attrs)
        if tag and tag.get_text(strip=True):
            if ai_field:
                tag.attrs["data-ai-field"] = ai_field
            return tag.get_text(strip=True)
    return None


def _meta_content(
    soup: BeautifulSoup,
    selectors: list[tuple[str, dict[str, Any]]],
    ai_field: str | None = None,
) -> str | None:
    for name, attrs in selectors:
        tag = soup.find(name, attrs=attrs)
        if tag is None:
            continue
        # Meta tags expose their value via `content`; <time> uses `datetime`.
        value = tag.get("content")
        if value is None:
            value = tag.get("datetime")
        if value:
            if ai_field:
                tag.attrs["data-ai-field"] = ai_field
            return str(value).strip()
    return None


def extract_article(soup: BeautifulSoup, url: str, hint: PageHint) -> dict[str, Any]:
    """Extract Article fields from HTML, applying hint overrides last."""
    if soup.body:
        soup.body.attrs["data-ai-entity"] = "article"
    data: dict[str, Any] = {}

    title = _meta_content(
        soup,
        [
            ("meta", {"property": "og:title"}),
            ("meta", {"name": "twitter:title"}),
        ],
    ) or _first_text(
        soup,
        [
            ("h1", {}),
            ("title", {}),
        ],
    )
    if title:
        data["headline"] = title

    description = _meta_content(
        soup,
        [
            ("meta", {"name": "description"}),
            ("meta", {"property": "og:description"}),
        ],
    )
    if description:
        data["description"] = description

    image = _meta_content(soup, [("meta", {"property": "og:image"})])
    if image:
        data["image"] = image

    author = _meta_content(
        soup,
        [
            ("meta", {"name": "author"}),
            ("meta", {"property": "article:author"}),
        ],
    )
    if author:
        data["author"] = author

    date_published = _meta_content(
        soup,
        [
            ("meta", {"property": "article:published_time"}),
            ("time", {"datetime": True}),
        ],
    )
    if date_published:
        data["datePublished"] = date_published

    data["url"] = url

    # Developer overrides win.
    data.update(hint.fields)
    return data


def _tag_add_to_cart(soup: BeautifulSoup) -> None:
    """Tag the primary add-to-cart control with data-ai-action="add_to_cart".

    Scoped to a product container (in priority order): the first element with
    itemprop="offers", then <main>, then the body. Within that scope we prefer a
    real <button> / role="button" element whose text matches; only as a fallback
    do we match arbitrary text. This prevents nav links, footers, or
    testimonials that merely mention "add to cart" from stealing the tag.
    """
    import re

    pattern = re.compile(r"add to cart", re.I)

    # 1. Choose the search scope: prefer a narrow product container.
    scope = soup.find(attrs={"itemprop": "offers"})
    if scope is None:
        scope = soup.find("main")
    if scope is None:
        scope = soup.body or soup

    # 2. Prefer a real button-like element whose text matches.
    candidate = None
    for btn in scope.find_all(["button", "input", "a"]):
        if btn.get("type", "").lower() in ("submit", "button") or btn.name == "button" or btn.get("role") == "button":
            text = btn.get_text(" ", strip=True) or (btn.get("value") or "")
            if pattern.search(text):
                candidate = btn
                break
    # 3. Fallback: any text node match within the scope only.
    if candidate is None:
        node = scope.find(string=pattern)
        if node is not None and node.parent is not None:
            candidate = node.parent

    if candidate is not None:
        candidate.attrs["data-ai-action"] = "add_to_cart"


def extract_product(soup: BeautifulSoup, url: str, hint: PageHint) -> dict[str, Any]:
    """Extract Product fields from HTML, applying hint overrides last."""
    if soup.body:
        soup.body.attrs["data-ai-entity"] = "product"

    _tag_add_to_cart(soup)

    data: dict[str, Any] = {}

    name = _first_text(
        soup,
        [
            ("h1", {}),
            ("meta", {"itemprop": "name"}),
        ],
    )
    if name:
        data["name"] = name

    description = _meta_content(
        soup,
        [
            ("meta", {"name": "description"}),
            ("meta", {"property": "og:description"}),
        ],
    )
    if description:
        data["description"] = description

    image = _meta_content(soup, [("meta", {"property": "og:image"})])
    if image:
        data["image"] = image

    # Price: prefer microdata itemprop, then scan for a currency pattern.
    price = _extract_price(soup)
    if price:
        data["price"] = price

    data["url"] = url
    data.update(hint.fields)
    return data


def _extract_price(soup: BeautifulSoup) -> str | None:
    """Best-effort price extraction → returns a numeric string like '29.99'.

    Attempts to be locale-aware for common formats (US, EU, INR, GBP).
    Returns None when no confident price is found.
    """
    import re

    def normalize_num(raw: str) -> str:
        # Remove spaces and non-breaking spaces
        s = raw.strip().replace('\xa0', '').replace(' ', '')
        # If both '.' and ',' present, infer decimal separator by last occurrence
        if '.' in s and ',' in s:
            if s.rfind('.') > s.rfind(','):
                # '.' likely decimal separator, remove grouping commas
                s = s.replace(',', '')
            else:
                # ',' likely decimal separator
                s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            # If comma followed by exactly 2 digits at end, treat as decimal
            if re.search(r",\d{1,2}$", s):
                s = s.replace(',', '.')
            else:
                # otherwise remove thousands separator commas
                s = s.replace(',', '')
        # else only dot present or only digits
        # Strip any non-digit/non-dot characters
        s = re.sub(r"[^0-9.]", "", s)
        # Trim leading/trailing dots
        s = s.strip('.')
        return s

    # 1) microdata itemprop price
    itemprop = soup.find(itemprop="price")
    if itemprop:
        raw = str(itemprop.get("content") or itemprop.get_text(strip=True))
        m = re.search(r"\d+[.,]?\d*", raw or "")
        if m:
            return normalize_num(m.group(0))

    # 2) Symbol-based patterns (symbol before or after)
    symbol_pattern_pre = re.compile(r"([$€£¥₹])\s?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)")
    symbol_pattern_post = re.compile(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)\s?([$€£¥₹])")
    for el in soup.find_all(string=True):
        txt = str(el)
        m = symbol_pattern_pre.search(txt)
        if m:
            return normalize_num(m.group(2))
        m = symbol_pattern_post.search(txt)
        if m:
            # group(1) is the number, group(2) is the symbol.
            return normalize_num(m.group(1))

    # 3) Currency code suffix or prefix, e.g. '1000 INR' or 'EUR 1.234,56'
    code_suffix = re.compile(r"(\d[\d.,]*)\s?(USD|EUR|GBP|INR)", re.IGNORECASE)
    code_prefix = re.compile(r"(USD|EUR|GBP|INR)\s?(\d[\d.,]*)", re.IGNORECASE)
    for el in soup.find_all(string=True):
        txt = str(el)
        m = code_suffix.search(txt)
        if m:
            return normalize_num(m.group(1))
        m = code_prefix.search(txt)
        if m:
            return normalize_num(m.group(2))

    # 4) Fallback: any 1-4 digit group with decimals and currency nearby
    generic = re.compile(r"\d+[.,]\d{2}")
    for el in soup.find_all(string=generic):
        txt = str(el)
        # ensure there's a currency symbol or code nearby in the element
        if re.search(r"[$€£¥₹]|USD|EUR|GBP|INR", txt, re.IGNORECASE):
            m = generic.search(txt)
            if m:
                return normalize_num(m.group(0))
    return None

def extract_profile(soup: BeautifulSoup, url: str, hint: PageHint) -> dict[str, Any]:
    if soup.body:
        soup.body.attrs["data-ai-entity"] = "profile"
    data: dict[str, Any] = {}
    name = _first_text(soup, [("h1", {}), ("h2", {})], "name")
    if name:
        data["name"] = name
    job = _meta_content(soup, [("meta", {"name": "job_title"})], "jobTitle")
    if job:
        data["jobTitle"] = job
    data["url"] = url
    data.update(hint.fields)
    return data
