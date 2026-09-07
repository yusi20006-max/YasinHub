"""
tests/test_pwa_retirement_filter.py
PWA hides retired services using the canonical registry signal
(`enabled === false` from /api/services) — never display-text matching.

- Retired rows are filtered before render; their control buttons are
  never injected (and stale ones are removed).
- All 5 active services keep rendering with full Start/Stop/Restart.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
JS = DASH / "js"

RETIRED = ("eitaa_news_v2", "yasin-coder", "backup_manager")
ACTIVE = ("yasinfeed", "yasinrelay", "yasin-agent", "yasin-ai", "yasinpress")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_api_client_exposes_services_endpoint():
    content = _read(JS / "api.js")
    assert "getServices" in content
    assert "/api/services" in content


def test_overview_filters_by_canonical_enabled_flag():
    content = _read(DASH / "app.js")
    # Canonical signal, strict comparison — not status text, not name lists.
    assert "enabled === false" in content
    assert "getServices" in content
    assert "visibleProjects" in content
    assert "__yasinhubServiceStates" in content


def test_controls_decorator_skips_retired_services():
    content = _read(DASH / "service-controls.js")
    assert "isRetiredService" in content
    assert "__yasinhubServiceStates" in content
    assert "enabled === false" in content


def test_no_hardcoded_service_names_in_filter():
    for rel in ("app.js", "service-controls.js", "js/api.js", "js/views.js"):
        content = _read(DASH / rel)
        for name in RETIRED + ACTIVE:
            assert name not in content, f"{rel} must not hardcode {name}"


def test_active_controls_intact():
    content = _read(DASH / "service-controls.js")
    assert 'ACTIONS = ["start", "stop", "restart"]' in content
    assert "buildControls" in content
    assert "decorateServices" in content
    views = _read(JS / "views.js")
    assert "renderOverview" in views
