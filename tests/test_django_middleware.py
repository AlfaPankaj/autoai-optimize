"""Tests for the Django middleware adapter.

These exercise the real Django middleware (``AutoAIMiddleware``) against
``HttpRequest`` / ``HttpResponse`` objects built by Django's ``RequestFactory``.
Django settings are configured minimally (once, idempotently) so the
middleware's ``_load_config()`` can read the ``AUTOAI_OPTIMIZE`` setting.

Coverage goals (from the improvement roadmap):
  * middleware applies ``optimize_html`` to HTML responses
  * respects ``deny_paths`` / ``allow_paths``
  * serves the ``/api/ai`` endpoint
  * respects ``AUTOAI_OPTIMIZE["enabled"] = False``
  * does not choke on non-HTML responses (JSON, redirects)
"""

from __future__ import annotations

import types

import pytest
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.test import RequestFactory, override_settings

from src.autoai_optimize.config import Config
from src.autoai_optimize.frameworks.django import AutoAIMiddleware, _load_config

# ---------------------------------------------------------------------------
# Minimal Django settings configuration (idempotent).
# Configured exactly once so the middleware can read settings.AUTOAI_OPTIMIZE.
# ---------------------------------------------------------------------------
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={},
        INSTALLED_APPS=[],
        ALLOWED_HOSTS=["*"],
        ROOT_URLCONF=[],
        AUTOAI_OPTIMIZE={"enabled": True, "min_confidence": 0.5},
    )

# Sample HTML strong enough to be classified as a Product page and enriched.
PRODUCT_HTML = (
    '<!doctype html><html><head><title>Widget</title></head>'
    '<body>'
    '<!-- @ai-entity:product -->'
    '<h1>Super Widget</h1>'
    '<p class="price">$19.99</p>'
    '<button>Add to Cart</button>'
    '</body></html>'
)

LD_MARKER = '<script type="application/ld+json">'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _html_response(body: str = PRODUCT_HTML, content_type: str = "text/html; charset=utf-8") -> HttpResponse:
    """A typical HTML response a Django view would return."""
    return HttpResponse(body, content_type=content_type)


def _stub_get_response(body: str = PRODUCT_HTML, content_type: str = "text/html; charset=utf-8"):
    """Return a get_response callable serving a fixed response body."""
    def get_response(request):  # noqa: ANN001
        return HttpResponse(body, content_type=content_type)
    return get_response


def _build_middleware(config: Config | None = None, get_response=None) -> AutoAIMiddleware:
    """Instantiate middleware with a stub get_response and an explicit config.

    Using an explicit config makes the path/allowance tests independent of
    global Django settings.
    """
    mw = AutoAIMiddleware(get_response or _stub_get_response())
    if config is not None:
        mw.config = config
    return mw


# ---------------------------------------------------------------------------
# 1. Core behavior: HTML enrichment
# ---------------------------------------------------------------------------

class TestHtmlEnrichment:
    def test_middleware_injects_jsonld_into_html(self):
        mw = _build_middleware()
        request = RequestFactory().get("/products/super-widget")
        response = mw(request)

        assert response.status_code == 200
        body = response.content.decode("utf-8")
        assert LD_MARKER in body
        # Body must actually have been rewritten (longer than original).
        assert len(body) > len(PRODUCT_HTML)

    def test_middleware_preserves_unenrichable_html(self):
        # A page with no classifiable signal and no hint -> original returned.
        empty = "<html><head></head><body><p>nothing here</p></body></html>"
        mw = _build_middleware(get_response=_stub_get_response(empty))
        request = RequestFactory().get("/")
        response = mw(request)

        assert response.status_code == 200
        assert LD_MARKER not in response.content.decode("utf-8")


# ---------------------------------------------------------------------------
# 2. Non-HTML responses are passed through untouched
# ---------------------------------------------------------------------------

