"""Focused #192 audit persistence failure/recovery tests."""

from __future__ import annotations

import time
from pathlib import Path

from yasinhub.storage.audit_store import (
    FileAuditStore,
    get_audit_persistence_status,
    record_append_failure,
    record_append_success,
)


def test_audit_append_failure_is_observable_and_recovery_clears(tmp_path, monkeypatch):
    store = FileAuditStore(str(tmp_path))
    store._cache = []

    original_open = Path.open

    def fail_open(*args, **kwargs):
        raise OSError("simulated append failure")

    monkeypatch.setattr(Path, "open", fail_open)
    store.append({"audit_id": "failure-1", "timestamp": time.time(), "outcome": "ok"})
    failed = get_audit_persistence_status()
    assert failed["status"] == "degraded"
    assert failed["append_failures"] == 1
    assert failed["last_failure_type"] == "OSError"

    monkeypatch.setattr(Path, "open", original_open)
    store.append({"audit_id": "recovery-1", "timestamp": time.time(), "outcome": "ok"})
    recovered = get_audit_persistence_status()
    assert recovered["status"] == "healthy"
    assert recovered["append_failures"] == 0
    assert recovered["last_failure_type"] is None


def test_failure_signal_contains_no_secret_data():
    record_append_failure(RuntimeError("token=super-secret"))
    status = get_audit_persistence_status()
    assert status["last_failure_type"] == "RuntimeError"
    assert "secret" not in str(status).lower()
    record_append_success()
