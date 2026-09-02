"""
tests/test_pwa_ui_verification.py
Deterministic coverage for redesigned PWA visual system, themes, states,
responsive structure, and existing control wiring (#125 / #116).
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];DASHBOARD=ROOT/"dashboard";JS=DASHBOARD/"js"
def _read(path:Path)->str:return path.read_text(encoding="utf-8")
def test_css_design_tokens_and_dark_mode():
 css=_read(DASHBOARD/"style.css")
 for token in ("--bg","--surface","--text","--muted","--border","--accent","--danger","--success","--warn","--shadow","--focus-ring"): assert token in css,token
 assert ".dark {" in css
 for st in ("status-queued","status-running","status-paused","status-succeeded","status-failed","status-cancelled","status-unknown"): assert st in css,st

def test_css_responsive_and_mobile_nav():
 css=_read(DASHBOARD/"style.css")
 assert "@media" in css and "nav-toggle" in css and ".sidebar.open" in css and "responsive-cards" in css
 assert "--touch-min" in css or "min-height" in css
 assert "dir=\"rtl\"" in css or "[dir=\"rtl\"]" in css or "html[dir=\"rtl\"]" in css

def test_css_states_loading_empty_error_offline():
 css=_read(DASHBOARD/"style.css")
 for cls in ("state-loading","state-empty","state-error","state-offline","stale-indicator","status-online","status-offline","control-feedback","control-pending","control-ok","control-error"): assert cls in css,cls

def test_css_tables_and_cards():
 css=_read(DASHBOARD/"style.css")
 for cls in (".data-table",".table-wrap",".card",".overview-cards",".badge"): assert cls in css

def test_views_render_services_table_and_states():
 views=_read(JS/"views.js")
 for token in ("renderOverview","Services","responsive-cards","data-label","renderLoading","renderEmpty","renderError","state-loading","state-empty","state-error","control-bar","ctrl-btn"): assert token in views
 assert "&amp;" in views
 assert "&lt;" in views

def test_views_keyboard_rows_and_status_badges():
 views=_read(JS/"views.js")
 assert "keydown" in views and "Enter" in views and "statusClass" in views
 for name in ("renderExecutionsList","renderExecutionDetail","renderFleetsList","renderFleetDetail","renderEventsTimeline"): assert name in views

def test_app_uses_status_endpoint_for_services():
 app=_read(DASHBOARD/"app.js");api=_read(JS/"api.js")
 assert "getSystemStatus" in api and "/api/status" in api and "getSystemStatus" in app and "getSystemDashboard" in app
 assert "control-pending" in app or "isPending" in app

def test_shell_preserves_routes_and_chrome():
 html=_read(DASHBOARD/"index.html")
 for nav in ("overview","executions","fleets","events"): assert f'data-nav="{nav}"' in html
 for token in ("connection-status","stale-indicator","theme-toggle","nav-toggle","skip-link","id=\"content\"","lang=\"fa\"","dir=\"rtl\"","style.css?v=2","service-controls.js?v=2"): assert token in html

def test_models_status_class_maps_health_states():
 models=_read(JS/"models.js")
 assert "statusClass" in models and "success" in models and "succeeded" in models