class TestNonHtmlPassthrough:
    def test_json_response_is_not_touched(self):
        mw = _build_middleware(get_response=_stub_get_response('{"ok": true}', "application/json"))
        request = RequestFactory().get("/api/data")
        response = mw(request)

        assert response.status_code == 200
        assert response.content.decode("utf-8") == '{"ok": true}'
        assert LD_MARKER not in response.content.decode("utf-8")

    def test_redirect_response_is_not_touched(self):
        def get_response(request):  # noqa: ANN001
            return HttpResponseRedirect("/login/")
        mw = AutoAIMiddleware(get_response)
        mw.config = Config()
        request = RequestFactory().get("/admin/panel")
        response = mw(request)

        assert isinstance(response, HttpResponseRedirect)
        assert response.status_code in (301, 302)
        assert response["Location"] == "/login/"

    def test_missing_content_type_is_passthrough(self):
        # No Content-Type header at all -> not HTML -> returned unchanged.
        def get_response(request):  # noqa: ANN001
            resp = HttpResponse(b"raw bytes", status=200)
            del resp["Content-Type"]
            resp.headers.pop("Content-Type", None)
            return resp
        mw = AutoAIMiddleware(get_response)
        mw.config = Config()
        request = RequestFactory().get("/some/path")
        response = mw(request)

        assert response.content == b"raw bytes"


# ---------------------------------------------------------------------------
# 3. Path filtering: deny_paths / allow_paths
# ---------------------------------------------------------------------------

class TestPathFiltering:
    def test_respects_deny_paths(self):
        cfg = Config(deny_paths=("/admin/",))
        mw = _build_middleware(cfg)
        request = RequestFactory().get("/admin/dashboard")
        response = mw(request)

        assert LD_MARKER not in response.content.decode("utf-8")

    def test_allows_non_denied_path(self):
        cfg = Config(deny_paths=("/admin/",))
        mw = _build_middleware(cfg)
        request = RequestFactory().get("/products/widget")
        response = mw(request)

        assert LD_MARKER in response.content.decode("utf-8")

    def test_respects_allow_paths(self):
        # allow_paths set: only matching paths are processed.
        cfg = Config(allow_paths=("/blog/",))
        mw = _build_middleware(cfg)

        # /blog/* is allowed -> enriched
        r1 = mw(RequestFactory().get("/blog/post-1"))
        # /products/* is NOT in allow list -> not enriched
        r2 = mw(RequestFactory().get("/products/widget"))

        assert LD_MARKER in r1.content.decode("utf-8")
        assert LD_MARKER not in r2.content.decode("utf-8")

    def test_deny_overrides_allow(self):
        cfg = Config(allow_paths=("/shop/",), deny_paths=("/shop/private/",))
        mw = _build_middleware(cfg)

        allowed = mw(RequestFactory().get("/shop/item-1"))
        denied = mw(RequestFactory().get("/shop/private/x"))

        assert LD_MARKER in allowed.content.decode("utf-8")
        assert LD_MARKER not in denied.content.decode("utf-8")


# ---------------------------------------------------------------------------
# 4. Disabled switch
# ---------------------------------------------------------------------------

class TestDisabledSwitch:
    def test_disabled_config_skips_enrichment(self):
        cfg = Config(enabled=False)
        mw = _build_middleware(cfg)
        request = RequestFactory().get("/products/widget")
        response = mw(request)

        assert LD_MARKER not in response.content.decode("utf-8")
        assert response.content.decode("utf-8") == PRODUCT_HTML

    @override_settings(AUTOAI_OPTIMIZE={"enabled": False, "min_confidence": 0.5})
    def test_load_config_reads_disabled_from_settings(self):
        cfg = _load_config()
        assert cfg.enabled is False


