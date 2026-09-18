"""Focused production durability tests for #189."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from yasinhub.auth import AuthMode, reset_auth_for_tests
from yasinhub.observer.execution_store import ExecutionObserverStore
from yasinhub.storage.audit_store import (
    FileAuditStore,
    create_audit_store_from_env,
    reset_audit_store_for_tests,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_auth_for_tests()
    reset_audit_store_for_tests()
    yield
    reset_auth_for_tests()
    reset_audit_store_for_tests()


def test_production_audit_defaults_to_file(monkeypatch, tmp_path: Path):
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens={})
    monkeypatch.delenv("YASIN_AUDIT_BACKEND", raising=False)
    monkeypatch.setenv("YASIN_AUDIT_DIR", str(tmp_path / "audit"))
    store = create_audit_store_from_env()
    assert isinstance(store, FileAuditStore)


def test_production_audit_rejects_explicit_memory(monkeypatch):
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens={})
    monkeypatch.setenv("YASIN_AUDIT_BACKEND", "memory")
    with pytest.raises(ValueError, match="production requires durable audit"):
        create_audit_store_from_env()


def test_production_execution_defaults_to_existing_file_persistence(monkeypatch, tmp_path: Path):
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens={})
    monkeypatch.delenv("YASIN_EXECUTION_BACKEND", raising=False)
    monkeypatch.setenv("YASIN_EXECUTION_STORE_DIR", str(tmp_path / "executions"))
    store = ExecutionObserverStore()
    assert store._durable_dir == tmp_path / "executions"


def test_production_execution_rejects_explicit_memory(monkeypatch):
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens={})
    monkeypatch.setenv("YASIN_EXECUTION_BACKEND", "memory")
    with pytest.raises(ValueError, match="production requires durable execution"):
        ExecutionObserverStore()


def test_execution_state_survives_store_restart(tmp_path: Path):
    path = tmp_path / "executions"
    store1 = ExecutionObserverStore(durable_dir=str(path))
    created = store1.create_execution(task_id="durable-189", execution_id="exec-189")
    assert created.status == "queued"

    store2 = ExecutionObserverStore(durable_dir=str(path))
    restored = store2.get_execution("exec-189")
    assert restored is not None
    assert restored.task_id == "durable-189"
    assert restored.status == "queued"


def test_audit_state_survives_store_restart(tmp_path: Path):
    path = tmp_path / "audit"
    store1 = FileAuditStore(str(path))
    store1.append({
        "audit_id": "durable-audit-189",
        "actor": "operator",
        "source": "test",
        "timestamp": 1.0,
        "action": "status",
        "execution_id": "exec-189",
        "policy_decision": "allow",
        "outcome": "ok",
        "target": "exec-189",
        "result": "ok",
        "external_ids": {},
        "metadata": {},
    })
    store2 = FileAuditStore(str(path))
    rows = store2.list(limit=10)
    assert rows[0]["audit_id"] == "durable-audit-189"


def test_production_validation_rejects_non_writable_audit_config(monkeypatch):
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens={})
    monkeypatch.setenv("YASIN_AUDIT_BACKEND", "memory")
    from yasinhub.storage.audit_store import validate_production_audit_config
    with pytest.raises(ValueError):
        validate_production_audit_config()


def test_production_validation_rejects_non_writable_execution_config(monkeypatch):
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens={})
    monkeypatch.setenv("YASIN_EXECUTION_BACKEND", "memory")
    from yasinhub.observer.lifecycle_ext import validate_production_execution_config
    with pytest.raises(ValueError):
        validate_production_execution_config()
