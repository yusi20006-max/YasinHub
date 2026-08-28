"""Tests for Execution Observer (#50), Fleet (#51), Control Plane (#52)."""
from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from yasinhub.api.server import YasinHubHandler
from yasinhub.observer import get_default_store
from yasinhub.observer.execution_store import InvalidTransitionError, redact_secrets
from yasinhub.observer.models import FleetSnapshot, WorkerSnapshot


@pytest.fixture(autouse=True)
def _clean_store():
    store = get_default_store()
    store.clear()
    yield
    store.clear()


@pytest.fixture
def store():
    return get_default_store()


def test_redact_secrets_keys_and_values():
    data = {
        "api_key": "sk-secret1234567890abcdef",
        "token": "bearer abc.def",
        "safe": "hello",
        "nested": {"password": "p@ss", "ok": 1},
    }
    out = redact_secrets(data)
    assert out["api_key"] == "***"
    assert out["token"] == "***"
    assert out["safe"] == "hello"
    assert out["nested"]["password"] == "***"
    assert "sk-" not in json.dumps(out)


def test_create_and_get_execution(store):
    snap = store.create_execution(
        task_id="task-1",
        agent_id="agent-a",
        capabilities=["search", "read"],
        metadata={"note": "ok", "api_key": "secret"},
    )
    assert snap.status == "queued"
    assert snap.execution_id.startswith("exec-")
    assert snap.metadata.get("api_key") == "***"
    got = store.get_execution(snap.execution_id)
    assert got is not None and got.task_id == "task-1"
    assert sorted(got.capabilities) == ["read", "search"]


def test_list_executions_filters(store):
    a = store.create_execution(task_id="t1", session_id="s1")
    store.create_execution(task_id="t1", session_id="s2")
    store.create_execution(task_id="t2", session_id="s1")
    store.start(a.execution_id)
    assert len(store.list_executions(task_id="t1")) == 2
    assert len(store.list_executions(status="running")) == 1


def test_successful_execution_lifecycle(store):
    snap = store.create_execution(task_id="ok")
    store.start(snap.execution_id)
    done = store.complete(snap.execution_id, result={"value": 42})
    assert done.status == "succeeded" and done.result == {"value": 42}
    events = store.list_events(execution_id=snap.execution_id)
    assert "execution.created" in [e.event_type for e in events]
    seqs = [e.sequence for e in events]
    assert seqs == sorted(seqs)


def test_failed_execution(store):
    snap = store.create_execution(task_id="fail")
    store.start(snap.execution_id)
    failed = store.fail(snap.execution_id, "boom api_key=sk-abcdef0123456789")
    assert failed.status == "failed" and failed.error and "sk-" not in failed.error


def test_cancelled_execution(store):
    snap = store.create_execution(task_id="cancel-me")
    store.start(snap.execution_id)
    cancelled = store.cancel(snap.execution_id)
    assert cancelled.status == "cancelled" and cancelled.cancel_requested


def test_unknown_execution(store):
    assert store.get_execution("exec-does-not-exist") is None
    with pytest.raises(KeyError):
        store.pause("exec-does-not-exist")


def test_as_dict_no_secrets_and_deterministic(store):
    snap = store.create_execution(
        task_id="det", capabilities=["b", "a"], metadata={"password": "x"}
    )
    d = snap.as_dict()
    assert d["capabilities"] == ["a", "b"]
    assert d["metadata"].get("password") == "***"
    assert json.dumps(d, sort_keys=True) == json.dumps(snap.as_dict(), sort_keys=True)


def test_fleet_two_workers_parallel(store):
    e1 = store.create_execution(task_id="fleet-1", session_id="sess-w1")
    e2 = store.create_execution(task_id="fleet-1", session_id="sess-w2")
    store.start(e1.execution_id)
    store.start(e2.execution_id)
    workers = [
        WorkerSnapshot(
            worker_id="worker-b",
            role="reviewer",
            objective="review",
            status="running",
            execution_id=e2.execution_id,
            session_id=e2.session_id,
        ),
        WorkerSnapshot(
            worker_id="worker-a",
            role="researcher",
            objective="collect",
            status="running",
            execution_id=e1.execution_id,
            session_id=e1.session_id,
        ),
    ]
    stored = store.upsert_fleet(FleetSnapshot(task_id="fleet-1", status="running", workers=workers))
    assert [w.worker_id for w in stored.workers] == ["worker-a", "worker-b"]


