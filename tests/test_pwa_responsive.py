"""Regression coverage for YasinHub PWA responsive/mobile fix.

Static cascade verification (no browser in CI): asserts the root causes
from docs/audits/yasinhub-pwa-mobile-audit.md stay fixed --
header/drawer/backdrop geometry, mobile padding cascade, overflow
containment, dvh fallback, breakpoints, card grids -- while desktop
rules, retired-service filtering and summary counters are untouched.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "dashboard"


def _r(name: str) -> str:
    return (D / name).read_text(encoding="utf-8")


def test_header_has_no_fixed_height_cap():
    ui20 = _r("ui20.css")
    assert ".app-header{min-height:64px" in ui20
    assert ".app-header{height:64px" not in ui20


def test_header_keeps_wrap_without_clipping():
    style = _r("style.css")
    assert "flex-wrap:wrap" in style
    # blanket horizontal-overflow mask must be gone; per-component
    # containment (table-wrap / responsive-cards / fixed drawer) applies
    assert "overflow-x:hidden" not in style


def test_skip_link_does_not_extend_scrollable_area():
    style = _r("style.css")
    assert "left:-9999px" not in style
    assert "clip-path:inset(50%)" in style


def test_drawer_and_backdrop_have_no_hardcoded_header_offset():
    style = _r("style.css")
    assert "inset:64px" not in style
    assert "top:64px" not in style
    # full-height fixed drawer above the sticky header; out of document
    # flow so open/close cannot create horizontal overflow or blank gaps
    assert ".sidebar{position:fixed;top:0;right:0;bottom:0" in style
    assert ".nav-backdrop.visible{display:block;position:fixed;inset:0" in style


def test_mobile_main_padding_survives_cascade():
    style = _r("style.css")
    ui20 = _r("ui20.css")
    assert "@media(max-width:800px)" in style
    assert "@media(max-width:800px)" in ui20
    # the later sheet (ui20.css) must agree on mobile padding instead of
    # overriding it with the desktop base rule
    assert ".main{padding:12px}" in ui20


def test_viewport_height_uses_dvh_with_vh_fallback():
    style = _r("style.css")
    ui20 = _r("ui20.css")
    assert style.count("100dvh") >= 2
    assert ui20.count("100dvh") >= 1
    # fallback for old browsers retained
    assert "100vh" in style and "100vh" in ui20


def test_breakpoints_stay_minimal_and_predictable():
    style = _r("style.css")
    ui20 = _r("ui20.css")
    for bp in ("max-width:560px", "max-width:800px", "max-width:900px"):
        assert bp in style + ui20, bp
    assert (style + ui20).count("@media") <= 5


def test_cards_and_hero_behave_on_small_viewports():
    ui20 = _r("ui20.css")
    assert "repeat(5,minmax(0,1fr))" in ui20  # desktop intact
    assert "repeat(3,1fr)" in ui20  # tablet
    assert "repeat(2,1fr)" in ui20  # mobile small
    assert ".hero{flex-wrap:wrap" in ui20


def test_tables_keep_internal_scroll_containment():
    style = _r("style.css")
    ui20 = _r("ui20.css")
    assert ".table-wrap{overflow-x:auto" in style
    assert ".table-wrap{overflow-x:auto" in ui20
    assert "responsive-cards" in style


def test_viewport_meta_covers_notch_devices():
    html = _r("index.html")
    assert "viewport-fit=cover" in html
    assert 'href="ui20.css"' in html


def test_desktop_layout_rules_untouched():
    style = _r("style.css")
    assert ".sidebar{width:220px;flex-shrink:0" in style
    assert ".app-shell{display:flex" in style
    assert "position:sticky;top:0;z-index:50" in style


def test_retired_service_behavior_untouched():
    app = _r("app.js")
    for token in ("buildServiceStates", "visibleProjects", "summarizeProjects",
                  "__yasinhubServiceStates", "enabled === false"):
        assert token in app, token
