"""Focused P0 HTTP control authentication and authorization tests."""

from __future__ import annotations

import json
from io import BytesIO

import pytest

from yasinhub.api.observer_routes import handle_execution_observer
from yasinhub.api.server import YasinHubHandler
from yasinhub.auth import AuthMode, Role, YasinPrincipal, reset_auth_for_tests
from yasinhub.observer import get_default_store
from yasinhub.observer.models import FleetSnapshot, WorkerSnapshot
from yasinhub.execution.policies import PolicyEngine


class _Handler:
    def __init__(self):
        self.responses = []

    def send_json(self, data, status=200):
        self.responses.append((status, data))


@pytest.fixture(autouse=True)
def _auth_and_store():
    reset_auth_for_tests(
        mode=AuthMode.PRODUCTION,
        tokens={
            "admin-token": YasinPrincipal("admin-user", Role.ADMIN, auth_method="bearer_token"),
            "operator-token": YasinPrincipal("operator-user", Role.OPERATOR, auth_method="bearer_token"),
            "viewer-token": YasinPrincipal("viewer-user", Role.VIEWER, auth_method="bearer_token"),
        },
    )
    store = get_default_store()
    store.clear()
    yield
    store.clear()
    reset_auth_for_tests()


def _headers(token=None, **extra):
    out = {}
    if token:
        out["Authorization"] = f"Bearer {token}"
    out.update(extra)
    return out


def _post_control(body, headers):
    payload = json.dumps(body).encode()
    result = _Handler()
    hdrs = {"Content-Length": str(len(payload)), **headers}
    from yasinhub.api.control_routes import handle_control_api_routes
    handle_control_api_routes("/api/control", "POST", "/api/control", hdrs, BytesIO(payload), result.send_json)
    return result.responses[0]


def test_direct_service_mutation_requires_auth(monkeypatch):
    called = []
    monkeypatch.setattr("yasinhub.api.server.default_registry", lambda: [])
    monkeypatch.setattr("yasinhub.api.server.start_service", lambda project: called.append(project) or True)

    h = _Handler()
    YasinHubHandler.handle_control(h, "/api/control/yasin-agent/start", "POST", {})
    assert h.responses[0][0] == 401
    assert called == []


def test_direct_service_mutation_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr("yasinhub.api.server.default_registry", lambda: [])
    h = _Handler()
    YasinHubHandler.handle_control(
        h, "/api/control/yasin-agent/start", "POST", _headers("wrong-token")
    )
    assert h.responses[0][0] == 401


def test_direct_service_mutation_requires_operator_role(monkeypatch):
    monkeypatch.setattr("yasinhub.api.server.default_registry", lambda: [])
    h = _Handler()
    YasinHubHandler.handle_control(
        h, "/api/control/yasin-agent/start", "POST", _headers("viewer-token")
    )
    assert h.responses[0][0] == 403


def test_direct_service_mutation_accepts_operator(monkeypatch):
    from yasinhub.registry import ProjectEntry
    project = ProjectEntry(name="yasin-agent", start_command="true")
    monkeypatch.setattr("yasinhub.api.server.default_registry", lambda: [project])
    monkeypatch.setattr("yasinhub.api.server.start_service", lambda p: True)
    monkeypatch.setattr(
        "yasinhub.api.server.service_runtime_snapshot",
        lambda name: {"status": "RUNNING", "pid": 123, "message": "ok", "process_running": True},
    )
    h = _Handler()
    YasinHubHandler.handle_control(
        h, "/api/control/yasin-agent/start", "POST", _headers("operator-token")
    )
    assert h.responses[0][0] == 200
    assert h.responses[0][1]["success"] is True


def test_observer_pause_rejects_missing_and_viewer_auth():
    snap = get_default_store().create_execution(task_id="p0")
    get_default_store().start(snap.execution_id)

    for headers, expected in ({}, 401), (_headers("viewer-token"), 403):
        h = _Handler()
        body = json.dumps({"actor": "spoofed-admin"}).encode()
        handle_execution_observer(
            f"/api/executions/{snap.execution_id}/pause",
            "POST",
            f"/api/executions/{snap.execution_id}/pause",
            {"Content-Length": str(len(body)), **headers},
            BytesIO(body),
            h.send_json,
        )
        assert h.responses[0][0] == expected
        assert get_default_store().get_execution(snap.execution_id).status == "running"


def test_observer_mutation_uses_token_identity_not_body_actor():
    snap = get_default_store().create_execution(task_id="p0")
    get_default_store().start(snap.execution_id)
    h = _Handler()
    body = json.dumps({"actor": "spoofed-admin", "request_id": "req-p0"}).encode()
    handle_execution_observer(
        f"/api/executions/{snap.execution_id}/pause",
        "POST",
        f"/api/executions/{snap.execution_id}/pause",
        {"Content-Length": str(len(body)), **_headers("operator-token")},
        BytesIO(body),
        h.send_json,
    )
    assert h.responses[0][0] == 200
    events = get_default_store().list_events(execution_id=snap.execution_id)
    assert any(e.as_dict().get("metadata", {}).get("actor") == "operator-user" for e in events)


