"""Production job lifecycle and runtime reliability (#112)."""

from __future__ import annotations

import tempfile
import threading
import time

import pytest

from yasinhub.observer.execution_store import (
    ExecutionObserverStore,
    InvalidTransitionError,
)
from yasinhub.storage.audit_store import MemoryAuditStore, reset_audit_store_for_tests


@pytest.fixture(autouse=True)
def _reset_audit():
    reset_audit_store_for_tests(MemoryAuditStore())
    yield
    reset_audit_store_for_tests(MemoryAuditStore())


def test_lifecycle_queued_running_completed():
    store = ExecutionObserverStore()
    snap = store.create_execution(task_id="job")
    assert snap.status == "queued"
    store.start(snap.execution_id, actor="ops")
    assert store.get_execution(snap.execution_id).status == "running"
    store.complete(snap.execution_id, {"ok": True}, actor="ops")
    final = store.get_execution(snap.execution_id)
    assert final.status == "succeeded"
    assert final.is_terminal()


def test_terminal_state_cannot_mutate():
    store = ExecutionObserverStore()
    snap = store.create_execution(task_id="job")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "boom")
    with pytest.raises(InvalidTransitionError):
        store.start(snap.execution_id)
    with pytest.raises(InvalidTransitionError):
        store.complete(snap.execution_id, {})


def test_cancel_from_running_is_terminal():
    store = ExecutionObserverStore()
    snap = store.create_execution(task_id="job")
    store.start(snap.execution_id)
    store.cancel(snap.execution_id, actor="ops")
    assert store.get_execution(snap.execution_id).status == "cancelled"
    again = store.cancel(snap.execution_id, actor="ops")
    assert again.status == "cancelled"


def test_durable_survives_restart():
    with tempfile.TemporaryDirectory() as d:
        s1 = ExecutionObserverStore(durable_dir=d)
        snap = s1.create_execution(task_id="persist")
        s1.start(snap.execution_id, actor="a")
        s2 = ExecutionObserverStore(durable_dir=d)
        loaded = s2.get_execution(snap.execution_id)
        assert loaded is not None
        assert loaded.status == "running"
        s2.complete(snap.execution_id, {"done": 1})
        s3 = ExecutionObserverStore(durable_dir=d)
        assert s3.get_execution(snap.execution_id).status == "succeeded"


def test_recover_stale_marks_failed():
    store = ExecutionObserverStore()
    snap = store.create_execution(task_id="stale")
    store.start(snap.execution_id)
    rec = store.get_execution(snap.execution_id)
    rec.started_at = time.time() - 10_000
    store.upsert_execution(rec)
    findings = store.recover_stale(max_age_seconds=60, actor="recovery")
    assert findings
    assert store.get_execution(snap.execution_id).status == "failed"


def test_concurrent_cancel_and_complete():
    store = ExecutionObserverStore()
    snap = store.create_execution(task_id="race")
    store.start(snap.execution_id)
    errors = []

    def cancel():
        try:
            store.cancel(snap.execution_id, actor="c")
        except Exception as exc:
            errors.append(exc)

    def complete():
        try:
            store.complete(snap.execution_id, {"x": 1}, actor="d")
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=cancel)
    t2 = threading.Thread(target=complete)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    final = store.get_execution(snap.execution_id)
    assert final.is_terminal()
    assert final.status in ("cancelled", "succeeded")
