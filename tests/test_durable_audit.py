"""Durable audit/event store (#111)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from yasinhub.execution.policies import PolicyEngine, get_policy_engine
from yasinhub.storage.audit_store import (
    FileAuditStore,
    MemoryAuditStore,
    get_audit_store,
    reset_audit_store_for_tests,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_audit_store_for_tests(MemoryAuditStore())
    yield
    reset_audit_store_for_tests(MemoryAuditStore())


def test_memory_audit_append_and_query():
    store = MemoryAuditStore()
    store.append(
        {
            "audit_id": "a1",
            "actor": "alice",
            "source": "pwa",
            "timestamp": time.time(),
            "action": "cancel",
            "execution_id": "exec_1",
            "policy_decision": "allow",
            "outcome": "authorized",
            "external_ids": {},
            "metadata": {"token": "secret-value"},
        }
    )
    rows = store.list(actor="alice", execution_id="exec_1")
    assert len(rows) == 1
    assert rows[0]["actor"] == "alice"
    assert "secret-value" not in str(rows[0])


def test_file_audit_survives_restart(tmp_path: Path):
    path = tmp_path / "audit"
    store1 = FileAuditStore(str(path), retention_max=100)
    store1.append(
        {
            "audit_id": "a2",
            "actor": "bob",
            "source": "slack",
            "timestamp": time.time(),
            "action": "retry",
            "execution_id": "exec_9",
            "policy_decision": "allow",
            "outcome": "authorized",
            "external_ids": {},
            "metadata": {},
        }
    )
    store2 = FileAuditStore(str(path), retention_max=100)
    rows = store2.list(execution_id="exec_9")
    assert len(rows) == 1
    assert rows[0]["actor"] == "bob"


def test_policy_engine_writes_durable_audit():
    engine = PolicyEngine()
    engine.authorize_and_record(
        action="status",
        actor="ops",
        source="http-api",
        execution_id="exec_x",
        control_event_id="evt-1",
    )
    rows = get_audit_store().list(actor="ops", execution_id="exec_x")
    assert any(r.get("action") == "status" for r in rows)


def test_retention_bound():
    store = MemoryAuditStore(retention_max=5)
    for i in range(12):
        store.append(
            {
                "audit_id": f"a{i}",
                "actor": "a",
                "source": "t",
                "timestamp": float(i),
                "action": "status",
                "execution_id": None,
                "policy_decision": "allow",
                "outcome": "ok",
                "external_ids": {},
                "metadata": {},
            }
        )
    rows = store.list(limit=100)
    assert len(rows) == 5
    assert rows[0]["audit_id"] == "a7"


def test_list_audit_query_filters():
    engine = get_policy_engine()
    engine.authorize_and_record(
        action="cancel",
        actor="carol",
        source="cli",
        execution_id="exec_c",
        control_event_id="evt-c1",
    )
    rows = engine.list_audit(limit=50, actor="carol", action="cancel")
    assert any(r.get("execution_id") == "exec_c" for r in rows)
