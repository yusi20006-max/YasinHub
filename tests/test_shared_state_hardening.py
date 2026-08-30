"""Control Plane production hardening and shared state (#93)."""

from __future__ import annotations

import threading

import pytest

from yasinhub.execution.control_api import ControlRequest, get_control_api
from yasinhub.execution.policies import get_policy_engine
from yasinhub.execution.reconciliation import reconcile, reset_reconcile_state_for_tests
from yasinhub.observer.execution_store import get_default_store
from yasinhub.storage.shared_state import (
    NS_CONTROL_EVENTS,
    NS_RECONCILE_LOCKS,
    NS_SLACK_THREADS,
    FileSharedState,
    MemorySharedState,
    get_shared_state,
    reset_shared_state_for_tests,
)


@pytest.fixture(autouse=True)
def _fresh_shared_state():
    reset_shared_state_for_tests(MemorySharedState())
    reset_reconcile_state_for_tests()
    eng = get_policy_engine()
    with eng._lock:
        eng._seen_control.clear()
    yield
    reset_shared_state_for_tests(MemorySharedState())


def test_memory_cas_idempotency():
    s = MemorySharedState()
    assert s.compare_and_set("ns", "k", None, "a") is True
    assert s.compare_and_set("ns", "k", None, "b") is False
    assert s.get("ns", "k") == "a"


def test_file_backend_persists_across_instances(tmp_path):
    root = tmp_path / "state"
    a = FileSharedState(root)
    a.set(NS_CONTROL_EVENTS, "evt-1", {"claimed": True}, ttl_seconds=3600)
    b = FileSharedState(root)
    assert b.get(NS_CONTROL_EVENTS, "evt-1") == {"claimed": True}
    assert b.compare_and_set(NS_CONTROL_EVENTS, "evt-1", None, "x") is False


def test_file_cas_concurrent(tmp_path):
    root = tmp_path / "state"
    store = FileSharedState(root)
    results = []

    def claim(i):
        ok = store.compare_and_set(NS_CONTROL_EVENTS, "same-evt", None, {"worker": i})
        results.append(ok)

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for r in results if r) == 1
    assert sum(1 for r in results if not r) == 7


def test_duplicate_control_event_denied():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec-idem-1")
    store.start(snap.execution_id)
    api = get_control_api()
    r1 = api.handle(
        ControlRequest(
            action="cancel",
            actor="ops",
            source="test",
            execution_id="exec-idem-1",
            control_event_id="ctrl-dup-1",
        )
    )
    assert r1.success is True
    r2 = api.handle(
        ControlRequest(
            action="cancel",
            actor="ops",
            source="test",
            execution_id="exec-idem-1",
            control_event_id="ctrl-dup-1",
        )
    )
    assert r2.success is False
    assert r2.status_code == 403


def test_concurrent_duplicate_control_events():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec-conc-1")
    store.start(snap.execution_id)
    api = get_control_api()
    outcomes = []

    def once():
        resp = api.handle(
            ControlRequest(
                action="cancel",
                actor="ops",
                source="test",
                execution_id="exec-conc-1",
                control_event_id="ctrl-concurrent-1",
            )
        )
        outcomes.append(resp.success)

    threads = [threading.Thread(target=once) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for o in outcomes if o) <= 1
    assert sum(1 for o in outcomes if not o) >= 5


def test_idempotency_survives_store_restart(tmp_path, monkeypatch):
    root = tmp_path / "persist"
    monkeypatch.setenv("YASIN_SHARED_STATE_BACKEND", "file")
    monkeypatch.setenv("YASIN_SHARED_STATE_DIR", str(root))
    reset_shared_state_for_tests(FileSharedState(root))

    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec-restart-1")
    store.start(snap.execution_id)
    api = get_control_api()
    r1 = api.handle(
        ControlRequest(
            action="cancel",
            actor="ops",
            source="test",
            execution_id="exec-restart-1",
            control_event_id="ctrl-restart-1",
        )
    )
    assert r1.success is True

    reset_shared_state_for_tests(FileSharedState(root))
    eng = get_policy_engine()
    with eng._lock:
        eng._seen_control.clear()

    r2 = api.handle(
        ControlRequest(
            action="cancel",
            actor="ops",
            source="test",
            execution_id="exec-restart-1",
            control_event_id="ctrl-restart-1",
        )
    )
    assert r2.success is False


def test_slack_thread_persistence(tmp_path):
    root = tmp_path / "slack"
    store = FileSharedState(root)
    store.set(NS_SLACK_THREADS, "exec-thr-1", {"thread_ts": "1234.5678", "channel": "C1"})
    other = FileSharedState(root)
    val = other.get(NS_SLACK_THREADS, "exec-thr-1")
    assert isinstance(val, dict)
    assert val["thread_ts"] == "1234.5678"


def test_reconcile_lock_coordination():
    reset_reconcile_state_for_tests()
    s = get_shared_state()
    assert s.try_acquire(NS_RECONCILE_LOCKS, "global", "w1", ttl_seconds=5)
    assert s.try_acquire(NS_RECONCILE_LOCKS, "global", "w2", ttl_seconds=5) is False
    s.release(NS_RECONCILE_LOCKS, "global", "w1")
    assert s.try_acquire(NS_RECONCILE_LOCKS, "global", "w2", ttl_seconds=5) is True


def test_reconcile_skip_when_locked():
    reset_reconcile_state_for_tests()
    s = get_shared_state()
    s.try_acquire(NS_RECONCILE_LOCKS, "global", "holder", ttl_seconds=30)
    report = reconcile(dry_run=True, worker_id="other")
    assert report.summary.get("skipped") == 1 or any("skipped" in f.message for f in report.findings)


def test_pause_resume_via_control_api():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec-pause-1")
    store.start(snap.execution_id)
    api = get_control_api()
    r = api.handle(
        ControlRequest(
            action="pause",
            actor="ops",
            source="test",
            execution_id="exec-pause-1",
            control_event_id="ctrl-pause-1",
        )
    )
    assert r.success is True
    assert r.action == "pause"
    r2 = api.handle(
        ControlRequest(
            action="resume",
            actor="ops",
            source="test",
            execution_id="exec-pause-1",
            control_event_id="ctrl-resume-1",
        )
    )
    assert r2.success is True
    assert r2.action == "resume"


def test_pause_is_supported_action():
    from yasinhub.execution.control_api import SUPPORTED_ACTIONS

    assert "pause" in SUPPORTED_ACTIONS
    assert "resume" in SUPPORTED_ACTIONS


def test_identity_map_env_is_source_of_truth(monkeypatch):
    from yasinhub.integrations.slack.permissions import load_identity_map_from_env, SlackRole

    monkeypatch.setenv("YASIN_SLACK_IDENTITY_MAP", "U99:operator:bob")
    m = load_identity_map_from_env()
    assert m["U99"].role == SlackRole.OPERATOR
    assert m["U99"].yasin_user_id == "bob"
