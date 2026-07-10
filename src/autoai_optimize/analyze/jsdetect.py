from __future__ import annotations

from bs4 import BeautifulSoup


def detect_js_rendered(html: str) -> bool:
    """Heuristic to detect likely client-side rendered pages.

    Returns True when the HTML appears to be a thin shell and relies on JS to
    render meaningful content. This is a heuristic (not perfect) and intended
    to warn users to use prerendering or the offload pre-scan pipeline.
    """
    if not html:
        return False
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body
    # Heuristic rules: very small body text, presence of a root app div, many
    # <script> tags, or presence of known SPA markers.
    text_len = len(body.get_text(strip=True)) if body else 0
    scripts = len(soup.find_all("script"))
    has_root_div = bool(soup.find(id=lambda x: x and str(x).lower() in ("app", "root", "__next", "svelte-app")))
    # If body text is tiny and scripts are many, likely JS heavy.
    if text_len < 50 and scripts >= 2 and has_root_div:
        return True
    # If the only text is a loader / noscript fallback, treat as JS-rendered.
    if body and body.find("noscript") and text_len < 100:
        return True
    return False
