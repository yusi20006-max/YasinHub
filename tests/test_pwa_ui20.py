"""Regression coverage for YasinHub PWA UI 2.0."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "dashboard"
JS = D / "js"


def _r(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_design_tokens_and_responsive_ui20():
    css = _r(D / "ui20.css")
    for token in ("--ui20-bg", "--ui20-surface", "--ui20-text", "--ui20-accent", "--ui20-danger", "--ui20-success"):
        assert token in css
    assert ".dark" in css
    assert ".table-toolbar" in css
    assert ".service-status-list" in css
    assert "@media(max-width:560px)" in css


def test_persian_rtl_shell_and_assets():
    html = _r(D / "index.html")
    assert 'lang="fa"' in html
    assert 'dir="rtl"' in html
    for text in ("نمای کلی", "اجراها", "ناوها", "رویدادها", "یاسین‌هاب"):
        assert text in html
    assert 'href="ui20.css"' in html
    assert 'src="ui20.js"' in html


def test_real_program_status_surface():
    views = _r(JS / "views.js")
    assert "service-status-list" in views
    assert "project.status" in views
    assert "project.message" in views
    assert "RUNNING / ACTIVE" in views
    assert "&amp;" in views


def test_progressive_table_tools_and_persian_layer():
    ui = _r(D / "ui20.js")
    assert "table-search" in ui
    assert "table-filter" in ui
    assert "MutationObserver" in ui
    assert "آنلاین" in ui


def test_app_keeps_observer_event_fetch():
    app = _r(D / "app.js")
    assert "listEvents" in app
    assert "renderOverview" in app
    assert "getSystemDashboard" in app
