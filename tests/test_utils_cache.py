from __future__ import annotations

import time

from src.autoai_optimize.utils import LRUCache


def test_lru_cache_set_get_and_ttl():
    cache = LRUCache(max_size=3, ttl_seconds=1)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1
    assert cache.get("b") == 2

    # Wait for TTL to expire
    time.sleep(1.1)
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_lru_eviction_order():
    cache = LRUCache(max_size=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    # Access a to make it most-recently-used
    assert cache.get("a") == 1
    # Insert c, should evict b
    cache.set("c", 3)
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3