def test_observer_fleet_cancel_requires_auth_and_accepts_operator():
    store = get_default_store()
    e = store.create_execution(task_id="fleet-p0")
    store.start(e.execution_id)
    store.upsert_fleet(
        FleetSnapshot(
            task_id="fleet-p0",
            status="running",
            workers=[WorkerSnapshot(worker_id="w1", status="running", execution_id=e.execution_id)],
        )
    )

    h = _Handler()
    handle_execution_observer(
        "/api/fleets/fleet-p0/cancel",
        "POST",
        "/api/fleets/fleet-p0/cancel",
        {"Content-Length": "2"},
        BytesIO(b"{}"),
        h.send_json,
    )
    assert h.responses[0][0] == 401

    h = _Handler()
    handle_execution_observer(
        "/api/fleets/fleet-p0/cancel",
        "POST",
        "/api/fleets/fleet-p0/cancel",
        {"Content-Length": "2", **_headers("operator-token")},
        BytesIO(b"{}"),
        h.send_json,
    )
    assert h.responses[0][0] == 200
    assert h.responses[0][1]["success"] is True


def test_control_role_and_actor_spoofing_are_enforced():
    status, data = _post_control(
        {"action": "cancel", "execution_id": "missing", "actor": "admin-user"},
        _headers("viewer-token"),
    )
    assert status == 403
    assert "viewer-user" not in json.dumps(data)

    status, data = _post_control(
        {"action": "status", "actor": "spoofed-admin"},
        _headers("operator-token"),
    )
    assert status == 200
    assert data["success"] is True


def test_confirmation_gate_remains_after_authz():
    eng = PolicyEngine()
    denied = eng.evaluate(action="production_merge", execution_id="e1", role=Role.ADMIN)
    assert denied.allowed is False
    assert denied.requires_approval is True
    eng.approve("e1", "production_merge", actor="admin-user")
    allowed = eng.evaluate(action="production_merge", execution_id="e1", role=Role.ADMIN)
    assert allowed.allowed is True


def test_control_idempotency_remains_intact():
    eng = PolicyEngine()
    first = eng.authorize_and_record(
        action="cancel", actor="operator-user", source="http-api",
        control_event_id="p0-idempotency", role=Role.OPERATOR,
    )
    second = eng.authorize_and_record(
        action="cancel", actor="operator-user", source="http-api",
        control_event_id="p0-idempotency", role=Role.OPERATOR,
    )
    assert first.allowed is True
    assert second.allowed is False
    assert second.policy == "idempotency"


def test_event_cleanup_policy_requires_operator_role():
    eng = PolicyEngine()
    assert eng.evaluate(action="events_cleanup", role=Role.VIEWER).allowed is False
    assert eng.evaluate(action="events_cleanup", role=Role.OPERATOR).allowed is True


def test_event_cleanup_route_requires_auth_and_role(monkeypatch):
    calls = []
    monkeypatch.setattr("yasinhub.events_engine.cleanup_events", lambda: calls.append(True) or True)

    class Request:
        def __init__(self, headers):
            self.path = "/api/events/cleanup"
            self.headers = headers
            self.rfile = BytesIO(b"")
            self.responses = []
            self.wfile = BytesIO()
        def send_json(self, data, status=200):
            self.responses.append((status, data))
        def send_response(self, status):
            self.responses.append((status, None))
        def send_header(self, *args):
            pass
        def end_headers(self):
            pass
        def handle_control(self, *args):
            return False

    from yasinhub.api.server import YasinHubHandler
    unauth = Request({})
    YasinHubHandler.do_POST(unauth)
    assert unauth.responses[0][0] == 401
    assert calls == []

    viewer = Request(_headers("viewer-token"))
    YasinHubHandler.do_POST(viewer)
    assert viewer.responses[0][0] == 403
    assert calls == []

    operator = Request(_headers("operator-token"))
    YasinHubHandler.do_POST(operator)
    assert operator.responses[0][0] == 200
    assert calls == [True]


def test_event_cleanup_actor_spoofing_does_not_change_audit_actor(monkeypatch):
    monkeypatch.setattr("yasinhub.events_engine.cleanup_events", lambda: True)
    class Request:
        def __init__(self):
            self.path = "/api/events/cleanup"
            self.headers = _headers("operator-token")
            self.rfile = BytesIO(b"")
            self.responses = []
            self.wfile = BytesIO()
        def send_json(self, data, status=200):
            self.responses.append((status, data))
        def send_response(self, status):
            self.responses.append((status, None))
        def send_header(self, *args):
            pass
        def end_headers(self):
            pass
        def handle_control(self, *args):
            return False
    from yasinhub.api.server import YasinHubHandler
    req = Request()
    YasinHubHandler.do_POST(req)
    assert req.responses[0][0] == 200
    rows = get_policy_engine().list_audit(limit=10, action="events_cleanup")
    assert rows and rows[-1]["actor"] == "operator-user"
