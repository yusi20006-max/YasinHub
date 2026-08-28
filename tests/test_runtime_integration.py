"""Issue #54 — Agent ↔ Hub runtime integration tests."""
from __future__ import annotations

import json
import threading
import time
from http.server import HTTPServer
from typing import Any, Dict
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from yasinhub.adapters.agent_runtime import (
    IntegrationContext,
    bind_agent_runtime,
    get_runtime_adapter,
    resolve_integration_context,
    set_runtime_adapter,
)
from yasinhub.api.server import YasinHubHandler
from yasinhub.observer import get_default_store
from yasinhub.observer.execution_store import InvalidTransitionError
from yasinhub.observer.models import FleetSnapshot, WorkerSnapshot


class _MockRecord:
    def __init__(self, **kwargs):
        self.execution_id = kwargs["execution_id"]
        self.task_id = kwargs.get("task_id", "t")
        self.session_id = kwargs.get("session_id", "s")
        self.status = kwargs.get("status", "queued")
        self.agent_id = kwargs.get("agent_id")
        self.workspace = kwargs.get("workspace") or {
            "workspace_id": "ws-1", "path": None, "scope": "default", "metadata": {},
        }
        self.capabilities = list(kwargs.get("capabilities") or [])
        self.created_at = kwargs.get("created_at", time.time())
        self.started_at = kwargs.get("started_at")
        self.finished_at = kwargs.get("finished_at")
        self.error = kwargs.get("error")
        self.result = kwargs.get("result")
        self.metadata = dict(kwargs.get("metadata") or {})
        self.history = list(kwargs.get("history") or [self.status])
        self.cancel_requested = bool(kwargs.get("cancel_requested", False))

    def is_terminal(self):
        return self.status in ("succeeded", "failed", "cancelled")

    def as_dict(self):
        return {
            "execution_id": self.execution_id, "task_id": self.task_id,
            "session_id": self.session_id, "agent_id": self.agent_id,
            "workspace": dict(self.workspace), "capabilities": sorted(self.capabilities),
            "status": self.status, "created_at": self.created_at,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "error": self.error, "result": self.result, "metadata": dict(self.metadata),
            "history": list(self.history), "cancel_requested": self.cancel_requested,
        }


class _MockEmitter:
    def __init__(self):
        self._listeners = []
        self._seq = 0

    def subscribe(self, listener):
        self._listeners.append(listener)

    def emit(self, event_type, **kwargs):
        self._seq += 1
        event = type("E", (), {})()
        event.event_id = f"evt-mock-{self._seq}"
        event.event_type = event_type
        event.timestamp = time.time()
        event.execution_id = kwargs.get("execution_id", "")
        event.task_id = kwargs.get("task_id", "")
        event.session_id = kwargs.get("session_id", "")
        event.status = kwargs.get("status", "")
        event.metadata = dict(kwargs.get("metadata") or {})
        event.agent_id = kwargs.get("agent_id")
        event.workspace_id = kwargs.get("workspace_id")
        event.sequence = self._seq
        event.worker_id = kwargs.get("worker_id") or event.metadata.get("worker_id")
        event.parent_task_id = kwargs.get("parent_task_id") or event.task_id

        def as_dict():
            d = {
                "event_id": event.event_id, "event_type": event.event_type,
                "timestamp": event.timestamp, "execution_id": event.execution_id,
                "task_id": event.task_id, "session_id": event.session_id,
                "status": event.status, "metadata": dict(event.metadata),
                "agent_id": event.agent_id, "workspace_id": event.workspace_id,
                "sequence": event.sequence,
            }
            if event.worker_id:
                d["worker_id"] = event.worker_id
            if event.parent_task_id:
                d["parent_task_id"] = event.parent_task_id
            return d

        event.as_dict = as_dict
        for lis in list(self._listeners):
            try:
                lis(event)
            except Exception:
                pass
        return event


