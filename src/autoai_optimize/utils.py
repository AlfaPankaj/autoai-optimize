"""Internal utilities: logging, content-type checks, small helpers."""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup

_logger: logging.Logger | None = None


def _preferred_parser() -> str:
    """Return the best available BeautifulSoup parser name.

    Prefers 'lxml' when installed (faster, better fidelity for real-world
    HTML), falls back to the stdlib 'html.parser' so the library has no hard
    lxml dependency.
    """
    try:
        import lxml  # noqa: F401
    except ImportError:
        return "html.parser"
    return "lxml"


def parse_html(html: str) -> BeautifulSoup:
    """Parse HTML with the best available parser (lxml if present).

    Centralizes parser selection so every entry point uses the same one and
    lxml can be adopted as a performance/fidelity win without code churn.
    """
    return BeautifulSoup(html, _preferred_parser())


def get_logger() -> logging.Logger:
    """Return the package logger (lazily configured, never propagates noise)."""
    global _logger
    if _logger is None:
        _logger = logging.getLogger("autoai_optimize")
        # Library convention: never configure handlers here; let the host app.
        if not _logger.handlers:
            _logger.addHandler(logging.NullHandler())
    return _logger


def is_html_content_type(content_type: str | None) -> bool:
    """True for HTML content types (text/html ...). Case-insensitive on the
    primary type; ignores parameters like charset."""
    if not content_type:
        return False
    primary = content_type.split(";", 1)[0].strip().lower()
    return primary == "text/html"


class LRUCache:
    """A thread-safe LRU cache with per-entry TTL.

    Usage:
        cache = LRUCache(max_size=1024, ttl_seconds=300)
        v = cache.get(k)
        cache.set(k, v)

    Eviction is lazy: ``get`` only checks TTL for the requested key (O(1)),
    and ``set`` batch-purges expired entries only when the cache is near
    capacity. This avoids the O(n) full-scan on every access that the
    original implementation had.
    """

    def __init__(self, max_size: int = 1024, ttl_seconds: int = 300) -> None:
        import threading
        import time
        from collections import OrderedDict

        self.max_size = int(max_size)
        self.ttl = int(ttl_seconds)
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._lock = threading.Lock()
        self._time = time

    def get(self, key: str) -> object | None:
        """Return value or None if missing/expired.

        Only checks TTL for the requested key — O(1), not O(n).
        """
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            _ts, val = item
            # Lazy TTL check: only for this key.
            if self._time.time() - _ts > self.ttl:
                del self._data[key]
                return None
            # Move to end as most recently used.
            self._data.move_to_end(key)
            return val

    def set(self, key: str, value: object) -> None:
        """Set value for key and enforce max_size.

        Batch-purges expired entries only when the cache is near capacity,
        amortizing the cost across many insertions.
        """
        with self._lock:
            self._data[key] = (self._time.time(), value)
            self._data.move_to_end(key)
            # Evict expired + oldest when over capacity.
            if len(self._data) > self.max_size:
                self._purge_expired()
                while len(self._data) > self.max_size:
                    self._data.popitem(last=False)

    def _purge_expired(self) -> None:
        """Remove all expired entries. Only called near capacity."""
        now = self._time.time()
        keys_to_delete: list[str] = []
        for k, (ts, _) in list(self._data.items()):
            if now - ts > self.ttl:
                keys_to_delete.append(k)
        for k in keys_to_delete:
            self._data.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class Metrics:
    """In-memory metrics counter useful for observability and testing.

    Lightweight and optional: the host application can call metrics.snapshot()
    or read counters. Counters are thread-safe.
    """

    def __init__(self) -> None:
        import threading
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}

    def incr(self, name: str, n: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + int(n)

    def get(self, name: str) -> int:
        with self._lock:
            return int(self._counters.get(name, 0))

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def clear(self) -> None:
        with self._lock:
            self._counters.clear()


# Global default metrics instance that the library instruments.
METRICS = Metrics()


def looks_like_html(body: str | bytes | None) -> bool:
    """Cheap heuristic: does this body plausibly contain an HTML document?

    Used as a backstop before invoking the parser on obviously-non-HTML bytes
    (e.g. a mislabeled JSON error page).
    """
    if body is None:
        return False
    if isinstance(body, bytes):
        try:
            sample = body[:512].decode("utf-8", errors="ignore").lstrip().lower()
        except Exception:
            return False
    else:
        sample = body[:512].lstrip().lower()
    # Strip a leading BOM / doctype variants.
    return sample.startswith(("<!doctype html", "<html", "<head", "<body")) or "<html" in sample[:200]