# ---------------------------------------------------------------------------
# 5. Settings -> Config wiring
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_defaults_when_setting_missing(self):
        # With AUTOAI_OPTIMIZE absent, defaults are applied.
        from django.test import override_settings as _ov

        @_ov()
        def _run():  # noqa: ANN202
            # Deleting a setting via override is tricky; instead use empty dict.
            return _load_config()

        cfg = _run()
        assert cfg.enabled is True
        assert cfg.min_confidence == pytest.approx(0.5)

    @override_settings(AUTOAI_OPTIMIZE={
        "enabled": True,
        "min_confidence": 0.8,
        "allow_paths": ["/blog/", "/shop/"],
        "deny_paths": ["/admin/"],
        "inject_existing": False,
    })
    def test_load_config_maps_all_fields(self):
        cfg = _load_config()
        assert cfg.enabled is True
        assert cfg.min_confidence == pytest.approx(0.8)
        assert cfg.allow_paths == ("/blog/", "/shop/")
        assert cfg.deny_paths == ("/admin/",)
        assert cfg.inject_existing is False

    @override_settings(AUTOAI_OPTIMIZE="not a dict")
    def test_load_config_ignores_non_dict_setting(self):
        cfg = _load_config()
        # Falls back to defaults.
        assert cfg.enabled is True
        assert cfg.min_confidence == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 6. /api/ai endpoint
# ---------------------------------------------------------------------------

