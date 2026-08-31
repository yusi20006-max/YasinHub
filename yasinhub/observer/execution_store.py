"""
Execution Observer Store — observation and control-plane data layer for YasinHub.

Consumes Yasin-Agent #26–#28 contracts without owning execution or governance.
Secrets are never returned. Serialization is deterministic.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence, Set

from .models import (
    ExecutionSnapshot,
    FleetSnapshot,
    StructuredEvent,
    WorkerSnapshot,
    WorkspaceSnapshot,
)

_TERMINAL: Set[str] = {"succeeded", "failed", "cancelled"}
_TRANSITIONS: Dict[str, Set[str]] = {
    "queued": {"running", "cancelled"},
    "running": {"paused", "succeeded", "failed", "cancelled"},
    "paused": {"running", "cancelled", "failed"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
}

_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|credential|authorization|bearer|"
    r"private[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._\-+/=]{8,}|sk-[a-z0-9]{16,}|ghp_[a-z0-9]{20,})"
)


def redact_secrets(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact secret-looking keys and common secret patterns."""
    if _depth > 8:
        return "<max-depth>"
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if _SECRET_KEY_RE.search(key_str):
                out[key_str] = "***"
            else:
                out[key_str] = redact_secrets(item, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item, _depth=_depth + 1) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE_RE.sub("***", value)
    return value


