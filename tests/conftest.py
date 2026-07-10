"""Shared test fixtures."""

from __future__ import annotations

import textwrap

import pytest

# ---------------------------------------------------------------------------
# Sample HTML fixtures used by multiple test modules
# ---------------------------------------------------------------------------

ARTICLE_HTML = textwrap.dedent("""\
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Why Fast APIs Matter</title>
        <meta property="og:title" content="Why Fast APIs Matter">
        <meta property="og:description" content="A look at API latency.">
        <meta property="og:image" content="https://example.com/img.png">
        <meta property="og:type" content="article">
        <meta property="article:author" content="Pankaj">
        <meta property="article:published_time" content="2026-07-01T09:00:00Z">
    </head>
    <body>
        <article>
            <h1>Why Fast APIs Matter</h1>
            <time datetime="2026-07-01T09:00:00Z">July 1, 2026</time>
        </article>
    </body>
    </html>
""")

PRODUCT_HTML = textwrap.dedent("""\
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Widget Pro 3000</title>
        <meta property="og:title" content="Widget Pro 3000">
        <meta property="og:description" content="Professional widget.">
        <meta property="og:image" content="https://example.com/widget.png">
        <meta property="og:type" content="product">
    </head>
    <body>
        <main>
            <h1>Widget Pro 3000</h1>
            <p class="price">$99.99</p>
            <button>Add to Cart</button>
        </main>
    </body>
    </html>
""")

UNKNOWN_HTML = textwrap.dedent("""\
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Welcome</title>
    </head>
    <body>
        <h1>Welcome to our site</h1>
        <p>Nothing to classify here.</p>
    </body>
    </html>
""")


@pytest.fixture()
def article_html() -> str:
    return ARTICLE_HTML


@pytest.fixture()
def product_html() -> str:
    return PRODUCT_HTML


@pytest.fixture()
def unknown_html() -> str:
    return UNKNOWN_HTML
