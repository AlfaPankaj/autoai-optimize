"""autoai-optimize: automatic Schema.org / JSON-LD injection for web apps.

Install once, get better Google rankings, voice-search readiness, and
AI-agent discoverability — zero manual structured-data work.

Public API:
    from src.autoai_optimize import Config, optimize_html
    from src.autoai_optimize.frameworks.fastapi import AutoAIMiddleware
    from src.autoai_optimize.frameworks.django import AutoAIMiddleware as DjangoMiddleware
"""

from __future__ import annotations

import importlib.metadata

from src.autoai_optimize.config import Config
from src.autoai_optimize.core import generate_jsonld, optimize_html

__all__ = ["Config", "__version__", "generate_jsonld", "optimize_html"]

try:
    __version__ = importlib.metadata.version("autoai-optimize")
except importlib.metadata.PackageNotFoundError:
    __version__ = "unknown"
