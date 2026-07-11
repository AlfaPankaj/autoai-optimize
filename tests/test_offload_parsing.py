from __future__ import annotations

from pathlib import Path

from src.autoai_optimize.core import optimize_html
from src.autoai_optimize.offload import prepopulate_cache_from_folder


def test_offload_populates_cache_and_optimize_on_hit():
    root = Path(__file__).resolve().parent.parent / "sample_site"
    # Prepopulate cache from sample_site
    cached = prepopulate_cache_from_folder(root)
    assert cached >= 1

    # Read a likely-enriched file (blog article) and ensure optimize_html returns enriched HTML
    html_file = root / "blog" / "why-fast-apis-matter.html"
    html = html_file.read_text(encoding="utf-8")
    enriched = optimize_html(html, url="/blog/why-fast-apis-matter.html")
    assert isinstance(enriched, str)
    assert "application/ld+json" in enriched
