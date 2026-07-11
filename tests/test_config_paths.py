from __future__ import annotations

from src.autoai_optimize.config import Config


def test_deny_paths_take_precedence():
    cfg = Config(deny_paths=("/admin/",))
    assert not cfg.path_allowed("/admin/dashboard")
    assert cfg.path_allowed("/public/page")


def test_require_explicit_opt_in_blocks_sensitive_by_default():
    cfg = Config(require_explicit_opt_in=True, sensitive_paths=("/admin/",))
    assert not cfg.path_allowed("/admin/dashboard")


def test_require_explicit_opt_in_allows_when_whitelisted():
    cfg = Config(require_explicit_opt_in=True, sensitive_paths=("/admin/",), allow_paths=("/admin/",))
    assert cfg.path_allowed("/admin/dashboard")


def test_allow_paths_behavior_when_set():
    cfg = Config(allow_paths=("/shop/",))
    assert cfg.path_allowed("/shop/item")
    assert not cfg.path_allowed("/blog/post")
