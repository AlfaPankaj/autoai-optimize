"""Configuration for autoai-optimize.

Zero-config by default: sensible thresholds so the library does the right
thing out of the box. Override only what you need.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    """Runtime configuration.

    Attributes:
        enabled: Master switch. When False, optimize_html returns input untouched.
        min_confidence: Minimum detection confidence (0.0–1.0) to emit schema.
            Below this the library stays silent — wrong schema can trigger
            Google penalties, so silence is always safe.
        allow_paths: Optional allow-list of URL path prefixes (e.g. ["/blog/"]).
            When set, only matching paths are processed. Empty = process all.
        deny_paths: Deny-list of URL path prefixes. Checked before allow_paths.
        inject_existing: If True and a page already has JSON-LD of the same
            @type, leave it untouched (idempotent). Recommended True.
    """

    enabled: bool = True
    min_confidence: float = 0.5
    allow_paths: tuple[str, ...] = ()
    deny_paths: tuple[str, ...] = ("/admin/", "/dashboard/", "/user/")
    # When True, requires paths listed in sensitive_paths to be explicitly
    # present in allow_paths before processing. Useful for large sites where
    # certain prefixes (e.g., /admin/, /user/) must never be auto-scanned
    # unless explicitly opted-in.
    require_explicit_opt_in: bool = False
    sensitive_paths: tuple[str, ...] = ("/admin/", "/dashboard/", "/user/")
    inject_existing: bool = True
    api_key: str | None = None
    webhook_url: str = "https://api.autoai-optimize.com/webhook"
    ai_endpoint: str = "/api/ai"
    # When False (default), the /api/ai endpoint is disabled and requests to it
    # fall through to the app. Set True to serve website_schemas.json. The full
    # catalog exposes every product/article URL on the site, so it's opt-in to
    # avoid creating an unauthenticated competitor-scraping vector.
    serve_ai_endpoint: bool = False
    # When set, requests to /api/ai must carry `Authorization: Bearer <key>`
    # matching this value. None = no auth required (use only behind a proxy).
    ai_endpoint_key: str | None = None
    # Reserved for future per-schema enable flags; kept to avoid config churn.
    _reserved: tuple[str, ...] = field(default=())

    def path_allowed(self, path: str) -> bool:
        """Return True if `path` should be processed under this config.

        Order of checks:
        1. deny_paths (deny overrides everything)
        2. if require_explicit_opt_in and path matches a sensitive prefix -> only
           allowed if present in allow_paths
        3. allow_paths (if empty, allow all non-denied)
        """
        if any(path.startswith(p) for p in self.deny_paths):
            return False

        if self.require_explicit_opt_in and any(path.startswith(p) for p in self.sensitive_paths):
            # Only allowed when the path is explicitly whitelisted.
            return any(path.startswith(p) for p in self.allow_paths)

        if not self.allow_paths:
            return True
        return any(path.startswith(p) for p in self.allow_paths)


DEFAULT_CONFIG = Config()
