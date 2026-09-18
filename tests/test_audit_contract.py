"""Focused #188 audit contract and operational read-surface tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from yasinhub.auth import AuthMode, Role, YasinPrincipal, reset_auth_for_tests
from yasinhub.execution.policies import PolicyEngine
from yasinhub.storage.audit_store import FileAuditStore, MemoryAuditStore


@pytest.fixture(autouse=True)
def _auth():
    reset_auth_for_tests(
        mode=AuthMode.PRODUCTION,
        tokens={
            "audit-operator": YasinPrincipal("operator-1", Role.OPERATOR, auth_method="bearer_token"),
            "audit-viewer": YasinPrincipal("viewer-1", Role.VIEWER, auth_method="bearer_token"),
        },
    )
    yield
    reset_auth_for_tests()


def test_new_audit_record_has_canonical_target_and_result():
    engine = PolicyEngine()
    record = engine._audit_record(
        actor="operator-1",
        source="http-api",
        action="cancel",
        policy_decision="allow",
        outcome="authorized",
        execution_id="exec-188",
    )
    data = record.as_dict()
    assert data["target"] == "exec-188"
    assert data["result"] == "authorized"


def test_legacy_file_records_are_normalized_without_rewrite(tmp_path: Path):
    store = FileAuditStore(str(tmp_path))
    store.append({
        "audit_id": "legacy-1",
        "actor": "alice",
        "source": "legacy",
        "timestamp": time.time(),
        "action": "status",
        "execution_id": "exec-old",
        "policy_decision": "allow",
        "outcome": "ok",
        "external_ids": {},
        "metadata": {},
    })
    rows = store.list(limit=10)
    assert rows[0]["target"] == "exec-old"
    assert rows[0]["result"] == "ok"


def test_legacy_record_with_external_target_is_normalized():
    store = MemoryAuditStore()
    store.append({
        "audit_id": "legacy-2",
        "actor": "alice",
        "source": "legacy",
        "timestamp": time.time(),
        "action": "status",
        "execution_id": None,
        "policy_decision": "allow",
        "outcome": "ok",
        "external_ids": {"target": "service:yasin-agent"},
        "metadata": {},
    })
    row = store.list(limit=1)[0]
    assert row["target"] == "service:yasin-agent"
    assert row["result"] == "ok"


class _FakeRequest:
    def __init__(self, path: str, token: str | None):
        self.path = path
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
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


def test_audit_http_read_requires_authentication():
    req = _FakeRequest("/api/audit", None)
    from yasinhub.api.server import YasinHubHandler
    YasinHubHandler.do_GET(req)
    assert req.responses[0][0] == 401


def test_audit_http_read_rejects_viewer():
    req = _FakeRequest("/api/audit", "audit-viewer")
    from yasinhub.api.server import YasinHubHandler
    YasinHubHandler.do_GET(req)
    assert req.responses[0][0] == 403


def test_audit_http_read_accepts_operator_and_filters():
    from yasinhub.storage.audit_store import reset_audit_store_for_tests, set_audit_store
    store = MemoryAuditStore()
    store.append({
        "audit_id": "read-1",
        "actor": "operator-1",
        "source": "http-api",
        "timestamp": time.time(),
        "action": "cancel",
        "execution_id": "exec-188",
        "policy_decision": "allow",
        "outcome": "authorized",
        "metadata": {"Authorization": "Bearer SECRET"},
    })
    set_audit_store(store)
    try:
        req = _FakeRequest("/api/audit?target=exec-188&result=authorized", "audit-operator")
        from yasinhub.api.server import YasinHubHandler
        YasinHubHandler.do_GET(req)
        status, payload = req.responses[0]
        assert status == 200
        assert payload["count"] == 1
        row = payload["audit"][0]
        assert row["target"] == "exec-188"
        assert row["result"] == "authorized"
        assert "SECRET" not in json.dumps(payload)
    finally:
        reset_audit_store_for_tests()
