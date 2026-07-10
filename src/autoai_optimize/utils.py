"""Internal utilities: logging, content-type checks, small helpers."""

from __future__ import annotations

import logging

_logger: logging.Logger | None = None


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
    """A simple thread-safe LRU cache with TTL per entry.

    Usage:
        cache = LRUCache(max_size=1024, ttl_seconds=300)
        v = cache.get(k)
        cache.set(k, v)
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

    def _purge_expired(self) -> None:
        now = self._time.time()
        keys_to_delete: list[str] = []
        for k, (ts, _) in list(self._data.items()):
            if ts + self.ttl < now:
                keys_to_delete.append(k)
        for k in keys_to_delete:
            self._data.pop(k, None)

    def get(self, key: str) -> object | None:
        """Return value or None if missing/expired."""
        with self._lock:
            self._purge_expired()
            item = self._data.get(key)
            if item is None:
                return None
            _ts, val = item
            # Move to end as most recently used
            self._data.move_to_end(key)
            return val

    def set(self, key: str, value: object) -> None:
        """Set value for key and enforce max_size/TTL."""
        with self._lock:
            self._purge_expired()
            self._data[key] = (self._time.time(), value)
            self._data.move_to_end(key)
            # Evict oldest when over capacity
            while len(self._data) > self.max_size:
                self._data.popitem(last=False)

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