class MockExecutionRuntime:
    _TRANSITIONS = {
        "queued": {"running", "cancelled"},
        "running": {"paused", "succeeded", "failed", "cancelled"},
        "paused": {"running", "cancelled", "failed"},
        "succeeded": set(), "failed": set(), "cancelled": set(),
    }

    def __init__(self):
        self._execs: Dict[str, _MockRecord] = {}
        self.events = _MockEmitter()

    def create(self, *, task_id, session_id=None, agent_id=None, execution_id=None, **kw):
        eid = execution_id or f"exec-agent-{len(self._execs)+1}"
        rec = _MockRecord(
            execution_id=eid, task_id=task_id,
            session_id=session_id or f"sess-{eid[-6:]}", agent_id=agent_id, status="queued", **kw,
        )
        self._execs[eid] = rec
        self.events.emit("execution.created", execution_id=eid, task_id=task_id,
                         session_id=rec.session_id, status="queued", agent_id=agent_id)
        return rec

    def get(self, execution_id):
        return self._execs.get(execution_id)

    def list_executions(self, task_id=None, session_id=None):
        items = list(self._execs.values())
        if task_id:
            items = [e for e in items if e.task_id == task_id]
        if session_id:
            items = [e for e in items if e.session_id == session_id]
        return items

    def _transition(self, execution_id, target):
        rec = self._execs.get(execution_id)
        if rec is None:
            raise KeyError(f"unknown execution_id: {execution_id}")
        if target not in self._TRANSITIONS.get(rec.status, set()):
            raise InvalidTransitionError(rec.status, target)
        rec.status = target
        rec.history.append(target)
        if target == "running" and rec.started_at is None:
            rec.started_at = time.time()
        if target in ("succeeded", "failed", "cancelled"):
            rec.finished_at = time.time()
        if target == "cancelled":
            rec.cancel_requested = True
        return rec

    def start(self, execution_id):
        rec = self._transition(execution_id, "running")
        self.events.emit("execution.started", execution_id=execution_id, task_id=rec.task_id,
                         session_id=rec.session_id, status="running", agent_id=rec.agent_id)
        return rec

    def pause(self, execution_id):
        rec = self._transition(execution_id, "paused")
        self.events.emit("execution.paused", execution_id=execution_id, task_id=rec.task_id,
                         session_id=rec.session_id, status="paused", agent_id=rec.agent_id,
                         metadata={"cooperative": True})
        return rec

    def resume(self, execution_id):
        rec = self._transition(execution_id, "running")
        self.events.emit("execution.resumed", execution_id=execution_id, task_id=rec.task_id,
                         session_id=rec.session_id, status="running", agent_id=rec.agent_id)
        return rec

    def cancel(self, execution_id):
        rec = self._execs.get(execution_id)
        if rec is None:
            raise KeyError(f"unknown execution_id: {execution_id}")
        if rec.is_terminal():
            return rec
        rec = self._transition(execution_id, "cancelled")
        self.events.emit("execution.cancelled", execution_id=execution_id, task_id=rec.task_id,
                         session_id=rec.session_id, status="cancelled", agent_id=rec.agent_id)
        return rec


class MockWorkerFleet:
    def __init__(self, runtime: MockExecutionRuntime):
        self.runtime = runtime
        self._statuses: Dict[str, Dict[str, Any]] = {}

    def register_task(self, task_id, workers):
        self._statuses[task_id] = {"task_id": task_id, "status": "running", "workers": workers}

    def status(self, task_id):
        data = self._statuses.get(task_id)
        if data is None:
            raise KeyError(f"unknown fleet: {task_id}")
        return type("FS", (), {"as_dict": lambda self=None, d=data: dict(d)})()

    def cancel(self, task_id):
        data = self._statuses.get(task_id)
        if data is None:
            raise KeyError(f"unknown fleet: {task_id}")
        for w in data["workers"]:
            eid = w.get("execution_id")
            if eid:
                try:
                    self.runtime.cancel(eid)
                except Exception:
                    pass
                w["status"] = "cancelled"
                w["cancellation_state"] = "requested"
        data["status"] = "cancelling"


@pytest.fixture(autouse=True)
def _reset():
    store = get_default_store()
    store.clear()
    set_runtime_adapter(None)
    yield
    store.clear()
    set_runtime_adapter(None)


@pytest.fixture
def runtime():
    return MockExecutionRuntime()


@pytest.fixture
def adapter(runtime):
    return bind_agent_runtime(runtime)


@pytest.fixture
def ctx():
    return IntegrationContext(request_id="req-test-1", actor="hub-system")


def test_real_execution_registration(adapter, runtime):
    rec = runtime.create(task_id="task-reg", agent_id="agent-1", capabilities=["read"])
    snap = adapter.register_execution(rec.as_dict())
    assert snap.execution_id == rec.execution_id and snap.status == "queued"


