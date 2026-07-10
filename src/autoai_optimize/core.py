"""Core orchestration: the framework-agnostic heart of autoai-optimize.

Two public entry points:

    generate_jsonld(html, url, ...) -> dict | None   # read-only, for tooling
    optimize_html(html, url, ...)   -> str           # injects into HTML

Everything else (classify, extract, build, inject) is wired here. The whole
pipeline is wrapped so that ANY failure returns the original input untouched —
the library must never break the host site.
"""

from __future__ import annotations

import hashlib
from typing import Any

from bs4 import BeautifulSoup

from autoai_optimize.analyze import classify, extract_article, extract_product, parse_hints
from autoai_optimize.analyze.classifier import PageType
from autoai_optimize.analyze.extractors import extract_profile
from autoai_optimize.config import DEFAULT_CONFIG, Config
from autoai_optimize.inject import inject_jsonld, existing_ld_nodes
from autoai_optimize.schema import build_for
from autoai_optimize.utils import LRUCache, get_logger

_log = get_logger()
# Thread-safe LRU cache with TTL to avoid unbounded memory growth and ensure
# cached HTML is eventually refreshed. Defaults chosen to be sensible for
# middleware usage; can be overridden by consumers by replacing core._CACHE.
_CACHE = LRUCache(max_size=1024, ttl_seconds=300)

def sync_updates(config: Config) -> bool:
    """POST a minimal update to the configured webhook URL with retries.

    Returns True on success (HTTP 2xx), False otherwise.
    """
    import json
    import time
    from urllib import request

    if not config.api_key:
        _log.warning("Cannot sync updates without an api_key.")
        return False

    payload = json.dumps({"event": "schema_updated"}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
        "User-Agent": "autoai-optimize/1.0",
    }

    max_attempts = 3
    backoff_base = 0.5
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            req = request.Request(config.webhook_url, data=payload, headers=headers, method="POST")
            with request.urlopen(req, timeout=5) as resp:
                code = getattr(resp, "status", None) or getattr(resp, "getcode", lambda: None)()
                if 200 <= (code or 0) < 300:
                    _log.info("Sync webhook succeeded (attempt %d)", attempt)
                    return True
                _log.warning("Sync webhook returned status %s (attempt %d)", code, attempt)
        except Exception as exc:
            last_exc = exc
            _log.warning("Sync webhook attempt %d failed: %s", attempt, exc)
        # Exponential backoff before next attempt
        if attempt < max_attempts:
            time.sleep(backoff_base * (2 ** (attempt - 1)))
    _log.error("Sync webhook failed after %d attempts: %s", max_attempts, last_exc)
    return False

# Extractor lookup by page type.
_EXTRACTORS = {
    PageType.ARTICLE: extract_article,
    PageType.PRODUCT: extract_product,
    PageType.PROFILE: extract_profile,
}


def _path_of(url: str) -> str:
    """Reduce a URL to its path component (always starts with '/').

    e.g. "https://x.com/blog/post?a=1" -> "/blog/post?a=1"; "/shop/p/2" -> "/shop/p/2".
    Used for URL-pattern classification.
    """
    if not url:
        return "/"
    path = url.split("://", 1)[-1]
    if "/" in path:
        path = "/" + path.split("/", 1)[1]
    else:
        path = "/"
    return path or "/"


def _classify_with_hints(
    html: str, url: str, context: dict[str, Any] | None, hints: dict[str, Any] | None, config: Config
) -> tuple[BeautifulSoup, PageType, Any]:
    """Shared classification step used by both public functions.

    Returns (soup, page_type, page_hint). Caller decides what to do on UNKNOWN.
    """
    soup = BeautifulSoup(html, "html.parser")
    url_path = _path_of(url)

    merged: dict[str, Any] = {}
    if context:
        merged.update(context.get("autoai", {}) if isinstance(context, dict) else {})
    if hints:
        merged.update(hints)
    page_hint = parse_hints(merged, html)

    classification = classify(url_path, soup)
    page_type = page_hint.page_type
    if page_type is None:
        page_type = (
            classification.page_type
            if classification.confidence >= config.min_confidence
            else PageType.UNKNOWN
        )
    return soup, page_type, page_hint


