"""Django middleware adapter.

USAGE:
    # settings.py
    MIDDLEWARE = [
        # ... existing middleware ...
        "autoai_optimize.frameworks.django.AutoAIMiddleware",
    ]

    # Optional: configure via settings
    AUTOAI_OPTIMIZE = {
        "enabled": True,
        "min_confidence": 0.5,
        "allow_paths": ["/blog/", "/shop/"],
        "deny_paths": ["/admin/"],
    }

HINTS (optional):
    Set an `autoai_hints` attribute on your view function:

        def product_detail(request, pk):
            product_detail.autoai_hints = {"type": "Product", "name": "Widget", "price": "29.99"}
            return render(request, "product.html", {...})

    Or set the X-AutoAI-Type response header inside the view:

        def product_detail(request, pk):
            response = render(request, "product.html", {...})
            response["X-AutoAI-Type"] = "Product"
            return response
"""

from __future__ import annotations

from typing import Any

from django.conf import settings  # type: ignore
from django.http import HttpRequest, HttpResponse  # type: ignore

from autoai_optimize.analyze.hints import HINT_HEADER
from autoai_optimize.config import Config
from autoai_optimize.core import optimize_html
from autoai_optimize.utils import get_logger, is_html_content_type

_log = get_logger()

# Settings key.
_SETTINGS_KEY = "AUTOAI_OPTIMIZE"


def _load_config() -> Config:
    """Build a Config from Django settings, falling back to defaults."""
    raw: dict[str, Any] = getattr(settings, _SETTINGS_KEY, {})
    if not isinstance(raw, dict):
        raw = {}
    return Config(
        enabled=raw.get("enabled", True),
        min_confidence=float(raw.get("min_confidence", 0.5)),
        allow_paths=tuple(raw.get("allow_paths", ())),
        deny_paths=tuple(raw.get("deny_paths", ())),
        inject_existing=bool(raw.get("inject_existing", True)),
    )


class AutoAIMiddleware:
    """Django middleware that auto-injects JSON-LD into HTML responses.

    Compatible with both old-style (MIDDLEWARE_CLASSES) and new-style
    (MIDDLEWARE) Django middleware.
    """

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response
        self.config = _load_config()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)

        if not isinstance(response, HttpResponse):
            return response

        content_type = response.get("Content-Type", "")
        if not is_html_content_type(content_type):
            return response

        path = request.path_info or request.get_full_path().split("?")[0]
        if hasattr(self.config, 'ai_endpoint') and path.startswith(self.config.ai_endpoint):
            # Opt-in only: the full catalog is an unauthenticated scraping
            # vector unless explicitly enabled.
            if not getattr(self.config, "serve_ai_endpoint", False):
                return response
            # Optional bearer auth.
            if self.config.ai_endpoint_key:
                provided = request.headers.get("Authorization", "")
                if provided != f"Bearer {self.config.ai_endpoint_key}":
                    from django.http import JsonResponse
                    return JsonResponse({"error": "unauthorized"}, status=401)

            import json
            import os

            from django.http import JsonResponse
            if os.path.exists("website_schemas.json"):
                with open("website_schemas.json", encoding="utf-8") as f:
                    return JsonResponse(json.load(f), safe=False)
            return JsonResponse({"status": "AI endpoint active. Run demo.py to generate schema."})
        if not self.config.path_allowed(path):
            return response

        hints = self._read_hints(request, response)
        content = getattr(response, "content", b"")

        try:
            html = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)
        except Exception:
            return response

        url = request.build_absolute_uri()
        enriched = optimize_html(html, url=url, hints=hints, config=self.config)

        if enriched is html:
            return response

        response.content = enriched.encode("utf-8")
        response["Content-Type"] = "text/html; charset=utf-8"
        # Remove Content-Length so Django re-calculates it for the new body.
        # HttpResponse has no .pop(); use dict-style deletion, guarded because
        # the header may be absent on some responses.
        try:
            del response["Content-Length"]
        except KeyError:
            pass
        return response

    # ------------------------------------------------------------------
    # Hint collection
    # ------------------------------------------------------------------

    def _read_hints(self, request: HttpRequest, response: HttpResponse) -> dict[str, Any] | None:
        """Collect hints from (priority order): response header, view attribute."""
        # 1. Response header set by the view.
        hint_header = response.get(HINT_HEADER)
        if hint_header:
            return {"type": hint_header}

        # 2. View function attribute.
        view_func = getattr(request, "resolver_match", None)
        if view_func is not None:
            func = getattr(view_func, "func", None)
            if func is None:
                func = getattr(view_func, "callable", None)
            if func is not None:
                hints = getattr(func, "autoai_hints", None)
                if isinstance(hints, dict):
                    return hints

        return None
