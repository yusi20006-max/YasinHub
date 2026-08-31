"""
UI 2.0 verification: design tokens, RTL/Persian shell, overview ops layout,
table toolbars, skeletons (#136–#142).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "dashboard"
JS = D / "js"

def _r(p):
    return p.read_text(encoding="utf-8")

def test_design_tokens_and_dark_mode():
    css = _r(D / "style.css")
    for tok in ("--bg", "--surface", "--text", "--accent", "--danger", "--success", "--focus-ring"):
        assert tok in css
    assert ".dark {" in css
    assert "responsive-cards" in css
    assert "skeleton" in css
    assert "toast-host" in css or ".toast" in css

def test_persian_rtl_shell():
    html = _r(D / "index.html")
    assert 'lang="fa"' in html
    assert 'dir="rtl"' in html
    assert "نمای کلی" in html
    assert "اجراها" in html
    assert "ناوها" in html
    assert "رویدادها" in html
    assert 'data-nav="overview"' in html
    assert "YasinHub" in html

def test_views_overview_programs_and_filters():
    views = _r(JS / "views.js")
    assert "Yasin Programs" in views
    assert "service-status-list" in views
    assert "RUNNING / ACTIVE" in views
    assert "table-toolbar" in views
    assert "renderSkeleton" in views
    assert "fa-IR" in views or "fa.IR" in views or "toLocaleString" in views
    assert "&amp;" in views

def test_app_overview_fetches_events():
    app = _r(D / "app.js")
    assert "listEvents" in app
    assert "renderOverview" in app
    assert "toast-host" in app or "toast" in app
