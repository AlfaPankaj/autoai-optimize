"""Direct tests for the shared framework adapter contract.

``frameworks/base.py`` defines:
  * ``BaseAdapter`` — abstract base that every framework adapter implements.
  * ``should_process_path(config, path)`` — default path-filtering logic
    shared by all adapters (delegates to ``config.path_allowed``).

These tests exercise the shared logic directly, independent of FastAPI /
Django, so framework-specific tests aren't the only thing covering it.
"""

from __future__ import annotations

import pytest

from src.autoai_optimize.config import Config
from src.autoai_optimize.frameworks.base import BaseAdapter, should_process_path


# ---------------------------------------------------------------------------
# should_process_path — the shared path-filtering helper
# ---------------------------------------------------------------------------

class TestShouldProcessPath:
    def test_allows_unrestricted_path_by_default(self):
        # Default config: no allow/deny lists -> everything allowed.
        cfg = Config()
        assert should_process_path(cfg, "/anything/here") is True
        assert should_process_path(cfg, "/") is True

    def test_denied_path_is_blocked(self):
        cfg = Config(deny_paths=("/admin/",))
        assert should_process_path(cfg, "/admin/dashboard") is False

    def test_non_denied_path_passes(self):
        cfg = Config(deny_paths=("/admin/",))
        assert should_process_path(cfg, "/products/widget") is True

    def test_allow_list_blocks_unlisted_paths(self):
        cfg = Config(allow_paths=("/blog/",))
        assert should_process_path(cfg, "/blog/post-1") is True
        assert should_process_path(cfg, "/products/widget") is False

    def test_deny_overrides_allow(self):
        cfg = Config(allow_paths=("/shop/",), deny_paths=("/shop/private/",))
        assert should_process_path(cfg, "/shop/item-1") is True
        assert should_process_path(cfg, "/shop/private/x") is False

    def test_returns_bool_not_truthy_value(self):
        # path_allowed returns a real bool; should_process_path must preserve
        # that contract so adapters can rely on `is True` checks.
        cfg = Config()
        result = should_process_path(cfg, "/x")
        assert isinstance(result, bool)
        assert result is True

    def test_sensitive_path_requires_explicit_opt_in(self):
        # With require_explicit_opt_in, a sensitive /admin path is only
        # allowed if it's also in allow_paths.
        cfg = Config(
            require_explicit_opt_in=True,
            sensitive_paths=("/admin/",),
        )
        # /admin/private is sensitive and NOT in allow_paths -> blocked.
        assert should_process_path(cfg, "/admin/private/page") is False
        # /admin/public is sensitive and explicitly allowed -> passes.
        cfg_allowed = Config(
            require_explicit_opt_in=True,
            sensitive_paths=("/admin/",),
            allow_paths=("/admin/public/",),
        )
        assert should_process_path(cfg_allowed, "/admin/public/page") is True


# ---------------------------------------------------------------------------
# BaseAdapter — abstract contract enforcement
# ---------------------------------------------------------------------------

class TestBaseAdapterContract:
    def test_cannot_instantiate_abstract_base_directly(self):
        # BaseAdapter declares abstract methods, so it must not be instantiable
        # without concrete implementations.
        with pytest.raises(TypeError):
            BaseAdapter()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_abstract_methods(self):
        # A subclass missing an abstract method still can't be instantiated.
        class Partial(BaseAdapter):
            def should_process(self, path, content_type=None):
                return True
            # extract_hints missing

        with pytest.raises(TypeError):
            Partial()  # type: ignore[abstract]

    def test_fully_implemented_subclass_instantiates(self):
        class ConcreteAdapter(BaseAdapter):
            def should_process(self, path, content_type=None):
                return path.startswith("/blog/")

            def extract_hints(self, extra):
                if isinstance(extra, dict) and "type" in extra:
                    return {"type": extra["type"]}
                return None

        adapter = ConcreteAdapter()
        assert adapter.should_process("/blog/post") is True
        assert adapter.should_process("/shop/item") is False
        assert adapter.extract_hints({"type": "Article"}) == {"type": "Article"}
        assert adapter.extract_hints(None) is None

    def test_should_process_accepts_optional_content_type(self):
        # The abstract signature includes an optional content_type; concrete
        # adapters should be able to consult it without type errors.
        class ContentTypeAdapter(BaseAdapter):
            def should_process(self, path, content_type=None):
                if content_type is None:
                    return True
                return "html" in content_type

            def extract_hints(self, extra):
                return None

        adapter = ContentTypeAdapter()
        assert adapter.should_process("/x", "text/html; charset=utf-8") is True
        assert adapter.should_process("/x", "application/json") is False
        assert adapter.should_process("/x") is True  # None content-type

    def test_should_process_path_delegates_to_path_allowed(self):
        # The module-level helper is a thin wrapper over config.path_allowed;
        # it must agree with it on identical inputs.
        configs = [
            Config(),
            Config(deny_paths=("/admin/",)),
            Config(allow_paths=("/blog/",)),
            Config(allow_paths=("/shop/",), deny_paths=("/shop/private/",)),
        ]
        paths = ["/", "/admin/x", "/blog/y", "/shop/z", "/shop/private/w"]
        for cfg in configs:
            for path in paths:
                assert should_process_path(cfg, path) == cfg.path_allowed(path)