def generate_jsonld(
    html: str,
    url: str = "",
    *,
    context: dict[str, Any] | None = None,
    hints: dict[str, Any] | None = None,
    config: Config = DEFAULT_CONFIG,
) -> dict[str, Any] | None:
    """Analyze one HTML document and return its JSON-LD node, or None.

    The read-only counterpart of optimize_html: classifies the page, extracts
    entities, builds the JSON-LD, but does NOT inject anything. Used by demo.py
    / CLI tools that want the raw structured data. Never raises.

    Returns None when: disabled, no confident classification, the page already
    has this schema (idempotent), or insufficient data for a valid node.
    """
    if not config.enabled or not html:
        from autoai_optimize.utils import METRICS
        METRICS.incr("skipped.disabled_or_empty")
        return None
    try:
        soup, page_type, page_hint = _classify_with_hints(html, url, context, hints, config)
        if page_type is PageType.UNKNOWN:
            # Detect JS-rendered shells and increment a separate metric to
            # advise prerendering instead of per-request parsing.
            from autoai_optimize.analyze.jsdetect import detect_js_rendered
            if detect_js_rendered(html):
                from autoai_optimize.utils import METRICS
                METRICS.incr("skipped.js_rendered")
                return None
            from autoai_optimize.utils import METRICS
            METRICS.incr("skipped.unknown")
            return None

        extractor = _EXTRACTORS.get(page_type)
        if extractor is None:
            from autoai_optimize.utils import METRICS
            METRICS.incr("skipped.no_extractor")
            return None
        data = extractor(soup, url or _path_of(url), page_hint)
        node = build_for(page_type, data)
        if node is None:
            from autoai_optimize.utils import METRICS
            METRICS.incr("skipped.insufficient_data")
            return None

        # Stronger idempotency: if inject_existing is enabled, skip when an
        # existing JSON-LD node of the same @type is already present with the
        # same URL or identical content.
        if config.inject_existing:
            try:
                existing_nodes = existing_ld_nodes(soup)
                for en in existing_nodes:
                    # Match by exact dict equality (recent frameworks may include
                    # ordering differences; a simple equality is still useful).
                    if en == node:
                        _log.debug("autoai-optimize: identical JSON-LD node already present, skipping")
                        from autoai_optimize.utils import METRICS
                        METRICS.incr("skipped.existing_identical")
                        return None
                    # Or match by same @type and same url field.
                    if isinstance(en.get("@type"), str) and en.get("@type") == node.get("@type") and en.get("url") and node.get("url") and en.get("url") == node.get("url"):
                        _log.debug("autoai-optimize: JSON-LD of same type and url already present, skipping")
                        from autoai_optimize.utils import METRICS
                        METRICS.incr("skipped.existing_same_type_url")
                        return None
            except Exception:
                # Be conservative: on parser errors, do not fail — proceed.
                _log.debug("autoai-optimize: existing node check failed, continuing")

        from autoai_optimize.utils import METRICS
        METRICS.incr("generated.jsonld")
        return node
    except Exception as exc:
        _log.warning("autoai-optimize: JSON-LD generation failed (%s)", exc)
        from autoai_optimize.utils import METRICS
        METRICS.incr("errors.generation")
        return None


def optimize_html(
    html: str,
    url: str = "",
    *,
    context: dict[str, Any] | None = None,
    hints: dict[str, Any] | None = None,
    config: Config = DEFAULT_CONFIG,
) -> str:
    """Enrich an HTML string with auto-generated JSON-LD.

    Args:
        html: The response body (HTML text).
        url: Absolute or path URL of the page (used for url field + classification).
        context: Optional framework context (e.g. view context). Keys may
            include extraction hints; treated as best-effort.
        hints: Explicit developer hints (highest priority). e.g.
            {"type": "Product", "name": "Widget", "price": "9.99"}.
        config: Runtime config. Defaults to zero-config sensible values.

    Returns:
        The HTML with a JSON-LD <script> injected into <head>, or the
        original HTML unchanged when nothing confident could be derived or
        any error occurred. Never raises.
    """
    if not config.enabled or not html:
        return html
    html_hash = hashlib.md5(html.encode("utf-8")).hexdigest()
    try:
        cached = _CACHE.get(html_hash) if hasattr(_CACHE, "get") else None
        if cached is not None:
            from autoai_optimize.utils import METRICS
            METRICS.incr("served.cache_hit")
            # Cache may hold any object — ensure we return a str to match API.
            return str(cached)
        node = generate_jsonld(html, url, context=context, hints=hints, config=config)
        if node is None:
            if hasattr(_CACHE, "set"):
                _CACHE.set(html_hash, html)
            from autoai_optimize.utils import METRICS
            METRICS.incr("served.no_node")
            return html
        res = inject_jsonld(html, node)
        if hasattr(_CACHE, "set"):
            _CACHE.set(html_hash, res)
        from autoai_optimize.utils import METRICS
        METRICS.incr("served.enriched")
        return res
    except Exception as exc:
        _log.warning("autoai-optimize: enrichment failed (%s); returning original HTML", exc)
        from autoai_optimize.utils import METRICS
        METRICS.incr("errors.enrichment")
        return html