class InvalidTransitionError(Exception):
    """Raised when an execution lifecycle transition is not allowed."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid execution transition: {current} -> {target}")


class ExecutionObserverStore:
    """In-process store for observable executions, events, and fleet snapshots."""

    def __init__(self) -> None:
        self._executions: Dict[str, ExecutionSnapshot] = {}
        self._events: List[StructuredEvent] = []
        self._fleets: Dict[str, FleetSnapshot] = {}
        self._seq = 0
        self._lock = threading.RLock()

    def upsert_execution(self, snapshot: ExecutionSnapshot) -> ExecutionSnapshot:
        safe = ExecutionSnapshot(
            execution_id=snapshot.execution_id,
            task_id=snapshot.task_id,
            session_id=snapshot.session_id,
            status=snapshot.status,
            agent_id=snapshot.agent_id,
            workspace=snapshot.workspace,
            capabilities=list(snapshot.capabilities),
            created_at=snapshot.created_at,
            started_at=snapshot.started_at,
            finished_at=snapshot.finished_at,
            error=redact_secrets(snapshot.error) if snapshot.error else None,
            result=redact_secrets(snapshot.result),
            metadata=redact_secrets(dict(snapshot.metadata)),
            history=list(snapshot.history),
            cancel_requested=snapshot.cancel_requested,
        )
        if safe.workspace and safe.workspace.metadata:
            safe.workspace = WorkspaceSnapshot(
                workspace_id=safe.workspace.workspace_id,
                path=safe.workspace.path,
                scope=safe.workspace.scope,
                metadata=redact_secrets(dict(safe.workspace.metadata)),
            )
        with self._lock:
            self._executions[safe.execution_id] = safe
        return safe

    def get_execution(self, execution_id: str) -> Optional[ExecutionSnapshot]:
        with self._lock:
            return self._executions.get(execution_id)

    def list_executions(
        self,
        *,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[ExecutionSnapshot]:
        with self._lock:
            items = list(self._executions.values())
        if task_id is not None:
            items = [e for e in items if e.task_id == task_id]
        if session_id is not None:
            items = [e for e in items if e.session_id == session_id]
        if status is not None:
            items = [e for e in items if e.status == status]
        items.sort(key=lambda e: (e.created_at or 0.0, e.execution_id))
        return items

    def create_execution(
        self,
        *,
        task_id: str,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        capabilities: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        execution_id: Optional[str] = None,
    ) -> ExecutionSnapshot:
        eid = execution_id or f"exec-{uuid.uuid4().hex[:16]}"
        sid = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        ws = WorkspaceSnapshot(workspace_id=workspace_id or f"ws-{uuid.uuid4().hex[:12]}")
        snap = ExecutionSnapshot(
            execution_id=eid,
            task_id=task_id,
            session_id=sid,
            status="queued",
            agent_id=agent_id,
            workspace=ws,
            capabilities=list(capabilities or ()),
            created_at=time.time(),
            metadata=redact_secrets(dict(metadata or {})),
            history=["queued"],
        )
        self.upsert_execution(snap)
        self.emit_event(
            event_type="execution.created",
            execution_id=eid,
            task_id=task_id,
            session_id=sid,
            status="queued",
            agent_id=agent_id,
            workspace_id=ws.workspace_id,
        )
        return snap

    def emit_event(
        self,
        *,
        event_type: str,
        execution_id: str,
        task_id: str,
        session_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
    ) -> StructuredEvent:
        with self._lock:
            self._seq += 1
            seq = self._seq
        event = StructuredEvent(
            event_id=f"evt-{uuid.uuid4().hex[:16]}",
            event_type=event_type,
            timestamp=time.time(),
            execution_id=execution_id,
            task_id=task_id,
            session_id=session_id,
            status=status,
            metadata=redact_secrets(dict(metadata or {})),
            agent_id=agent_id,
            workspace_id=workspace_id,
            sequence=seq,
            worker_id=worker_id,
            parent_task_id=parent_task_id,
        )
        with self._lock:
            self._events.append(event)
        return event

    def list_events(
        self,
        *,
        execution_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[StructuredEvent]:
        with self._lock:
            events = list(self._events)
        if execution_id is not None:
            events = [e for e in events if e.execution_id == execution_id]
        if task_id is not None:
            events = [e for e in events if e.task_id == task_id]
        if session_id is not None:
            events = [e for e in events if e.session_id == session_id]
        if worker_id is not None:
            events = [e for e in events if e.worker_id == worker_id]
        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]
        events.sort(key=lambda e: (e.sequence, e.timestamp, e.event_id))
        if limit is not None:
            try:
                lim = int(limit)
                if lim >= 0:
                    events = events[-lim:] if lim else events
            except (TypeError, ValueError):
                pass
        return events

    def _transition(
        self,
        execution_id: str,
        target: str,
        *,
        actor: Optional[str] = None,
        request_id: Optional[str] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> ExecutionSnapshot:
        with self._lock:
            rec = self._executions.get(execution_id)
            if rec is None:
                raise KeyError(f"unknown execution_id: {execution_id}")
            current = rec.status
            allowed = _TRANSITIONS.get(current, set())
            if target not in allowed:
                raise InvalidTransitionError(current, target)
            history = list(rec.history) + [target]
            started_at = rec.started_at
            finished_at = rec.finished_at
            now = time.time()
            if target == "running" and started_at is None:
                started_at = now
            if target in _TERMINAL:
                finished_at = now
            cancel_requested = rec.cancel_requested or (target == "cancelled")
            updated = ExecutionSnapshot(
                execution_id=rec.execution_id,
                task_id=rec.task_id,
                session_id=rec.session_id,
                status=target,
                agent_id=rec.agent_id,
                workspace=rec.workspace,
                capabilities=list(rec.capabilities),
                created_at=rec.created_at,
                started_at=started_at,
                finished_at=finished_at,
                error=rec.error,
                result=rec.result,
                metadata=dict(rec.metadata),
                history=history,
                cancel_requested=cancel_requested,
            )
            self._executions[execution_id] = updated
        meta: Dict[str, Any] = {"status": target}
        if actor:
            meta["actor"] = actor
        if request_id:
            meta["request_id"] = request_id
        if extra_meta:
            meta.update(extra_meta)
        event_type_map = {
            "running": "execution.started",
            "paused": "execution.paused",
            "succeeded": "execution.completed",
            "failed": "execution.failed",
            "cancelled": "execution.cancelled",
        }
        et = (
            "execution.resumed"
            if current == "paused" and target == "running"
            else event_type_map.get(target, "execution.state_changed")
        )
        self.emit_event(
            event_type=et,
            execution_id=updated.execution_id,
            task_id=updated.task_id,
            session_id=updated.session_id,
            status=target,
            metadata=meta,
            agent_id=updated.agent_id,
            workspace_id=updated.workspace.workspace_id if updated.workspace else None,
        )
        self.emit_event(
            event_type="execution.state_changed",
            execution_id=updated.execution_id,
            task_id=updated.task_id,
            session_id=updated.session_id,
            status=target,
            metadata=meta,
            agent_id=updated.agent_id,
            workspace_id=updated.workspace.workspace_id if updated.workspace else None,
        )
        return updated

    def pause(
        self, execution_id: str, *, actor: Optional[str] = None, request_id: Optional[str] = None
    ) -> ExecutionSnapshot:
        return self._transition(
            execution_id, "paused", actor=actor, request_id=request_id, extra_meta={"cooperative": True}
        )

    def resume(
        self, execution_id: str, *, actor: Optional[str] = None, request_id: Optional[str] = None
    ) -> ExecutionSnapshot:
        return self._transition(execution_id, "running", actor=actor, request_id=request_id)

    def cancel(
        self, execution_id: str, *, actor: Optional[str] = None, request_id: Optional[str] = None
    ) -> ExecutionSnapshot:
        with self._lock:
            rec = self._executions.get(execution_id)
            if rec is None:
                raise KeyError(f"unknown execution_id: {execution_id}")
            if rec.is_terminal():
                return rec
        return self._transition(execution_id, "cancelled", actor=actor, request_id=request_id)

    def complete(
        self, execution_id: str, result: Any = None, *, actor: Optional[str] = None
    ) -> ExecutionSnapshot:
        with self._lock:
            rec = self._executions.get(execution_id)
            if rec is None:
                raise KeyError(f"unknown execution_id: {execution_id}")
            if rec.cancel_requested and not rec.is_terminal():
                return self.cancel(execution_id, actor=actor)
            rec.result = redact_secrets(result)
            self._executions[execution_id] = rec
        return self._transition(execution_id, "succeeded", actor=actor)

    def fail(
        self, execution_id: str, error: str, *, actor: Optional[str] = None
    ) -> ExecutionSnapshot:
        with self._lock:
            rec = self._executions.get(execution_id)
            if rec is None:
                raise KeyError(f"unknown execution_id: {execution_id}")
            rec.error = str(redact_secrets(error))
            self._executions[execution_id] = rec
            if rec.is_terminal():
                return rec
        return self._transition(execution_id, "failed", actor=actor)

    def start(self, execution_id: str, *, actor: Optional[str] = None) -> ExecutionSnapshot:
        return self._transition(execution_id, "running", actor=actor)

    def upsert_fleet(self, fleet: FleetSnapshot) -> FleetSnapshot:
        ordered = sorted(fleet.workers, key=lambda w: w.worker_id)
        safe_workers = [
            WorkerSnapshot(
                worker_id=w.worker_id,
                role=w.role,
                objective=w.objective,
                status=w.status,
                execution_id=w.execution_id,
                session_id=w.session_id,
                progress=redact_secrets(w.progress),
                result=redact_secrets(w.result),
                error=str(redact_secrets(w.error)) if w.error else None,
                cancellation_state=w.cancellation_state,
                agent_id=w.agent_id,
            )
            for w in ordered
        ]
        snap = FleetSnapshot(task_id=fleet.task_id, status=fleet.status, workers=safe_workers)
        with self._lock:
            self._fleets[snap.task_id] = snap
        return snap

    def get_fleet(self, task_id: str) -> Optional[FleetSnapshot]:
        with self._lock:
            return self._fleets.get(task_id)

    def list_fleets(self) -> List[FleetSnapshot]:
        with self._lock:
            items = list(self._fleets.values())
        items.sort(key=lambda f: f.task_id)
        return items

    def aggregate_fleet_status(self, workers: Sequence[WorkerSnapshot]) -> str:
        if not workers:
            return "unknown"
        statuses = {w.status for w in workers}
        if statuses <= {"succeeded"}:
            return "succeeded"
        if statuses <= {"cancelled"}:
            return "cancelled"
        if "running" in statuses or "queued" in statuses or "paused" in statuses:
            if any(w.cancellation_state == "requested" for w in workers):
                return "cancelling"
            return "running"
        if "failed" in statuses and ("succeeded" in statuses or "cancelled" in statuses):
            return "completed_with_failures"
        if statuses <= {"failed"}:
            return "failed"
        if "failed" in statuses:
            return "completed_with_failures"
        if "cancelled" in statuses:
            return "cancelled"
        if "succeeded" in statuses:
            return "succeeded"
        return "unknown"

    def cancel_fleet(
        self,
        task_id: str,
        *,
        actor: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> FleetSnapshot:
        fleet = self.get_fleet(task_id)
        if fleet is None:
            raise KeyError(f"unknown fleet task_id: {task_id}")
        updated_workers: List[WorkerSnapshot] = []
        for w in fleet.workers:
            if w.execution_id and w.status not in _TERMINAL:
                try:
                    self.cancel(w.execution_id, actor=actor, request_id=request_id)
                    exec_snap = self.get_execution(w.execution_id)
                    new_status = exec_snap.status if exec_snap else "cancelled"
                except (KeyError, InvalidTransitionError):
                    new_status = "cancelled"
                updated_workers.append(
                    WorkerSnapshot(
                        worker_id=w.worker_id,
                        role=w.role,
                        objective=w.objective,
                        status=new_status,
                        execution_id=w.execution_id,
                        session_id=w.session_id,
                        progress=w.progress,
                        result=w.result,
                        error=w.error,
                        cancellation_state="requested",
                        agent_id=w.agent_id,
                    )
                )
            else:
                updated_workers.append(w)
        status = self.aggregate_fleet_status(updated_workers)
        if any(w.status not in _TERMINAL for w in updated_workers):
            status = "cancelling"
        new_fleet = FleetSnapshot(task_id=task_id, status=status, workers=updated_workers)
        self.upsert_fleet(new_fleet)
        self.emit_event(
            event_type="fleet.cancel_requested",
            execution_id="",
            task_id=task_id,
            session_id="",
            status=status,
            metadata={"actor": actor, "request_id": request_id, "worker_count": len(updated_workers)},
            parent_task_id=task_id,
        )
        return new_fleet

    def clear(self) -> None:
        with self._lock:
            self._executions.clear()
            self._events.clear()
            self._fleets.clear()
            self._seq = 0


_default_store: Optional[ExecutionObserverStore] = None
_default_lock = threading.Lock()


def get_default_store() -> ExecutionObserverStore:
    global _default_store
    with _default_lock:
        if _default_store is None:
            _default_store = ExecutionObserverStore()
        return _default_store


# Production lifecycle durability/recovery (#112)
from .lifecycle_ext import install as _install_lifecycle

_install_lifecycle(ExecutionObserverStore, redact_secrets=redact_secrets, InvalidTransitionError=InvalidTransitionError)
