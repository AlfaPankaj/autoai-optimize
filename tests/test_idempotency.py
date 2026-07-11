from __future__ import annotations

from src.autoai_optimize.core import generate_jsonld, optimize_html


def test_generate_jsonld_skips_existing_identical():
    html = '''<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"Hi","url":"/post"}</script>
</head><body><h1>Hi</h1></body></html>'''
    node = generate_jsonld(html, url="/post")
    assert node is None


def test_optimize_html_preserves_existing():
    html = '''<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"Hi","url":"/post"}</script>
</head><body><h1>Hi</h1></body></html>'''
    out = optimize_html(html, url="/post")
    assert out == html
