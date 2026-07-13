from __future__ import annotations

from pathlib import Path

from autoai_optimize.core import optimize_html
from autoai_optimize.offload import prepopulate_cache_from_folder


def test_offload_populates_cache_and_optimize_on_hit(tmp_path: Path):
    # Create a temporary directory with a dummy HTML file
    blog_dir = tmp_path / "blog"
    blog_dir.mkdir()
    html_file = blog_dir / "why-fast-apis-matter.html"
    html_file.write_text(
        '<html><head><meta property="og:type" content="article"></head><body><h1>Hi</h1></body></html>',
        encoding="utf-8"
    )

    # Prepopulate cache from the temporary folder
    cached = prepopulate_cache_from_folder(tmp_path)
    assert cached >= 1

    # Read the file and ensure optimize_html returns enriched HTML
    html = html_file.read_text(encoding="utf-8")
    enriched = optimize_html(html, url="/blog/why-fast-apis-matter.html")
    assert isinstance(enriched, str)
    assert "application/ld+json" in enriched