def test_fleet_isolation_identities(store):
    e1 = store.create_execution(task_id="iso", session_id="s-a")
    e2 = store.create_execution(task_id="iso", session_id="s-b")
    assert e1.session_id != e2.session_id and e1.execution_id != e2.execution_id


def test_fleet_partial_failure_aggregation(store):
    workers = [
        WorkerSnapshot(worker_id="w1", status="succeeded"),
        WorkerSnapshot(worker_id="w2", status="failed", error="x"),
    ]
    assert store.aggregate_fleet_status(workers) == "completed_with_failures"


def test_fleet_all_succeeded(store):
    assert (
        store.aggregate_fleet_status(
            [
                WorkerSnapshot(worker_id="w1", status="succeeded"),
                WorkerSnapshot(worker_id="w2", status="succeeded"),
            ]
        )
        == "succeeded"
    )


def test_fleet_all_failed(store):
    assert (
        store.aggregate_fleet_status(
            [
                WorkerSnapshot(worker_id="w1", status="failed"),
                WorkerSnapshot(worker_id="w2", status="failed"),
            ]
        )
        == "failed"
    )


def test_fleet_cancelled(store):
    assert (
        store.aggregate_fleet_status(
            [
                WorkerSnapshot(worker_id="w1", status="cancelled"),
                WorkerSnapshot(worker_id="w2", status="cancelled"),
            ]
        )
        == "cancelled"
    )


def test_fleet_running(store):
    assert (
        store.aggregate_fleet_status(
            [
                WorkerSnapshot(worker_id="w1", status="running"),
                WorkerSnapshot(worker_id="w2", status="succeeded"),
            ]
        )
        == "running"
    )


def test_event_correlation_parent_worker_session(store):
    e = store.create_execution(task_id="parent-1", session_id="sess-w")
    store.emit_event(
        event_type="worker.registered",
        execution_id=e.execution_id,
        task_id="parent-1",
        session_id=e.session_id,
        status="queued",
        worker_id="w1",
        parent_task_id="parent-1",
        metadata={"worker_id": "w1"},
    )
    events = store.list_events(task_id="parent-1", worker_id="w1")
    assert events[-1].worker_id == "w1" and events[-1].parent_task_id == "parent-1"


def test_stale_unknown_events_do_not_break_list(store):
    store.emit_event(
        event_type="unknown.custom",
        execution_id="exec-stale",
        task_id="t-stale",
        session_id="s-stale",
        status="unknown",
    )
    assert len(store.list_events(task_id="t-stale")) == 1


def test_pause_resume_valid(store):
    snap = store.create_execution(task_id="ctrl")
    store.start(snap.execution_id)
    assert store.pause(snap.execution_id, actor="hub-user", request_id="r1").status == "paused"
    assert store.resume(snap.execution_id, actor="hub-user", request_id="r2").status == "running"


def test_invalid_transition_rejected(store):
    snap = store.create_execution(task_id="bad")
    with pytest.raises(InvalidTransitionError) as ei:
        store.pause(snap.execution_id)
    assert ei.value.current == "queued"
    store.start(snap.execution_id)
    store.complete(snap.execution_id)
    with pytest.raises(InvalidTransitionError):
        store.pause(snap.execution_id)


def test_cancel_idempotent_on_terminal(store):
    snap = store.create_execution(task_id="term")
    store.start(snap.execution_id)
    store.complete(snap.execution_id)
    assert store.cancel(snap.execution_id).status == "succeeded"


def test_parent_cancellation_propagates(store):
    e1 = store.create_execution(task_id="parent-c", session_id="s1")
    e2 = store.create_execution(task_id="parent-c", session_id="s2")
    store.start(e1.execution_id)
    store.start(e2.execution_id)
    store.upsert_fleet(
        FleetSnapshot(
            task_id="parent-c",
            status="running",
            workers=[
                WorkerSnapshot(
                    worker_id="w1",
                    status="running",
                    execution_id=e1.execution_id,
                    session_id=e1.session_id,
                ),
                WorkerSnapshot(
                    worker_id="w2",
                    status="running",
                    execution_id=e2.execution_id,
                    session_id=e2.session_id,
                ),
            ],
        )
    )
    result = store.cancel_fleet("parent-c", actor="ops", request_id="cancel-1")
    assert result.status in ("cancelling", "cancelled")
    for w in result.workers:
        assert w.status == "cancelled" or w.cancellation_state == "requested"


