"""Focused #205 execution persistence failure/recovery tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from yasinhub.auth import AuthMode, reset_auth_for_tests
from yasinhub.observer.execution_store import ExecutionObserverStore
from yasinhub.observer.lifecycle_ext import (
    get_execution_persistence_status,
    record_execution_persistence_success,
)


@pytest.fixture(autouse=True)
def _reset_execution_persistence_state():
    reset_auth_for_tests()
    record_execution_persistence_success()
    yield
    reset_auth_for_tests()
    record_execution_persistence_success()


def test_execution_persistence_failure_is_observable_and_recovery_clears(tmp_path, monkeypatch):
    reset_auth_for_tests(mode=AuthMode.TEST)
    store = ExecutionObserverStore(durable_dir=str(tmp_path / "executions"))

    original_write_text = Path.write_text

    def fail_write(*args, **kwargs):
        raise OSError("simulated execution persistence failure")

    monkeypatch.setattr(Path, "write_text", fail_write)
    snap = store.create_execution(task_id="persist-failure", execution_id="exec-persist-failure")
    failed = get_execution_persistence_status()

    assert snap.execution_id == "exec-persist-failure"
    assert failed["status"] == "degraded"
    assert failed["persist_failures"] == 1
    assert failed["last_failure_type"] == "OSError"
    assert "simulated execution persistence failure" not in str(failed)

    monkeypatch.setattr(Path, "write_text", original_write_text)
    store._persist_execution(snap)
    recovered = get_execution_persistence_status()

    assert recovered["status"] == "healthy"
    assert recovered["persist_failures"] == 0
    assert recovered["last_failure_type"] is None


def test_execution_persistence_status_never_contains_secret_message():
    from yasinhub.observer import lifecycle_ext

    try:
        lifecycle_ext.record_execution_persistence_failure(
            RuntimeError("token=super-secret")
        )
        status = lifecycle_ext.get_execution_persistence_status()
        assert status["last_failure_type"] == "RuntimeError"
        assert "super-secret" not in str(status)
    finally:
        record_execution_persistence_success()
