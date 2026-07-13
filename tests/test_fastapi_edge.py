"""Edge-case tests for the FastAPI/Starlette middleware.

Targets the previously-uncovered branches in fastapi.py:
  - /api/ai endpoint interception (with and without website_schemas.json)
  - deny_paths enforcement
  - non-HTML passthrough
  - view-attribute hints
  - idempotency (already-injected page is not double-injected)
  - disabled config
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.testclient import TestClient

from autoai_optimize.config import Config
from autoai_optimize.frameworks.fastapi import AutoAIMiddleware

LD_MARKER = '<script type="application/ld+json">'

PRODUCT_HTML = (
    '<!doctype html><html><head><title>Widget</title></head>'
    '<body>'
    '<!-- @ai-entity:product -->'
    '<h1>Super Widget</h1>'
    '<p class="price">$19.99</p>'
    '<button>Add to Cart</button>'
    '</body></html>'
)


def _client_with_middleware(config: Config | None = None):
    app = FastAPI()
    if config is not None:
        app.add_middleware(AutoAIMiddleware, config=config)
    else:
        app.add_middleware(AutoAIMiddleware)
    return app


class TestAiEndpoint:
    def test_ai_endpoint_serves_schema_file(self, monkeypatch, tmp_path):
        schema = [{"@type": "Product", "name": "Widget"}]
        schema_file = tmp_path / "website_schemas.json"
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        # Opt-in required now (serve_ai_endpoint=True).
        app = _client_with_middleware(Config(serve_ai_endpoint=True))

        @app.get("/api/ai")
        async def ai():
            return HTMLResponse("should be intercepted")

        with TestClient(app) as client:
            r = client.get("/api/ai")
            assert r.status_code == 200
            body = r.json()
            assert isinstance(body, list)
            assert body[0]["name"] == "Widget"

    def test_ai_endpoint_without_file_returns_status(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        app = _client_with_middleware(Config(serve_ai_endpoint=True))

        @app.get("/api/ai")
        async def ai():
            return HTMLResponse("x")

        with TestClient(app) as client:
            r = client.get("/api/ai")
            assert r.status_code == 200
            assert "status" in r.json()

    def test_ai_endpoint_disabled_by_default(self, monkeypatch, tmp_path):
        """Security: /api/ai must NOT serve the catalog unless opted in."""
        (tmp_path / "website_schemas.json").write_text('[{"@type": "Product"}]', encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        # Default config -> serve_ai_endpoint=False -> endpoint is inert.
        app = _client_with_middleware(Config())

        @app.get("/api/ai")
        async def ai():
            return HTMLResponse("fallback page")

        with TestClient(app) as client:
            r = client.get("/api/ai")
            # Should fall through to the route, not serve the schema.
            assert "fallback page" in r.text
            assert r.json() if "json" in r.headers.get("content-type", "") else True

    def test_ai_endpoint_requires_bearer_key_when_set(self, monkeypatch, tmp_path):
        """When ai_endpoint_key is set, requests without it get 401."""
        (tmp_path / "website_schemas.json").write_text('[{"@type": "Product"}]', encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        app = _client_with_middleware(
            Config(serve_ai_endpoint=True, ai_endpoint_key="secret-key")
        )

        @app.get("/api/ai")
        async def ai():
            return HTMLResponse("x")

        with TestClient(app) as client:
            # No auth header -> 401.
            r1 = client.get("/api/ai")
            assert r1.status_code == 401
            # Wrong key -> 401.
            r2 = client.get("/api/ai", headers={"Authorization": "Bearer wrong"})
            assert r2.status_code == 401
            # Correct key -> 200 with schema.
            r3 = client.get("/api/ai", headers={"Authorization": "Bearer secret-key"})
            assert r3.status_code == 200


class TestPathFiltering:
    def test_deny_paths_blocks_enrichment(self):
        app = _client_with_middleware(Config(deny_paths=("/admin/",)))

        @app.get("/admin/dashboard")
        async def admin():
            return HTMLResponse(PRODUCT_HTML)

        with TestClient(app) as client:
            r = client.get("/admin/dashboard")
            assert LD_MARKER not in r.text

    def test_allow_paths_only_processes_listed(self):
        app = _client_with_middleware(Config(allow_paths=("/products/",)))

        @app.get("/products/widget")
        async def product():
            return HTMLResponse(PRODUCT_HTML)

        @app.get("/blog/post")
        async def blog():
            return HTMLResponse(PRODUCT_HTML)

        with TestClient(app) as client:
            assert LD_MARKER in client.get("/products/widget").text
            assert LD_MARKER not in client.get("/blog/post").text


class TestNonHtmlPassthrough:
    def test_json_response_untouched(self):
        app = _client_with_middleware()

        @app.get("/api/data")
        async def data():
            return JSONResponse({"ok": True})

        with TestClient(app) as client:
            r = client.get("/api/data")
            assert r.json() == {"ok": True}
            assert LD_MARKER not in r.text

    def test_plain_text_untouched(self):
        app = _client_with_middleware()

        @app.get("/text")
        async def text():
            return PlainTextResponse("hello world")

        with TestClient(app) as client:
            r = client.get("/text")
            assert r.text == "hello world"


class TestHintPaths:
    def test_route_function_attribute_hint(self):
        app = _client_with_middleware()

        @app.get("/products/{id}")
        async def get_product(id: int):
            return HTMLResponse(
                '<html><head></head><body>'
                '<h1>Widget</h1><p>$42.00</p>'
                '</body></html>'
            )

        # Attach explicit hints to the route function.
        get_product.autoai_hints = {"type": "Product", "name": "Widget", "price": "42.00"}

        with TestClient(app) as client:
            r = client.get("/products/1")
            assert LD_MARKER in r.text
            assert '"Product"' in r.text


class TestDisabledConfig:
    def test_disabled_does_not_enrich(self):
        app = _client_with_middleware(Config(enabled=False))

        @app.get("/products/widget")
        async def product():
            return HTMLResponse(PRODUCT_HTML)

        with TestClient(app) as client:
            r = client.get("/products/widget")
            assert LD_MARKER not in r.text


class TestIdempotency:
    def test_already_injected_page_not_double_injected(self):
        # A page that already carries the JSON-LD should not get a duplicate.
        node = {"@type": "Product", "name": "Super Widget", "url": "/products/widget"}
        pre = (
            '<!doctype html><html><head>'
            f'<script type="application/ld+json">{json.dumps(node)}</script>'
            '</head><body><h1>Super Widget</h1><p>$19.99</p>'
            '<button>Add to Cart</button></body></html>'
        )
        app = _client_with_middleware(Config(inject_existing=True))

        @app.get("/products/widget")
        async def product():
            return HTMLResponse(pre)

        with TestClient(app) as client:
            r = client.get("/products/widget")
            # Exactly one ld+json script, not two.
            assert r.text.count(LD_MARKER) == 1