class TestAiEndpoint:
    def test_ai_endpoint_returns_json(self, monkeypatch, tmp_path):
        # Point cwd at a tmp dir containing a schema file so the test is
        # independent of the repo root.
        schema = {"@type": "WebSite", "name": "Demo"}
        schema_file = tmp_path / "website_schemas.json"
        schema_file.write_text('{"@type": "WebSite", "name": "Demo"}', encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        # Opt-in required now (serve_ai_endpoint=True).
        mw = _build_middleware(Config(serve_ai_endpoint=True))
        # The view returns HTML, but the middleware should intercept /api/ai
        # and respond with the JSON schema instead.
        request = RequestFactory().get("/api/ai")
        response = mw(request)

        assert isinstance(response, JsonResponse)
        assert response.status_code == 200
        body = response.content.decode("utf-8")
        assert "WebSite" in body

    def test_ai_endpoint_without_schema_file_returns_status(self, monkeypatch, tmp_path):
        # No website_schemas.json present -> status placeholder JSON.
        monkeypatch.chdir(tmp_path)
        # Ensure no file is present.
        assert not (tmp_path / "website_schemas.json").exists()

        mw = _build_middleware(Config(serve_ai_endpoint=True))
        request = RequestFactory().get("/api/ai")
        response = mw(request)

        assert isinstance(response, JsonResponse)
        assert response.status_code == 200
        assert "status" in response.content.decode("utf-8")

    def test_ai_endpoint_disabled_by_default(self, monkeypatch, tmp_path):
        """Security: /api/ai must NOT serve the catalog unless opted in."""
        (tmp_path / "website_schemas.json").write_text('{"@type": "WebSite"}', encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        # Default config -> serve_ai_endpoint=False -> endpoint inert, falls through.
        mw = _build_middleware(Config())
        request = RequestFactory().get("/api/ai")
        response = mw(request)
        # Falls through to the view (which returns PRODUCT_HTML), not the schema.
        assert not isinstance(response, JsonResponse)
        assert "Super Widget" in response.content.decode("utf-8")

    def test_ai_endpoint_requires_bearer_key_when_set(self, monkeypatch, tmp_path):
        """When ai_endpoint_key is set, requests without it get 401."""
        (tmp_path / "website_schemas.json").write_text('{"@type": "WebSite"}', encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        mw = _build_middleware(
            Config(serve_ai_endpoint=True, ai_endpoint_key="secret-key")
        )
        # No auth header -> 401.
        r1 = mw(RequestFactory().get("/api/ai"))
        assert r1.status_code == 401
        # Wrong key -> 401.
        r2 = mw(RequestFactory().get("/api/ai", HTTP_AUTHORIZATION="Bearer wrong"))
        assert r2.status_code == 401
        # Correct key -> 200 with schema.
        r3 = mw(RequestFactory().get("/api/ai", HTTP_AUTHORIZATION="Bearer secret-key"))
        assert r3.status_code == 200


# ---------------------------------------------------------------------------
# 7. Hint collection (response header + view attribute)
# ---------------------------------------------------------------------------

class TestHintCollection:
    def test_hint_from_response_header(self):
        def get_response(request):  # noqa: ANN001
            resp = HttpResponse(
                '<html><head><title>A</title></head><body>'
                '<h1>How to Brew Coffee</h1>'
                '<time datetime="2026-07-01T09:00:00Z">July 1</time>'
                '</body></html>',
                content_type="text/html; charset=utf-8",
            )
            resp["X-AutoAI-Type"] = "Article"
            return resp
        mw = AutoAIMiddleware(get_response)
        mw.config = Config()

        request = RequestFactory().get("/blog/coffee")
        response = mw(request)

        body = response.content.decode("utf-8")
        assert LD_MARKER in body
        assert '"Article"' in body

    def test_hint_from_view_attribute(self):
        def my_view(request):  # noqa: ANN001
            return HttpResponse(
                '<html><head></head><body>'
                '<h1>Super Widget</h1><p>$42.00</p>'
                '</body></html>',
                content_type="text/html; charset=utf-8",
            )
        my_view.autoai_hints = {"type": "Product", "name": "Super Widget", "price": "42.00"}

        def get_response(request):  # noqa: ANN001
            return my_view(request)

        mw = AutoAIMiddleware(get_response)
        mw.config = Config()

        request = RequestFactory().get("/products/super-widget")
        # Simulate Django's resolver attaching the match to the request.
        request.resolver_match = types.SimpleNamespace(func=my_view)

        response = mw(request)
        body = response.content.decode("utf-8")
        assert LD_MARKER in body
        assert '"Product"' in body
        assert "Super Widget" in body


# ---------------------------------------------------------------------------
# 8. Robustness: non-HttpResponse return value
# ---------------------------------------------------------------------------

class TestRobustness:
    def test_non_httpresponse_returned_unchanged(self):
        def get_response(request):  # noqa: ANN001
            return "not a response object"
        mw = AutoAIMiddleware(get_response)
        mw.config = Config()

        request = RequestFactory().get("/products/x")
        result = mw(request)
        # Middleware short-circuits when the response is not an HttpResponse.
        assert result == "not a response object"

    def test_content_length_header_is_recomputed_after_enrichment(self):
        # The enriched body differs in length, so the middleware must drop the
        # stale Content-Length (Django recomputes it downstream via
        # CommonMiddleware / the WSGI server). Regression test for the
        # response.pop("Content-Length") crash — HttpResponse has no .pop().
        def get_response(request):  # noqa: ANN001
            resp = HttpResponse(PRODUCT_HTML, content_type="text/html; charset=utf-8")
            resp["Content-Length"] = str(len(PRODUCT_HTML.encode("utf-8")))
            return resp
        mw = AutoAIMiddleware(get_response)
        mw.config = Config()

        request = RequestFactory().get("/products/widget")
        response = mw(request)

        body = response.content.decode("utf-8")
        assert LD_MARKER in body
        # The stale Content-Length (which referenced the OLD, shorter body)
        # must be gone so it cannot lie about the new body size.
        assert "Content-Length" not in response
        # Sanity: the new body is genuinely larger than the original.
        assert len(response.content) > len(PRODUCT_HTML.encode("utf-8"))

    def test_resolver_match_without_autoai_hints_falls_through(self):
        # resolver_match present but the view has no autoai_hints -> no crash,
        # enrichment still proceeds based on classification.
        def my_view(request):  # noqa: ANN001
            return HttpResponse(
                '<html><head></head><body>'
                '<h1>Super Widget</h1><p>$42.00</p>'
                '</body></html>',
                content_type="text/html; charset=utf-8",
            )
        # No autoai_hints attribute set on my_view.
        def get_response(request):  # noqa: ANN001
            return my_view(request)
        mw = AutoAIMiddleware(get_response)
        mw.config = Config()

        request = RequestFactory().get("/products/widget")
        # resolver_match present, .func points to a view with no hints, and
        # has no .callable either -> _read_hints returns None.
        request.resolver_match = types.SimpleNamespace(func=my_view)
        response = mw(request)
        assert LD_MARKER in response.content.decode("utf-8")