def test_state_synchronization(adapter, runtime):
    rec = runtime.create(task_id="sync")
    adapter.register_execution(rec.as_dict())
    runtime.start(rec.execution_id)
    snap = adapter.sync_execution(rec.execution_id)
    assert snap is not None and snap.status == "running"


def test_event_ingestion_and_ordering(adapter, runtime):
    rec = runtime.create(task_id="ev")
    adapter.register_execution(rec.as_dict())
    runtime.start(rec.execution_id)
    runtime.pause(rec.execution_id)
    events = get_default_store().list_events(execution_id=rec.execution_id)
    seqs = [e.sequence for e in events]
    assert seqs == sorted(seqs)


def test_duplicate_event_handling(adapter):
    data = {
        "event_id": "evt-dup-1", "event_type": "execution.started",
        "execution_id": "exec-d", "task_id": "t", "session_id": "s",
        "status": "running", "timestamp": time.time(), "sequence": 1,
    }
    adapter.register_execution({"execution_id": "exec-d", "task_id": "t", "session_id": "s", "status": "queued"})
    assert adapter.ingest_event(data) is not None
    assert adapter.ingest_event(data) is None


def test_execution_session_correlation(adapter, runtime):
    r1 = runtime.create(task_id="parent", session_id="sess-a")
    r2 = runtime.create(task_id="parent", session_id="sess-b")
    adapter.register_execution(r1.as_dict())
    adapter.register_execution(r2.as_dict())
    assert r1.session_id != r2.session_id
    assert len(adapter.list_executions(task_id="parent")) == 2


def test_fleet_parent_worker_execution_correlation(adapter, runtime):
    e1 = runtime.create(task_id="fleet-p", session_id="s1")
    e2 = runtime.create(task_id="fleet-p", session_id="s2")
    workers = [
        {"worker_id": "worker-b", "role": "reviewer", "status": "running",
         "execution_id": e2.execution_id, "session_id": e2.session_id},
        {"worker_id": "worker-a", "role": "researcher", "status": "running",
         "execution_id": e1.execution_id, "session_id": e1.session_id},
    ]
    projected = adapter.register_fleet({"task_id": "fleet-p", "status": "running", "workers": workers})
    assert [w.worker_id for w in projected.workers] == ["worker-a", "worker-b"]


def test_worker_isolation(adapter, runtime):
    e1 = runtime.create(task_id="iso", session_id="sa")
    e2 = runtime.create(task_id="iso", session_id="sb")
    assert e1.session_id != e2.session_id and e1.execution_id != e2.execution_id


def test_deterministic_aggregation():
    store = get_default_store()
    workers = [
        WorkerSnapshot(worker_id="w2", status="failed", error="x"),
        WorkerSnapshot(worker_id="w1", status="succeeded"),
    ]
    assert store.aggregate_fleet_status(workers) == "completed_with_failures"


def test_pause_resume_cancel_via_adapter(adapter, runtime, ctx):
    rec = runtime.create(task_id="ctl")
    adapter.register_execution(rec.as_dict())
    runtime.start(rec.execution_id)
    assert adapter.pause(rec.execution_id, context=ctx)["status"] == "paused"
    assert adapter.resume(rec.execution_id, context=ctx)["status"] == "running"
    assert adapter.cancel(rec.execution_id, context=ctx)["status"] == "cancelled"
    assert runtime.get(rec.execution_id).status == "cancelled"


def test_invalid_transition_409(adapter, runtime, ctx):
    rec = runtime.create(task_id="bad")
    adapter.register_execution(rec.as_dict())
    with pytest.raises(InvalidTransitionError):
        adapter.pause(rec.execution_id, context=ctx)


def test_unknown_execution_404(adapter, ctx):
    with pytest.raises(KeyError):
        adapter.pause("exec-missing", context=ctx)


