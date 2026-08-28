"""
Serializable observation models aligned with Yasin-Agent execution contracts.

These shapes mirror the JSON-facing contracts from Yasin-Agent #26–#28
(ExecutionRecord.as_dict, FleetStatus.as_dict, WorkerResult, events)
so the PWA and control plane can consume them deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _sorted_caps(caps: Any) -> List[str]:
    if not caps:
        return []
    return sorted(str(c) for c in caps)


@dataclass
class WorkspaceSnapshot:
    workspace_id: str
    path: Optional[str] = None
    scope: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "path": self.path,
            "scope": self.scope,
            "metadata": dict(self.metadata),
        }


@dataclass
class ExecutionSnapshot:
    """One observable execution (aligned with ExecutionRecord.as_dict)."""

    execution_id: str
    task_id: str
    session_id: str
    status: str
    agent_id: Optional[str] = None
    workspace: Optional[WorkspaceSnapshot] = None
    capabilities: List[str] = field(default_factory=list)
    created_at: Optional[float] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    result: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    history: List[str] = field(default_factory=list)
    cancel_requested: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "workspace": self.workspace.as_dict() if self.workspace else None,
            "capabilities": _sorted_caps(self.capabilities),
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "result": self.result,
            "metadata": dict(self.metadata),
            "history": list(self.history),
            "cancel_requested": self.cancel_requested,
        }

    def is_terminal(self) -> bool:
        return self.status in ("succeeded", "failed", "cancelled")


@dataclass
class StructuredEvent:
    """Structured observability event (aligned with ExecutionEvent.as_dict)."""

    event_id: str
    event_type: str
    timestamp: float
    execution_id: str
    task_id: str
    session_id: str
    status: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    agent_id: Optional[str] = None
    workspace_id: Optional[str] = None
    sequence: int = 0
    worker_id: Optional[str] = None
    parent_task_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "status": self.status,
            "metadata": dict(self.metadata),
            "agent_id": self.agent_id,
            "workspace_id": self.workspace_id,
            "sequence": self.sequence,
        }
        if self.worker_id is not None:
            d["worker_id"] = self.worker_id
        if self.parent_task_id is not None:
            d["parent_task_id"] = self.parent_task_id
        return d


@dataclass
class WorkerSnapshot:
    """One worker under a parent task / fleet."""

    worker_id: str
    role: str = ""
    objective: str = ""
    status: str = "unknown"
    execution_id: str = ""
    session_id: str = ""
    progress: Optional[Any] = None
    result: Any = None
    error: Optional[str] = None
    cancellation_state: Optional[str] = None
    agent_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "role": self.role,
            "objective": self.objective,
            "status": self.status,
            "execution_id": self.execution_id,
            "session_id": self.session_id,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "failure": self.error,
            "cancellation_state": self.cancellation_state,
            "agent_id": self.agent_id,
        }


@dataclass
class FleetSnapshot:
    """Parent task / fleet aggregation."""

    task_id: str
    status: str
    workers: List[WorkerSnapshot] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        # Deterministic ordering by worker_id
        ordered = sorted(self.workers, key=lambda w: w.worker_id)
        return {
            "task_id": self.task_id,
            "status": self.status,
            "workers": [w.as_dict() for w in ordered],
        }
