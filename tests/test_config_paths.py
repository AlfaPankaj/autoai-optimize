from __future__ import annotations

from autoai_optimize.config import Config


def test_deny_paths_take_precedence():
    cfg = Config(deny_paths=("/admin/",))
    assert not cfg.path_allowed("/admin/dashboard")
    assert cfg.path_allowed("/public/page")


def test_require_explicit_opt_in_blocks_sensitive_by_default():
    cfg = Config(require_explicit_opt_in=True, sensitive_paths=("/admin/",))
    assert not cfg.path_allowed("/admin/dashboard")


def test_require_explicit_opt_in_allows_when_whitelisted():
    # Use a sensitive path NOT in the default deny_paths to test the opt-in
    # logic independently. /admin/ is now denied by default, so we use
    # /private/ here.
    cfg = Config(
        require_explicit_opt_in=True,
        sensitive_paths=("/private/",),
        allow_paths=("/private/"),
    )
    assert cfg.path_allowed("/private/page")


def test_allow_paths_behavior_when_set():
    cfg = Config(allow_paths=("/shop/",))
    assert cfg.path_allowed("/shop/item")
    assert not cfg.path_allowed("/blog/post")