def test_fleet_cancellation_propagation(adapter, runtime, ctx):
    fleet = MockWorkerFleet(runtime)
    e1 = runtime.create(task_id="fc", session_id="s1")
    e2 = runtime.create(task_id="fc", session_id="s2")
    runtime.start(e1.execution_id)
    runtime.start(e2.execution_id)
    workers = [
        {"worker_id": "w1", "status": "running", "execution_id": e1.execution_id, "session_id": e1.session_id},
        {"worker_id": "w2", "status": "running", "execution_id": e2.execution_id, "session_id": e2.session_id},
    ]
    fleet.register_task("fc", workers)
    adapter._fleet = fleet
    adapter.register_fleet({"task_id": "fc", "status": "running", "workers": workers})
    get_default_store().upsert_fleet(FleetSnapshot(
        task_id="fc", status="running",
        workers=[
            WorkerSnapshot(worker_id="w1", status="running", execution_id=e1.execution_id, session_id=e1.session_id),
            WorkerSnapshot(worker_id="w2", status="running", execution_id=e2.execution_id, session_id=e2.session_id),
        ],
    ))
    result = adapter.cancel_fleet("fc", context=ctx)
    assert result["status"] in ("cancelling", "cancelled")
    assert runtime.get(e1.execution_id).status == "cancelled"


def test_unknown_fleet_404(adapter, ctx):
    with pytest.raises(KeyError):
        adapter.cancel_fleet("fleet-missing", context=ctx)


def test_actor_boundary_does_not_trust_client():
    ctx = resolve_integration_context({"actor": "evil-admin", "request_id": "r-1"})
    assert ctx.actor == "hub-system"
    assert ctx.metadata.get("actor_hint") == "evil-admin"


def test_request_id_propagation(adapter, runtime, ctx):
    rec = runtime.create(task_id="rid")
    adapter.register_execution(rec.as_dict())
    runtime.start(rec.execution_id)
    adapter.pause(rec.execution_id, context=ctx)
    events = get_default_store().list_events(execution_id=rec.execution_id)
    assert any(e.metadata.get("request_id") == ctx.request_id for e in events)


def test_secret_redaction_in_events(adapter, runtime, ctx):
    rec = runtime.create(task_id="sec", metadata={"api_key": "sk-abcdefghijklmnopqrstuvwxyz", "note": "ok"})
    adapter.register_execution(rec.as_dict())
    snap = get_default_store().get_execution(rec.execution_id)
    assert snap.metadata.get("api_key") == "***"
    for e in get_default_store().list_events(execution_id=rec.execution_id):
        assert "sk-" not in json.dumps(e.as_dict())


def test_no_privilege_escalation_via_actor_hint(adapter, runtime):
    evil = IntegrationContext(request_id="r-evil", actor="hub-system", metadata={"actor_hint": "root"})
    rec = runtime.create(task_id="priv")
    adapter.register_execution(rec.as_dict())
    runtime.start(rec.execution_id)
    adapter.pause(rec.execution_id, context=evil)
    for e in get_default_store().list_events(execution_id=rec.execution_id):
        if e.metadata.get("actor"):
            assert e.metadata["actor"] == "hub-system"


@pytest.fixture
def api_server():
    server = HTTPServer(("127.0.0.1", 0), YasinHubHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def _post(url, body=None):
    data = json.dumps(body or {}).encode()
    req = Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode()), resp.status
    except HTTPError as e:
        return json.loads(e.read().decode()), e.code


def test_api_control_via_bound_adapter(api_server, adapter, runtime):
    rec = runtime.create(task_id="api-ctl")
    adapter.register_execution(rec.as_dict())
    runtime.start(rec.execution_id)
    data, status = _post(
        f"{api_server}/api/executions/{rec.execution_id}/pause",
        {"actor": "pwa", "request_id": "req-api-1"},
    )
    assert status == 200 and data["success"] is True
    assert data["execution"]["status"] == "paused"
    assert runtime.get(rec.execution_id).status == "paused"


def test_api_unknown_execution_with_adapter(api_server, adapter):
    data, status = _post(f"{api_server}/api/executions/exec-nope/cancel", {})
    assert status == 404 and data["error"] == "unknown execution"


def test_api_invalid_transition_with_adapter(api_server, adapter, runtime):
    rec = runtime.create(task_id="inv-api")
    adapter.register_execution(rec.as_dict())
    data, status = _post(f"{api_server}/api/executions/{rec.execution_id}/pause", {})
    assert status == 409 and data["error"] == "invalid transition"


def test_unbound_adapter_preserves_store_control():
    set_runtime_adapter(None)
    adapter = get_runtime_adapter()
    store = get_default_store()
    snap = store.create_execution(task_id="local")
    store.start(snap.execution_id)
    ctx = IntegrationContext(request_id="r-local", actor="hub-system")
    assert adapter.pause(snap.execution_id, context=ctx)["status"] == "paused"