def test_control_events_audit_safe_no_secrets(store):
    snap = store.create_execution(
        task_id="audit", metadata={"api_token": "ghp_abcdefghijklmnopqrstuvwxyz"}
    )
    store.start(snap.execution_id)
    store.pause(snap.execution_id, actor="auditor", request_id="req-secret-test")
    for e in store.list_events(execution_id=snap.execution_id):
        assert "ghp_" not in json.dumps(e.as_dict())


@pytest.fixture
def api_server():
    server = HTTPServer(("127.0.0.1", 0), YasinHubHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def _get(url: str):
    try:
        with urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode()), resp.status
    except HTTPError as e:
        return json.loads(e.read().decode()), e.code


def _post(url: str, body=None):
    data = json.dumps(body or {}).encode()
    req = Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode()), resp.status
    except HTTPError as e:
        return json.loads(e.read().decode()), e.code


def test_api_list_and_get_execution(api_server, store):
    snap = store.create_execution(task_id="api-t")
    store.start(snap.execution_id)
    data, status = _get(f"{api_server}/api/executions")
    assert status == 200 and data["count"] >= 1
    data, status = _get(f"{api_server}/api/executions/{snap.execution_id}")
    assert status == 200 and data["execution"]["status"] == "running"


def test_api_unknown_execution(api_server):
    data, status = _get(f"{api_server}/api/executions/exec-missing")
    assert status == 404 and data["error"] == "unknown execution"


def test_api_execution_events(api_server, store):
    snap = store.create_execution(task_id="ev")
    store.start(snap.execution_id)
    data, status = _get(f"{api_server}/api/executions/{snap.execution_id}/events")
    assert status == 200 and data["count"] >= 1
    assert [e["sequence"] for e in data["events"]] == sorted(e["sequence"] for e in data["events"])


def test_api_malformed_control_body(api_server, store):
    snap = store.create_execution(task_id="mal")
    store.start(snap.execution_id)
    req = Request(
        f"{api_server}/api/executions/{snap.execution_id}/pause",
        data=b"not-json{{{",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urlopen(req, timeout=5)
        assert False
    except HTTPError as e:
        assert e.code == 400
        assert json.loads(e.read().decode())["error"] == "malformed request body"


def test_api_pause_resume_cancel(api_server, store):
    snap = store.create_execution(task_id="ctl-api")
    store.start(snap.execution_id)
    data, status = _post(
        f"{api_server}/api/executions/{snap.execution_id}/pause", {"actor": "pwa"}
    )
    assert status == 200 and data["execution"]["status"] == "paused"
    data, status = _post(
        f"{api_server}/api/executions/{snap.execution_id}/resume", {"actor": "pwa"}
    )
    assert status == 200 and data["execution"]["status"] == "running"
    data, status = _post(
        f"{api_server}/api/executions/{snap.execution_id}/cancel", {"actor": "pwa"}
    )
    assert status == 200 and data["execution"]["status"] == "cancelled"


def test_api_invalid_transition(api_server, store):
    snap = store.create_execution(task_id="inv")
    data, status = _post(f"{api_server}/api/executions/{snap.execution_id}/pause", {})
    assert status == 409 and data["error"] == "invalid transition"


def test_api_fleets(api_server, store):
    e1 = store.create_execution(task_id="f-api")
    store.upsert_fleet(
        FleetSnapshot(
            task_id="f-api",
            status="running",
            workers=[
                WorkerSnapshot(
                    worker_id="w1",
                    status="running",
                    execution_id=e1.execution_id,
                    session_id=e1.session_id,
                    role="r",
                    objective="o",
                )
            ],
        )
    )
    data, status = _get(f"{api_server}/api/fleets")
    assert status == 200 and data["count"] >= 1
    data, status = _get(f"{api_server}/api/fleets/f-api")
    assert status == 200 and data["fleet"]["workers"][0]["worker_id"] == "w1"


def test_api_fleet_cancel(api_server, store):
    e1 = store.create_execution(task_id="f-cancel")
    store.start(e1.execution_id)
    store.upsert_fleet(
        FleetSnapshot(
            task_id="f-cancel",
            status="running",
            workers=[
                WorkerSnapshot(
                    worker_id="w1",
                    status="running",
                    execution_id=e1.execution_id,
                    session_id=e1.session_id,
                )
            ],
        )
    )
    data, status = _post(f"{api_server}/api/fleets/f-cancel/cancel", {"actor": "ops"})
    assert status == 200 and data["success"] is True
    assert data["fleet"]["workers"][0]["status"] == "cancelled"
