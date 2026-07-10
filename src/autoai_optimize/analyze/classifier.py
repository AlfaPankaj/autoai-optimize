"""Heuristic page-type classifier.

Determines whether a response represents an Article or a Product page using
URL patterns, HTML signals, and meta tags. Confidence-scored so the core can
fall back to silence when uncertain — a wrong schema is worse than none.

Developer hints (see hints.py) always override this classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from bs4 import BeautifulSoup

ARTICLE_URL_HINTS = ("/blog/", "/post/", "/article/", "/news/", "/posts/")
PRODUCT_URL_HINTS = ("/product/", "/products/", "/shop/", "/p/", "/item/")


class PageType(str, Enum):
    """Page types autoai-optimize knows how to enrich in Phase 1."""

    ARTICLE = "Article"
    PRODUCT = "Product"
    PROFILE = "Profile"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class Classification:
    """The result of classifying a single response."""

    page_type: PageType
    confidence: float  # 0.0–1.0


def _score_article(url_path: str, soup: BeautifulSoup) -> float:
    """Confidence that the page is an Article."""
    score = 0.0
    if any(h in url_path for h in ARTICLE_URL_HINTS):
        score += 0.4
    if soup.find("article"):
        score += 0.25
    if soup.find("time"):
        score += 0.15
    # Common blog/article metadata.
    if soup.find("meta", attrs={"name": "author"}) or soup.find("meta", attrs={"property": "article:author"}):
        score += 0.15
    og_type = _og_type(soup)
    if og_type == "article":
        score += 0.3
    return min(score, 1.0)


def _score_product(url_path: str, soup: BeautifulSoup) -> float:
    """Confidence that the page is a Product page."""
    score = 0.0
    if any(h in url_path for h in PRODUCT_URL_HINTS):
        score += 0.4
    # Price-like text anywhere (currency symbol followed by digits).
    if _has_price_signal(soup):
        score += 0.25
    # Add-to-cart / buy controls are strong commerce signals.
    text_lc = soup.get_text(" ") if soup.find() else ""
    if any(k in text_lc for k in ("add to cart", "add to bag", "buy now")):
        score += 0.2
    # og:type=product is a strong, explicit signal.
    og_type = _og_type(soup)
    if og_type == "product":
        score += 0.3
    return min(score, 1.0)


def _og_type(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", attrs={"property": "og:type"})
    if tag and tag.get("content"):
        return str(tag["content"]).strip().lower()
    return None


def _has_price_signal(soup: BeautifulSoup) -> bool:
    """True if the page contains plausible price text (e.g. '$29.99', '€10')."""
    import re

    pattern = re.compile(r"[$€£¥₹]\s?\d|\d+[.,]\d{2}\s?(?:usd|eur|gbp)", re.IGNORECASE)
    for _el in soup.find_all(string=pattern):
        return True
    # microdata/itemprop price is an even stronger, explicit signal.
    return soup.find(itemprop="price") is not None


def classify(url_path: str, soup: BeautifulSoup) -> Classification:
    """Classify a parsed page. Never raises; returns UNKNOWN on no signal.

    Args:
        url_path: Path portion of the request URL (e.g. "/blog/my-post").
        soup: Parsed HTML (BeautifulSoup).
    """
    art = _score_article(url_path, soup)
    prod = _score_product(url_path, soup)
    if art == prod == 0.0:
        return Classification(PageType.UNKNOWN, 0.0)
    if art >= prod:
        return Classification(PageType.ARTICLE, art)
    return Classification(PageType.PRODUCT, prod)

def _score_profile(url_path: str, soup: BeautifulSoup) -> float:
    score = 0.0
    import re
    if "/author/" in url_path or "/profile/" in url_path or "/user/" in url_path:
        score += 0.5
    if soup.find(class_=re.compile("profile|bio|author-card", re.I)):
        score += 0.4
    return min(1.0, score)
