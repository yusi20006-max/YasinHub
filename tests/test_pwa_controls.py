"""
tests/test_pwa_controls.py
Safe execution/fleet controls in PWA (#58).
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.test_api_server import DummyHandler, MockRequest
from yasinhub.observer import get_default_store
from yasinhub.observer.models import FleetSnapshot, WorkerSnapshot

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
JS = DASH / "js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_api_js_has_control_post_helpers():
    content = _read(JS / "api.js")
    assert "postJSON" in content
    assert "pauseExecution" in content
    assert "resumeExecution" in content
    assert "cancelExecution" in content
    assert "cancelFleet" in content
    assert "newRequestId" in content
    assert "request_id" in content
    # Must not hardcode credentials
    assert "Authorization" not in content
    assert "Bearer" not in content
    assert "localStorage" not in content


def test_models_control_availability_helpers():
    content = _read(JS / "models.js")
    assert "canPause" in content
    assert "canResume" in content
    assert "canCancel" in content
    assert "canCancelFleet" in content


def test_views_control_buttons_and_confirm():
    content = _read(JS / "views.js")
    assert "controlBarHtml" in content or "control-bar" in content
    assert 'data-ctrl="pause"' in content
    assert 'data-ctrl="resume"' in content
    assert 'data-ctrl="cancel"' in content
    assert 'data-ctrl="fleet-cancel"' in content
    assert "data-confirm" in content
    assert "formatControlError" in content
    assert "disabled" in content


def test_app_js_wires_controls_and_reconciles():
    content = _read(DASH / "app.js")
    assert "handleControlClick" in content
    assert "wireControls" in content
    assert "formatControlError" in content
    assert "pauseExecution" in content
    assert "cancelFleet" in content
    # Reconcile from server after control
    assert "soft: true" in content
    assert "window.confirm" in content


def test_style_control_bar_present():
    content = _read(DASH / "style.css")
    assert "control-bar" in content
    assert "control-feedback" in content
    assert "ctrl-btn" in content


def test_docs_control_endpoints():
    content = _read(ROOT / "docs" / "PWA_ARCHITECTURE.md")
    assert "#58" in content
    assert "/pause" in content
    assert "/resume" in content
    assert "/cancel" in content
    assert "409" in content
    assert "request_id" in content


def test_no_client_auth_identity_as_authority():
    """Frontend must not treat client actor as authenticated identity."""
    api = _read(JS / "api.js")
    assert "request_id" in api
    assert "localStorage" not in api
    assert "sessionStorage" not in api
    assert "Authorization" not in api
    # actor is optional body field only, not forced
    assert "opts.actor" in api or "opts && opts.actor" in api


# --- Backend regression: control plane still works ---

@pytest.fixture
def store():
    s = get_default_store()
    s.clear()
    yield s
    s.clear()


def test_backend_pause_resume_cancel_contract(store):
    snap = store.create_execution(task_id="pwa-ctl")
    store.start(snap.execution_id)
    assert store.pause(snap.execution_id).status == "paused"
    assert store.resume(snap.execution_id).status == "running"
    assert store.cancel(snap.execution_id).status == "cancelled"


def test_backend_invalid_transition_raises(store):
    from yasinhub.observer.execution_store import InvalidTransitionError

    snap = store.create_execution(task_id="pwa-inv")
    with pytest.raises(InvalidTransitionError):
        store.pause(snap.execution_id)


def test_backend_fleet_cancel(store):
    e1 = store.create_execution(task_id="pwa-fc")
    store.start(e1.execution_id)
    store.upsert_fleet(
        FleetSnapshot(
            task_id="pwa-fc",
            status="running",
            workers=[
                WorkerSnapshot(
                    worker_id="w1",
                    status="running",
                    execution_id=e1.execution_id,
                    session_id=e1.session_id,
                )
            ],
        )
    )
    result = store.cancel_fleet("pwa-fc", actor="ops", request_id="r-pwa")
    assert result.status in ("cancelling", "cancelled")
