"""
Agent Runtime Adapter — transport-agnostic boundary between YasinHub and Yasin-Agent.

Yasin-Agent remains authoritative for execution lifecycle.
YasinHub observes/projects state and forwards control commands.
Transport may later become HTTP, WebSocket, event bus, or MCP bridge without
rewriting Observer APIs.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..observer.execution_store import (
    ExecutionObserverStore,
    InvalidTransitionError,
    get_default_store,
    redact_secrets,
)
from ..observer.models import (
    ExecutionSnapshot,
    FleetSnapshot,
    StructuredEvent,
    WorkerSnapshot,
    WorkspaceSnapshot,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntegrationContext:
    """Authenticated integration context. Never trust client-supplied actor alone."""

    request_id: str
    actor: str
    source: str = "hub-control"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_audit(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "actor": self.actor,
            "source": self.source,
            "timestamp": time.time(),
        }


def resolve_integration_context(
    body: Optional[Dict[str, Any]] = None,
    *,
    headers: Optional[Any] = None,
    default_actor: str = "hub-system",
) -> IntegrationContext:
    body = body or {}
    request_id = (
        body.get("request_id")
        or (headers.get("X-Request-Id") if headers and hasattr(headers, "get") else None)
        or f"req-{uuid.uuid4().hex[:16]}"
    )
    hinted = body.get("actor")
    actor = default_actor
    meta: Dict[str, Any] = {}
    if hinted and isinstance(hinted, str) and hinted.strip():
        meta["actor_hint"] = str(hinted)
    return IntegrationContext(
        request_id=str(request_id),
        actor=actor,
        source="hub-control",
        metadata=meta,
    )


class AgentRuntimeAdapter(ABC):
    @abstractmethod
    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def list_executions(
        self,
        *,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def list_events(
        self,
        *,
        execution_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def pause(self, execution_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        ...

    @abstractmethod
    def resume(self, execution_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        ...

    @abstractmethod
    def cancel(self, execution_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        ...

    @abstractmethod
    def cancel_fleet(self, task_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        ...

    @abstractmethod
    def get_fleet(self, task_id: str) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def list_fleets(self) -> List[Dict[str, Any]]:
        ...


def _dict_to_workspace(data: Optional[Dict[str, Any]]) -> Optional[WorkspaceSnapshot]:
    if not data:
        return None
    return WorkspaceSnapshot(
        workspace_id=str(data.get("workspace_id") or f"ws-{uuid.uuid4().hex[:12]}"),
        path=data.get("path"),
        scope=str(data.get("scope") or "default"),
        metadata=redact_secrets(dict(data.get("metadata") or {})),
    )


def project_execution_dict(data: Dict[str, Any]) -> ExecutionSnapshot:
    status = str(data.get("status") or "queued")
    history = list(data.get("history") or [status])
    return ExecutionSnapshot(
        execution_id=str(data["execution_id"]),
        task_id=str(data.get("task_id") or ""),
        session_id=str(data.get("session_id") or ""),
        status=status,
        agent_id=data.get("agent_id"),
        workspace=_dict_to_workspace(data.get("workspace") if isinstance(data.get("workspace"), dict) else None),
        capabilities=list(data.get("capabilities") or []),
        created_at=data.get("created_at"),
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
        error=str(redact_secrets(data["error"])) if data.get("error") else None,
        result=redact_secrets(data.get("result")),
        metadata=redact_secrets(dict(data.get("metadata") or {})),
        history=[str(h) for h in history],
        cancel_requested=bool(data.get("cancel_requested", False)),
    )


def project_event_dict(data: Dict[str, Any], sequence: int = 0) -> StructuredEvent:
    return StructuredEvent(
        event_id=str(data.get("event_id") or f"evt-{uuid.uuid4().hex[:16]}"),
        event_type=str(data.get("event_type") or "unknown"),
        timestamp=float(data.get("timestamp") or time.time()),
        execution_id=str(data.get("execution_id") or ""),
        task_id=str(data.get("task_id") or ""),
        session_id=str(data.get("session_id") or ""),
        status=str(data.get("status") or ""),
        metadata=redact_secrets(dict(data.get("metadata") or {})),
        agent_id=data.get("agent_id"),
        workspace_id=data.get("workspace_id"),
        sequence=int(data.get("sequence") or sequence),
        worker_id=data.get("worker_id") or (data.get("metadata") or {}).get("worker_id"),
        parent_task_id=data.get("parent_task_id") or data.get("task_id"),
    )


def project_fleet_dict(data: Dict[str, Any]) -> FleetSnapshot:
    workers_raw = data.get("workers") or []
    workers: List[WorkerSnapshot] = []
    for w in workers_raw:
        if not isinstance(w, dict):
            continue
        workers.append(
            WorkerSnapshot(
                worker_id=str(w.get("worker_id") or ""),
                role=str(w.get("role") or ""),
                objective=str(w.get("objective") or ""),
                status=str(w.get("status") or "unknown"),
                execution_id=str(w.get("execution_id") or ""),
                session_id=str(w.get("session_id") or ""),
                progress=redact_secrets(w.get("progress")),
                result=redact_secrets(w.get("result")),
                error=str(redact_secrets(w["error"])) if w.get("error") else None,
                cancellation_state=w.get("cancellation_state"),
                agent_id=w.get("agent_id"),
            )
        )
    return FleetSnapshot(
        task_id=str(data.get("task_id") or ""),
        status=str(data.get("status") or "unknown"),
        workers=workers,
    )


class InProcessAgentRuntimeAdapter(AgentRuntimeAdapter):
    def __init__(
        self,
        *,
        runtime: Any = None,
        fleet: Any = None,
        store: Optional[ExecutionObserverStore] = None,
        audit_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self._runtime = runtime
        self._fleet = fleet
        self._store = store or get_default_store()
        self._audit_sink = audit_sink
        self._seen_event_ids: set = set()
        self._lock = threading.RLock()
        self._bound = runtime is not None
        if runtime is not None and hasattr(runtime, "events") and hasattr(runtime.events, "subscribe"):
            try:
                runtime.events.subscribe(self._on_agent_event)
            except Exception:
                logger.exception("failed to subscribe to agent event emitter")

    @property
    def store(self) -> ExecutionObserverStore:
        return self._store

    @property
    def is_bound(self) -> bool:
        return self._bound

    def _on_agent_event(self, event: Any) -> None:
        try:
            data = event.as_dict() if hasattr(event, "as_dict") else dict(event)
        except Exception:
            return
        self.ingest_event(data)

    def ingest_event(self, data: Dict[str, Any]) -> Optional[StructuredEvent]:
        if not isinstance(data, dict):
            return None
        event_id = str(data.get("event_id") or "")
        with self._lock:
            if event_id and event_id in self._seen_event_ids:
                return None
            if event_id:
                self._seen_event_ids.add(event_id)
        eid = data.get("execution_id")
        if eid and data.get("status"):
            existing = self._store.get_execution(str(eid))
            if existing is not None:
                updated = ExecutionSnapshot(
                    execution_id=existing.execution_id,
                    task_id=existing.task_id,
                    session_id=existing.session_id,
                    status=str(data["status"]),
                    agent_id=existing.agent_id or data.get("agent_id"),
                    workspace=existing.workspace,
                    capabilities=list(existing.capabilities),
                    created_at=existing.created_at,
                    started_at=existing.started_at,
                    finished_at=existing.finished_at,
                    error=existing.error,
                    result=existing.result,
                    metadata=dict(existing.metadata),
                    history=list(existing.history)
                    + ([str(data["status"])] if str(data["status"]) not in existing.history else []),
                    cancel_requested=existing.cancel_requested or str(data.get("status")) == "cancelled",
                )
                self._store.upsert_execution(updated)
            elif self._runtime is not None:
                rec = self._runtime.get(str(eid)) if hasattr(self._runtime, "get") else None
                if rec is not None:
                    d = rec.as_dict() if hasattr(rec, "as_dict") else dict(rec)
                    self._store.upsert_execution(project_execution_dict(d))
        worker_id = data.get("worker_id") or (data.get("metadata") or {}).get("worker_id")
        parent_task_id = data.get("parent_task_id") or data.get("task_id")
        return self._store.emit_event(
            event_type=str(data.get("event_type") or "unknown"),
            execution_id=str(data.get("execution_id") or ""),
            task_id=str(data.get("task_id") or ""),
            session_id=str(data.get("session_id") or ""),
            status=str(data.get("status") or ""),
            metadata=redact_secrets(dict(data.get("metadata") or {})),
            agent_id=data.get("agent_id"),
            workspace_id=data.get("workspace_id"),
            worker_id=worker_id,
            parent_task_id=parent_task_id,
        )

    def sync_execution(self, execution_id: str) -> Optional[ExecutionSnapshot]:
        if self._runtime is None:
            return self._store.get_execution(execution_id)
        rec = self._runtime.get(execution_id) if hasattr(self._runtime, "get") else None
        if rec is None:
            return self._store.get_execution(execution_id)
        d = rec.as_dict() if hasattr(rec, "as_dict") else dict(rec)
        return self._store.upsert_execution(project_execution_dict(d))

    def register_execution(self, data: Dict[str, Any]) -> ExecutionSnapshot:
        snap = project_execution_dict(data)
        self._store.upsert_execution(snap)
        self._store.emit_event(
            event_type="execution.created",
            execution_id=snap.execution_id,
            task_id=snap.task_id,
            session_id=snap.session_id,
            status=snap.status,
            agent_id=snap.agent_id,
            workspace_id=snap.workspace.workspace_id if snap.workspace else None,
            metadata={"source": "agent-runtime"},
        )
        return snap

    def register_fleet(self, data: Dict[str, Any]) -> FleetSnapshot:
        return self._store.upsert_fleet(project_fleet_dict(data))

    def _audit(self, action: str, context: IntegrationContext, **extra: Any) -> None:
        record = {
            **context.as_audit(),
            "action": action,
            **{k: v for k, v in extra.items() if k not in ("token", "password", "api_key", "secret")},
        }
        record = redact_secrets(record)
        if self._audit_sink:
            try:
                self._audit_sink(record)
            except Exception:
                logger.exception("audit sink failed")
        logger.info("audit %s", record)

    def _raise_from_runtime(self, exc: Exception) -> None:
        name = type(exc).__name__
        msg = str(exc).lower()
        if isinstance(exc, KeyError) or "unknown" in msg:
            raise KeyError(str(exc)) from exc
        if "invalid" in msg and "transition" in msg:
            current, target = "unknown", "unknown"
            if "->" in str(exc):
                parts = str(exc).split("->")
                current = parts[0].split()[-1].strip()
                target = parts[-1].strip()
            raise InvalidTransitionError(current, target) from exc
        if name == "InvalidTransitionError" or hasattr(exc, "current"):
            current = getattr(exc, "current", "unknown")
            target = getattr(exc, "target", "unknown")
            if hasattr(current, "value"):
                current = current.value
            if hasattr(target, "value"):
                target = target.value
            raise InvalidTransitionError(str(current), str(target)) from exc
        raise

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        if self._runtime is not None and hasattr(self._runtime, "get"):
            rec = self._runtime.get(execution_id)
            if rec is not None:
                d = rec.as_dict() if hasattr(rec, "as_dict") else dict(rec)
                self._store.upsert_execution(project_execution_dict(d))
                return d
        snap = self._store.get_execution(execution_id)
        return snap.as_dict() if snap else None

    def list_executions(
        self,
        *,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if self._runtime is not None and hasattr(self._runtime, "list_executions"):
            try:
                items = self._runtime.list_executions(task_id=task_id, session_id=session_id)
                out = []
                for rec in items:
                    d = rec.as_dict() if hasattr(rec, "as_dict") else dict(rec)
                    if status is not None and str(d.get("status")) != status:
                        continue
                    self._store.upsert_execution(project_execution_dict(d))
                    out.append(d)
                return out
            except Exception:
                logger.exception("list_executions from runtime failed; using projection")
        return [
            e.as_dict()
            for e in self._store.list_executions(task_id=task_id, session_id=session_id, status=status)
        ]

    def list_events(
        self,
        *,
        execution_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        events = self._store.list_events(
            execution_id=execution_id,
            task_id=task_id,
            session_id=session_id,
            worker_id=worker_id,
            event_type=event_type,
            limit=limit,
        )
        return [e.as_dict() for e in events]

    def pause(self, execution_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        self._audit("pause", context, execution_id=execution_id)
        if self._runtime is not None and hasattr(self._runtime, "pause"):
            try:
                rec = self._runtime.pause(execution_id)
            except Exception as exc:
                self._raise_from_runtime(exc)
                raise
            d = rec.as_dict() if hasattr(rec, "as_dict") else dict(rec)
            self._store.upsert_execution(project_execution_dict(d))
            self._store.emit_event(
                event_type="execution.paused",
                execution_id=execution_id,
                task_id=d.get("task_id", ""),
                session_id=d.get("session_id", ""),
                status="paused",
                metadata={
                    "actor": context.actor,
                    "request_id": context.request_id,
                    "cooperative": True,
                    **context.metadata,
                },
                agent_id=d.get("agent_id"),
            )
            self._audit("pause", context, execution_id=execution_id, result="ok")
            return d
        snap = self._store.pause(execution_id, actor=context.actor, request_id=context.request_id)
        self._audit("pause", context, execution_id=execution_id, result="ok")
        return snap.as_dict()

    def resume(self, execution_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        self._audit("resume", context, execution_id=execution_id)
        if self._runtime is not None and hasattr(self._runtime, "resume"):
            try:
                rec = self._runtime.resume(execution_id)
            except Exception as exc:
                self._raise_from_runtime(exc)
                raise
            d = rec.as_dict() if hasattr(rec, "as_dict") else dict(rec)
            self._store.upsert_execution(project_execution_dict(d))
            self._store.emit_event(
                event_type="execution.resumed",
                execution_id=execution_id,
                task_id=d.get("task_id", ""),
                session_id=d.get("session_id", ""),
                status="running",
                metadata={
                    "actor": context.actor,
                    "request_id": context.request_id,
                    **context.metadata,
                },
                agent_id=d.get("agent_id"),
            )
            self._audit("resume", context, execution_id=execution_id, result="ok")
            return d
        snap = self._store.resume(execution_id, actor=context.actor, request_id=context.request_id)
        self._audit("resume", context, execution_id=execution_id, result="ok")
        return snap.as_dict()

    def cancel(self, execution_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        self._audit("cancel", context, execution_id=execution_id)
        if self._runtime is not None and hasattr(self._runtime, "cancel"):
            try:
                rec = self._runtime.cancel(execution_id)
            except Exception as exc:
                self._raise_from_runtime(exc)
                raise
            d = rec.as_dict() if hasattr(rec, "as_dict") else dict(rec)
            self._store.upsert_execution(project_execution_dict(d))
            self._store.emit_event(
                event_type="execution.cancelled",
                execution_id=execution_id,
                task_id=d.get("task_id", ""),
                session_id=d.get("session_id", ""),
                status=str(d.get("status") or "cancelled"),
                metadata={
                    "actor": context.actor,
                    "request_id": context.request_id,
                    **context.metadata,
                },
                agent_id=d.get("agent_id"),
            )
            self._audit("cancel", context, execution_id=execution_id, result="ok")
            return d
        snap = self._store.cancel(execution_id, actor=context.actor, request_id=context.request_id)
        self._audit("cancel", context, execution_id=execution_id, result="ok")
        return snap.as_dict()

    def cancel_fleet(self, task_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        self._audit("fleet_cancel", context, task_id=task_id)
        if self._fleet is not None and hasattr(self._fleet, "cancel"):
            try:
                self._fleet.cancel(task_id)
            except Exception as exc:
                self._raise_from_runtime(exc)
                raise
            status = None
            if hasattr(self._fleet, "status"):
                try:
                    st = self._fleet.status(task_id)
                    status = st.as_dict() if hasattr(st, "as_dict") else dict(st)
                except Exception:
                    status = None
            if status:
                fleet = self.register_fleet(status)
            else:
                fleet = self._store.cancel_fleet(
                    task_id, actor=context.actor, request_id=context.request_id
                )
            self._audit("fleet_cancel", context, task_id=task_id, result="ok")
            return fleet.as_dict() if hasattr(fleet, "as_dict") else fleet
        fleet = self._store.cancel_fleet(
            task_id, actor=context.actor, request_id=context.request_id
        )
        self._audit("fleet_cancel", context, task_id=task_id, result="ok")
        return fleet.as_dict()

    def get_fleet(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self._fleet is not None and hasattr(self._fleet, "status"):
            try:
                st = self._fleet.status(task_id)
                d = st.as_dict() if hasattr(st, "as_dict") else dict(st)
                self._store.upsert_fleet(project_fleet_dict(d))
                return d
            except Exception:
                pass
        snap = self._store.get_fleet(task_id)
        return snap.as_dict() if snap else None

    def list_fleets(self) -> List[Dict[str, Any]]:
        return [f.as_dict() for f in self._store.list_fleets()]


_adapter: Optional[AgentRuntimeAdapter] = None
_adapter_lock = threading.Lock()


def get_runtime_adapter() -> AgentRuntimeAdapter:
    global _adapter
    with _adapter_lock:
        if _adapter is None:
            _adapter = InProcessAgentRuntimeAdapter()
        return _adapter


def set_runtime_adapter(adapter: Optional[AgentRuntimeAdapter]) -> None:
    global _adapter
    with _adapter_lock:
        _adapter = adapter


def bind_agent_runtime(runtime: Any, fleet: Any = None) -> InProcessAgentRuntimeAdapter:
    adapter = InProcessAgentRuntimeAdapter(runtime=runtime, fleet=fleet)
    set_runtime_adapter(adapter)
    return adapter


__all__ = [
    "AgentRuntimeAdapter",
    "InProcessAgentRuntimeAdapter",
    "IntegrationContext",
    "resolve_integration_context",
    "get_runtime_adapter",
    "set_runtime_adapter",
    "bind_agent_runtime",
    "project_execution_dict",
    "project_event_dict",
    "project_fleet_dict",
]
