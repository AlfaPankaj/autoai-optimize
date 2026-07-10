"""Abstract adapter contract.

Every framework adapter (FastAPI, Django, Flask, ...) implements a thin
translation layer:

    incoming request  ->  (html, url, context, hints)  ->  core.optimize_html()
    outgoing response <-  enriched html               <-

The shared core does all the heavy lifting; adapters only handle
framework-specific response rewriting and header management.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """Interface for framework middleware adapters."""

    @abstractmethod
    def should_process(self, path: str, content_type: str | None) -> bool:
        """Return True if this request/response should be enriched."""

    @abstractmethod
    def extract_hints(self, extra: Any) -> dict[str, Any] | None:
        """Pull developer hints from a framework-specific source.

        `extra` is whatever the adapter has access to (a request object,
        view attributes, route metadata, etc.). May return None when
        no hints are present.
        """


def should_process_path(config: Any, path: str) -> bool:
    """Default path-filtering logic shared by all adapters."""
    return bool(config.path_allowed(path))
