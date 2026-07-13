from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from starlette.testclient import TestClient

from autoai_optimize.frameworks.fastapi import AutoAIMiddleware


def test_middleware_injects_jsonld():
    app = FastAPI()
    app.add_middleware(AutoAIMiddleware)

    @app.get("/page")
    async def page():
        return HTMLResponse('<html><head></head><body><h1>Hi</h1></body></html>', headers={"X-AutoAI-Type": "Article"})

    with TestClient(app) as client:
        r = client.get("/page")
        assert r.status_code == 200
        assert '<script type="application/ld+json">' in r.text


def test_middleware_non_html_passthrough():
    app = FastAPI()
    app.add_middleware(AutoAIMiddleware)

    @app.get("/text")
    async def t():
        return PlainTextResponse("ok")

    with TestClient(app) as client:
        r = client.get("/text")
        assert r.status_code == 200
        assert r.text == "ok"


def test_middleware_respects_deny_paths():
    app = FastAPI()
    # Disable processing for /admin
    from autoai_optimize.config import Config
    cfg = Config(deny_paths=("/admin/",))
    app.add_middleware(AutoAIMiddleware, config=cfg)

    @app.get("/admin/dashboard")
    async def admin():
        return HTMLResponse('<html><head></head><body><h1>Admin</h1></body></html>')

    with TestClient(app) as client:
        r = client.get("/admin/dashboard")
        assert r.status_code == 200
        assert '<script type="application/ld+json">' not in r.text
