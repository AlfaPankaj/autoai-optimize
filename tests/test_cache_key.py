"""Regression tests for cache-key composition (finding #7).

The cache key MUST include the config + url, not just the HTML hash,
otherwise two calls with the same HTML but different settings collide
and the second caller silently gets the first caller's result.

We reproduce the collision with two configs that BOTH reach the cache
(neither disabled) but produce different outputs: differing min_confidence
on hint-free HTML classifies the page differently.
"""

from __future__ import annotations

from autoai_optimize.config import Config
from autoai_optimize.core import _CACHE, optimize_html

# Hint-free product HTML. Scores ~0.65 as Product (/products/ URL + price signal).
# At min_confidence=0.5 -> enriched; at min_confidence=0.8 -> UNKNOWN -> original.
HINT_FREE_PRODUCT = (
    '<html><head><title>Widget</title></head>'
    '<body>'
    '<h1>Super Widget</h1>'
    '<p class="price">$19.99</p>'
    '<button>Add to Cart</button>'
    '</body></html>'
)


def _reset_cache() -> None:
    _CACHE.clear()


def test_cache_collision_same_html_different_min_confidence():
    """THE BUG: same HTML + different min_confidence must NOT share a cache entry.

    Both calls reach the cache (neither is disabled). The first call's result
    must not be served to the second call with a different threshold.
    """
    _reset_cache()

    # Call 1: strict threshold -> page is UNKNOWN -> original HTML cached.
    strict = optimize_html(
        HINT_FREE_PRODUCT, url="/products/widget", config=Config(min_confidence=0.8)
    )
    assert '<script type="application/ld+json">' not in strict  # not enriched

    # Call 2: lenient threshold on the SAME html, WITHOUT clearing the cache.
    # BUG (old key): returns Call 1's cached original HTML.
    # FIX (config-aware key): actually enriches because threshold is met.
    lenient = optimize_html(
        HINT_FREE_PRODUCT, url="/products/widget", config=Config(min_confidence=0.5)
    )
    assert '<script type="application/ld+json">' in lenient  # must be enriched


def test_cache_key_differs_by_inject_existing():
    """inject_existing=True vs False on HTML carrying existing LD must differ."""
    _reset_cache()
    existing_node = '{"@type": "Product", "name": "Super Widget", "url": "/products/widget"}'
    html_with_ld = (
        '<html><head>'
        f'<script type="application/ld+json">{existing_node}</script>'
        '</head><body><h1>Super Widget</h1><p>$19.99</p></body></html>'
    )

    # With inject_existing=True -> skips injection (idempotent), caches original.
    idempotent = optimize_html(
        html_with_ld, url="/products/widget", config=Config(inject_existing=True)
    )
    assert idempotent.count('<script type="application/ld+json">') == 1

    # With inject_existing=False on the SAME html -> should inject a SECOND node.
    # BUG (old key): returns the cached single-node result.
    # FIX: actually injects because inject_existing=False.
    force_inject = optimize_html(
        html_with_ld, url="/products/widget", config=Config(inject_existing=False)
    )
    assert force_inject.count('<script type="application/ld+json">') >= 2


def test_cache_hit_for_identical_inputs_is_stable():
    """Sanity: identical html + url + config still hits the cache (no false miss)."""
    _reset_cache()
    cfg = Config()
    first = optimize_html(HINT_FREE_PRODUCT, url="/products/widget", config=cfg)
    second = optimize_html(HINT_FREE_PRODUCT, url="/products/widget", config=cfg)
    assert first == second  # deterministic and cached


def test_cache_key_differs_by_url():
    """Same HTML at different URLs should not collide (url affects the JSON-LD node)."""
    _reset_cache()
    cfg = Config(min_confidence=0.5)
    a = optimize_html(HINT_FREE_PRODUCT, url="/products/a", config=cfg)
    b = optimize_html(HINT_FREE_PRODUCT, url="/products/b", config=cfg)
    # The injected JSON-LD url field differs, so the cached HTML must differ.
    assert a != b
