"""Phase 4: PWA ↔ Control Plane truthful integration contracts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from yasinhub.registry import ProjectEntry
from tests.test_api_server import DummyHandler, MockRequest
import pytest

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"


@pytest.fixture
def dummy_handler():
    return DummyHandler(MockRequest(), ("127.0.0.1", 12345), MagicMock())


def test_status_payload_includes_pid_and_process_running(dummy_handler):
    report = MagicMock()
    report.name = "yasinrelay"
    report.health_state = "RUNNING"
    report.last_run = "2026-01-01T00:00:00+00:00"
    report.last_success = True
    report.last_message = "observed running"
    report.metrics = {}
    report.db_stats = {}
    report.health = {}
    report.process_running = True

    with patch("yasinhub.api.server.build_report", return_value=[report]), patch(
        "yasinhub.api.server.read_pid", return_value=4242
    ), patch("yasinhub.api.server.is_pid_alive", return_value=True):
        dummy_handler.path = "/api/status"
        dummy_handler.do_GET()

    body = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert body["projects"][0]["pid"] == 4242
    assert body["projects"][0]["process_running"] is True
    assert body["projects"][0]["status"] == "RUNNING"


def test_control_start_returns_authoritative_snapshot(dummy_handler):
    project = ProjectEntry(name="yasinrelay", start_command="dummy")
    report = MagicMock()
    report.name = "yasinrelay"
    report.health_state = "RUNNING"
    report.last_message = "observed running"
    report.process_running = True
    report.last_run = None
    report.last_success = True

    with patch("yasinhub.api.server.default_registry", return_value=[project]), patch(
        "yasinhub.api.server.start_service", return_value=True
    ), patch("yasinhub.api.server.build_report", return_value=[report]), patch(
        "yasinhub.api.server.read_pid", return_value=777
    ), patch("yasinhub.api.server.is_pid_alive", return_value=True):
        dummy_handler.path = "/api/control/yasinrelay/start"
        dummy_handler.do_POST()

    assert dummy_handler.response_code == 200
    body = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert body["success"] is True
    assert body["status"] == "RUNNING"
    assert body["pid"] == 777


def test_control_failure_is_not_http_200(dummy_handler):
    project = ProjectEntry(name="yasinrelay", start_command="dummy")
    report = MagicMock()
    report.name = "yasinrelay"
    report.health_state = "IDLE"
    report.last_message = "startup failed"
    report.process_running = False
    report.last_run = None
    report.last_success = False

    with patch("yasinhub.api.server.default_registry", return_value=[project]), patch(
        "yasinhub.api.server.start_service", return_value=False
    ), patch("yasinhub.api.server.build_report", return_value=[report]), patch(
        "yasinhub.api.server.read_pid", return_value=None
    ), patch("yasinhub.api.server.is_pid_alive", return_value=False):
        dummy_handler.path = "/api/control/yasinrelay/start"
        dummy_handler.do_POST()

    assert dummy_handler.response_code == 409
    body = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert body["success"] is False
    assert body["status"] == "IDLE"


def test_control_unknown_service_404(dummy_handler):
    with patch("yasinhub.api.server.default_registry", return_value=[]):
        dummy_handler.path = "/api/control/missing-svc/start"
        dummy_handler.do_POST()
    assert dummy_handler.response_code == 404
    body = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert body["success"] is False


def test_pwa_overview_renders_pid_column():
    views = (DASH / "js" / "views.js").read_text(encoding="utf-8")
    assert 'data-label="PID"' in views
    assert "project.pid" in views
    assert "<th>PID</th>" in views


def test_pwa_controls_require_backend_success_and_show_status():
    source = (DASH / "service-controls.js").read_text(encoding="utf-8")
    assert "data.success===true" in source
    assert "formatAuthoritativeResult" in source
    assert "data-lifecycle-pending" in source
    assert "state=" in source
    assert "pid=" in source
    assert "running = true" not in source
    assert 'status="RUNNING"' not in source


def test_pwa_no_secrets_in_dashboard_js():
    for path in (DASH / "js").glob("*.js"):
        text = path.read_text(encoding="utf-8")
        assert "Bearer " not in text
        assert "api_key" not in text.lower()
    sc = (DASH / "service-controls.js").read_text(encoding="utf-8")
    assert "Bearer " not in sc
