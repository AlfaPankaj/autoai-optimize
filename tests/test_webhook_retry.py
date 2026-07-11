from __future__ import annotations

from urllib.error import URLError

from src.autoai_optimize.config import Config
from src.autoai_optimize.core import sync_updates


class DummyResp:
    def __init__(self, code=200):
        self._code = code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self._code


def test_sync_updates_retries_and_succeeds(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=5):
        calls.append(req)
        # Fail first two times, succeed third
        if len(calls) < 3:
            raise URLError("Temporary failure")
        return DummyResp(200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    cfg = Config(api_key="secret", webhook_url="http://example.local/hook")
    assert sync_updates(cfg) is True
    assert len(calls) == 3


def test_sync_updates_fails_without_key():
    cfg = Config(api_key=None, webhook_url="http://example.local/hook")
    assert sync_updates(cfg) is False


def test_sync_updates_returns_false_on_permanent_failure(monkeypatch):
    def bad_urlopen(req, timeout=5):
        raise URLError("Permanent failure")

    monkeypatch.setattr("urllib.request.urlopen", bad_urlopen)
    cfg = Config(api_key="secret", webhook_url="http://example.local/hook")
    assert sync_updates(cfg) is False
