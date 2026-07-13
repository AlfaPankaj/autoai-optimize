from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

import autoai_optimize.core as core
from autoai_optimize.core import generate_jsonld
from autoai_optimize.inject.html import inject_jsonld
from autoai_optimize.utils import get_logger

_log = get_logger()


def discover_html_files(root: Path | str) -> Iterable[Path]:
    rootp = Path(root)
    for p in sorted(rootp.rglob("*")):
        if p.suffix.lower() in {".html", ".htm"} and p.is_file():
            yield p


def prepopulate_cache_from_folder(root: Path | str) -> int:
    """Scan a folder of HTML files, generate JSON-LD nodes and populate
    the runtime cache with the enriched HTML. Returns the number of pages
    cached.

    This helps large sites by doing expensive parsing ahead of time (e.g.,
    during deploy) so runtime middleware often hits the cache and skips
    per-request BeautifulSoup work.
    """
    count = 0
    rootp = Path(root)
    if not rootp.is_dir():
        raise ValueError(f"{root} is not a directory")
    for html_file in discover_html_files(rootp):
        try:
            html = html_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _log.warning("offload: could not read %s: %s", html_file, exc)
            continue
        # Best-guess URL path from file location (mimic demo.file_to_url)
        rel = html_file.relative_to(rootp).with_suffix("")
        parts = rel.parts
        if not parts or parts[-1] == "index":
            path = "/" + "/".join(parts[:-1])
        else:
            path = "/" + "/".join(parts)
        url = path if path.endswith("/") or path == "/" or "." in path else path

        node = generate_jsonld(html, url=url)
        if node is None:
            continue
        enriched = inject_jsonld(html, node)
        h = hashlib.md5(html.encode("utf-8")).hexdigest()
        try:
            if hasattr(core, "_CACHE") and core._CACHE is not None:
                cache = core._CACHE
                if hasattr(cache, "set"):
                    cache.set(h, enriched)
                    count += 1
        except Exception as exc:
            _log.warning("offload: failed to set cache for %s: %s", html_file, exc)
    return count
