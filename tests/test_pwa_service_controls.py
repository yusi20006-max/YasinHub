from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_service_control_surface_exists_and_uses_backend_endpoint():
    source = (ROOT / "dashboard" / "service-controls.js").read_text(encoding="utf-8")
    assert 'const ACTIONS = ["start", "stop", "restart"]' in source
    assert 'data-service-action="${action}"' in source
    assert "encodeURIComponent(action)" in source
    assert "/api/control/" in source
    assert 'method:"POST"' in source or 'method: "POST"' in source
    assert 'credentials:"same-origin"' in source or 'credentials: "same-origin"' in source


def test_service_control_surface_reconciles_from_authoritative_state():
    source = (ROOT / "dashboard" / "service-controls.js").read_text(encoding="utf-8")
    assert "refreshOverview" in source
    assert "await refreshOverview()" in source
    assert "MutationObserver" in source
    assert "data-service-status" in source


def test_service_control_surface_has_direct_actions_and_state_gating():
    source = (ROOT / "dashboard" / "service-controls.js").read_text(encoding="utf-8")
    assert "service-controls" in source
    assert "service-action" in source
    assert "allowed(action,status)" in source or "allowed(a,normalized)" in source
    assert "ACTIONS" in source
    assert "ACTIONS.filter" in source
    assert "data-service-action" in source
    assert "disabled=true" in source or ".disabled=true" in source
