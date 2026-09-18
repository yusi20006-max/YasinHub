"""Focused HTTP mutation-surface security tests for #190."""

from __future__ import annotations

import pytest

from yasinhub.api.server import YasinHubHandler
from yasinhub.auth import AuthMode, Role, YasinPrincipal, reset_auth_for_tests
from yasinhub.execution.policies import get_policy_engine
from yasinhub.storage.audit_store import reset_audit_store_for_tests
import yasinhub.execution.policies as policies


class _Request(YasinHubHandler):
    def __init__(self, path, token=None, actor=None):
        self.path = path
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        if actor:
            self.headers["X-Actor"] = actor
        self.rfile = None
        self.responses = []

    def send_json(self, data, status=200):
        self.responses.append((status, data))

    def send_response(self, status):
        self.responses.append((status, None))

    def send_header(self, *args):
        pass

    def end_headers(self):
        pass


@pytest.fixture(autouse=True)
def _auth():
    reset_auth_for_tests(
        mode=AuthMode.PRODUCTION,
        tokens={
            "operator-token": YasinPrincipal("operator-190", Role.OPERATOR, auth_method="bearer_token"),
            "viewer-token": YasinPrincipal("viewer-190", Role.VIEWER, auth_method="bearer_token"),
        },
    )
    reset_audit_store_for_tests()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(policies, "_engine", None)
    yield
    reset_audit_store_for_tests()
    monkeypatch.undo()
    reset_auth_for_tests()


@pytest.mark.parametrize("path", ["/api/events/cleanup", "/api/events/clear"])
def test_event_mutation_requires_auth(monkeypatch, path):
    called = []
    monkeypatch.setattr("yasinhub.events_engine.cleanup_events", lambda: called.append(True) or True)
    req = _Request(path)
    YasinHubHandler.do_POST(req)
    assert req.responses[0][0] == 401
    assert called == []


@pytest.mark.parametrize("path", ["/api/events/cleanup", "/api/events/clear"])
def test_event_mutation_rejects_invalid_and_viewer_auth(monkeypatch, path):
    called = []
    monkeypatch.setattr("yasinhub.events_engine.cleanup_events", lambda: called.append(True) or True)
    for token, expected in [("bad-token", 401), ("viewer-token", 403)]:
        req = _Request(path, token=token)
        YasinHubHandler.do_POST(req)
        assert req.responses[0][0] == expected
    assert called == []


@pytest.mark.parametrize("path", ["/api/events/cleanup", "/api/events/clear"])
def test_event_cleanup_authorized_identity_is_token_principal(monkeypatch, path):
    called = []
    monkeypatch.setattr("yasinhub.events_engine.cleanup_events", lambda: called.append(True) or True)
    req = _Request(path, token="operator-token", actor="spoofed-admin")
    if path.endswith("/cleanup"):
        YasinHubHandler.do_POST(req)
    else:
        YasinHubHandler.do_GET(req)
    assert req.responses[0][0] == 200
    assert called == [True]
    action = "cleanup" if path.endswith("/cleanup") else "clear"
    rows = get_policy_engine().list_audit(limit=20, actor="operator-190", action=action)
    assert rows


def test_event_cleanup_idempotency_prevents_reuse(monkeypatch):
    calls = []
    monkeypatch.setattr("yasinhub.events_engine.cleanup_events", lambda: calls.append(True) or True)
    req1 = _Request("/api/events/cleanup", token="operator-token")
    req1.headers["X-Idempotency-Key"] = "cleanup-190"
    YasinHubHandler.do_POST(req1)
    req2 = _Request("/api/events/cleanup", token="operator-token")
    req2.headers["X-Idempotency-Key"] = "cleanup-190"
    YasinHubHandler.do_POST(req2)
    assert req1.responses[0][0] == 200
    assert req2.responses[0][0] == 403
    assert calls == [True]
