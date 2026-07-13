"""FastAPI / Starlette middleware adapter.

USAGE (FastAPI):
    from autoai_optimize.frameworks.fastapi import AutoAIMiddleware

    app = FastAPI()
    app.add_middleware(AutoAIMiddleware)

USAGE (plain Starlette):
    from starlette.applications import Starlette
    from autoai_optimize.frameworks.fastapi import AutoAIMiddleware

    app = Starlette()
    app.add_middleware(AutoAIMiddleware)

HINTS (optional):
    Set the X-AutoAI-Type response header inside a route, or attach an
    `autoai_hints` attribute to the route function:

        @app.get("/products/{id}")
        async def get_product(id: int):
            get_product.autoai_hints = {"type": "Product", "name": "Widget", "price": "29.99"}
            return HTMLResponse(...)

    Or in a dependency:
        from autoai_optimize.frameworks.fastapi import ai_hints

        @app.get("/blog/{slug}")
        async def get_post(slug: str, hints=Depends(ai_hints)):
            hints.set({"type": "Article"})
            return HTMLResponse(...)
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint  # type: ignore
from starlette.requests import Request  # type: ignore
from starlette.responses import Response  # type: ignore
from starlette.routing import Match  # type: ignore

from autoai_optimize.analyze.hints import HINT_HEADER
from autoai_optimize.config import Config
from autoai_optimize.core import optimize_html
from autoai_optimize.utils import get_logger, is_html_content_type

_log = get_logger()


class AutoAIMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    """Starlette-compatible middleware that auto-injects JSON-LD into HTML responses.

    This middleware is ASGI/async friendly: heavy CPU-bound parsing and HTML
    enrichment are executed in a threadpool so the event loop is not blocked.
    """

    def __init__(
        self,
        app: Any,
        config: Config | None = None,
    ) -> None:
        super().__init__(app)
        self.config = config or Config()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        if not is_html_content_type(content_type):
            return response

        path = request.url.path
        if path.startswith(self.config.ai_endpoint):
            # Opt-in only: the full catalog is an unauthenticated scraping
            # vector unless explicitly enabled.
            if not getattr(self.config, "serve_ai_endpoint", False):
                return response
            # Optional bearer auth.
            if self.config.ai_endpoint_key:
                provided = request.headers.get("authorization", "")
                if provided != f"Bearer {self.config.ai_endpoint_key}":
                    from starlette.responses import JSONResponse
                    return JSONResponse({"error": "unauthorized"}, status_code=401)

            import json
            import os

            from starlette.responses import JSONResponse
            if os.path.exists("website_schemas.json"):
                with open("website_schemas.json", encoding="utf-8") as f:
                    return JSONResponse(json.load(f))
            return JSONResponse({"status": "AI endpoint active. Run demo.py to generate schema."})

        if not self.config.path_allowed(path):
            return response

        # Collect hints from route function attributes or headers.
        hints = self._read_hints(request, response)

        # Read body, optimize, rewrite.
        body = getattr(response, "body", None)
        streamed = False
        if body is None:
            # Streaming responses: read, rewrite, return a plain Response.
            streamed = True
            chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            raw = b"".join(chunks)
        else:
            raw = body

        try:
            html = raw.decode("utf-8", errors="replace")
        except Exception:
            # If we consumed a streaming body, restore it to a fresh response.
            if streamed:
                from starlette.responses import Response as _R

                return _R(content=raw, status_code=response.status_code, headers=dict(response.headers), media_type=response.media_type)
            return response

        url = str(request.url)
        # Offload optimize_html to a threadpool to avoid blocking the event loop.
        loop = asyncio.get_running_loop()
        func = functools.partial(optimize_html, html, url, context=None, hints=hints, config=self.config)
        try:
            enriched = await loop.run_in_executor(None, func)
        except Exception:
            _log.exception("autoai-optimize: async enrichment failed")
            # If streaming response was consumed, return original bytes to avoid losing content.
            if streamed:
                from starlette.responses import Response as _R

                hdrs = dict(response.headers)
                if "content-length" in hdrs:
                    hdrs.pop("content-length")
                return _R(content=raw, status_code=response.status_code, headers=hdrs, media_type=response.media_type)
            return response

        if enriched is html:
            # Nothing changed; ensure we return the original content. For streamed
            # responses the original response.body_iterator was consumed so return
            # a fresh Response containing the original raw bytes.
            if streamed:
                from starlette.responses import Response as _R

                hdrs = dict(response.headers)
                if "content-length" in hdrs:
                    hdrs.pop("content-length")
                return _R(content=raw, status_code=response.status_code, headers=hdrs, media_type=response.media_type)
            return response  # Nothing changed.

        enriched_bytes = enriched.encode("utf-8")
        if "content-length" in response.headers:
            del response.headers["content-length"]
        # Starlette Response.init_headers expects no args here; call to ensure
        # headers are prepared (keep compatibility with multiple versions).
        import contextlib

        with contextlib.suppress(TypeError):
            response.init_headers(response.headers)
        # Workaround: Starlette BaseHTTPMiddleware doesn't easily let us replace
        # the streaming body, so return a fresh Response.
        from starlette.responses import Response as _R

        return _R(
            content=enriched_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type="text/html; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Hint collection
    # ------------------------------------------------------------------

    def _read_hints(self, request: Request, response: Response) -> dict[str, Any] | None:
        """Collect hints from (priority order): response header, route attribute."""
        # 1. Response header set by the route handler.
        hint_header = response.headers.get(HINT_HEADER)
        if hint_header:
            return {"type": hint_header}

        # 2. Route function attribute.
        route_func = self._get_route_function(request)
        if route_func is not None:
            hints = getattr(route_func, "autoai_hints", None)
            if isinstance(hints, dict):
                return hints

        return None

    @staticmethod
    def _get_route_function(request: Request) -> Callable[..., Any] | None:
        """Best-effort: find the actual endpoint function on the matched route."""
        try:
            for route in request.app.routes:
                match, _child_scope = route.matches(request.scope)
                if match == Match.FULL:
                    return getattr(route, "endpoint", None)
        except Exception:
            pass
        return None


# ------------------------------------------------------------------
# Optional helper: dependency for setting hints mid-request
# ------------------------------------------------------------------

class _HintCarrier:
    """Mutable container that a route can populate via a FastAPI Depends."""

    def __init__(self) -> None:
        self._hints: dict[str, Any] | None = None

    def set(self, hints: dict[str, Any]) -> None:
        self._hints = hints

    def get(self) -> dict[str, Any] | None:
        return self._hints


def ai_hints() -> _HintCarrier:
    """FastAPI dependency that returns a mutable hint carrier.

    Usage::

        @app.get("/blog/{slug}")
        async def get_post(slug: str, hints=Depends(ai_hints)):
            hints.set({"type": "Article", "headline": slug.replace("-", " ").title()})
            return HTMLResponse(...)
    """
    return _HintCarrier()
