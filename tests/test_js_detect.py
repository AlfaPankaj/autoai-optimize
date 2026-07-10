from __future__ import annotations

from autoai_optimize.analyze.jsdetect import detect_js_rendered


def test_detects_small_shell_with_root_div_and_scripts():
    html = '<html><head><script src="app.js"></script><script src="vendor.js"></script></head><body><div id="app"></div></body></html>'
    assert detect_js_rendered(html) is True


def test_does_not_flag_normal_html():
    html = '<html><head></head><body><h1>Hello</h1><p>Welcome</p></body></html>'
    assert detect_js_rendered(html) is False


def test_detects_noscript_loader():
    html = '<html><head></head><body><noscript>Please enable JS</noscript></body></html>'
    assert detect_js_rendered(html) is True
