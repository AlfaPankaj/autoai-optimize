from __future__ import annotations

from src.autoai_optimize.core import generate_jsonld, optimize_html
from src.autoai_optimize.utils import METRICS


def test_metrics_increment_on_generate_and_optimize():
    METRICS.clear()
    html = '<html><head></head><body><h1>Hi</h1></body></html>'
    # No hints, should be unknown -> skipped. Metrics incremented.
    node = generate_jsonld(html, url="/")
    assert node is None
    assert METRICS.get("skipped.unknown") >= 1

    METRICS.clear()
    _ = optimize_html('<html><head></head><body><h1>Hi</h1></body></html>', url="/blog/post")
    # /blog/post likely classified as Article -> enriched or skipped based on content
    snap = METRICS.snapshot()
    assert isinstance(snap, dict)
    # At least one of served.enriched, served.no_node or served.cache_hit is present
    assert snap.get("served.enriched", 0) + snap.get("served.no_node", 0) + snap.get("served.cache_hit", 0) >= 1
