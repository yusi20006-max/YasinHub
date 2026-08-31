"""Lifecycle durability, recovery, and audit hooks (#112)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import ExecutionSnapshot, WorkspaceSnapshot


def load_durable(store) -> None:
    if not store._durable_dir or not store._durable_dir.exists():
        return
    for path in store._durable_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not data.get("execution_id"):
            continue
        eid = str(data["execution_id"])
        ws = None
        if data.get("workspace"):
            w = data["workspace"]
            ws = WorkspaceSnapshot(
                workspace_id=str(w.get("workspace_id") or f"ws-{eid[:8]}"),
                path=w.get("path"),
                scope=str(w.get("scope") or "default"),
                metadata=dict(w.get("metadata") or {}),
            )
        snap = ExecutionSnapshot(
            execution_id=eid,
            task_id=str(data.get("task_id") or "unknown"),
            session_id=str(data.get("session_id") or "unknown"),
            status=str(data.get("status") or "queued"),
            agent_id=data.get("agent_id"),
            workspace=ws,
            capabilities=list(data.get("capabilities") or []),
            created_at=data.get("created_at"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            error=data.get("error"),
            result=data.get("result"),
            metadata=dict(data.get("metadata") or {}),
            history=list(data.get("history") or []),
            cancel_requested=bool(data.get("cancel_requested")),
        )
        store._executions[eid] = snap


def install(store_cls, *, redact_secrets, InvalidTransitionError) -> None:
    if getattr(store_cls, "_lifecycle_installed", False):
        return

    _orig_init = store_cls.__init__
    _orig_transition = store_cls._transition
    _orig_upsert = store_cls.upsert_execution

    def __init__(self, *args, durable_dir: Optional[str] = None, **kwargs):
        _orig_init(self, *args, **kwargs)
        raw = durable_dir or (os.environ.get("YASIN_EXECUTION_STORE_DIR") or "").strip() or None
        self._durable_dir = Path(raw) if raw else None
        if self._durable_dir is not None:
            self._durable_dir.mkdir(parents=True, exist_ok=True)
            load_durable(self)

    def _execution_path(self, execution_id: str) -> Optional[Path]:
        if not self._durable_dir:
            return None
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in execution_id)[:128]
        return self._durable_dir / f"{safe}.json"

    def _persist_execution(self, snap: ExecutionSnapshot) -> None:
        path = self._execution_path(snap.execution_id)
        if path is None:
            return
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(redact_secrets(snap.as_dict()), default=str), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass

    def upsert_execution(self, snapshot: ExecutionSnapshot) -> ExecutionSnapshot:
        safe = _orig_upsert(self, snapshot)
        self._persist_execution(safe)
        return safe

    def _transition(self, execution_id, target, *, actor=None, request_id=None, extra_meta=None):
        with self._lock:
            rec = self._executions.get(execution_id)
            current = rec.status if rec else None
        updated = _orig_transition(
            self, execution_id, target, actor=actor, request_id=request_id, extra_meta=extra_meta
        )
        self._persist_execution(updated)
        try:
            from ..execution.policies import get_policy_engine

            get_policy_engine()._audit_record(
                actor=actor or "system",
                source="execution-store",
                action=f"lifecycle:{target}",
                policy_decision="allow",
                outcome="ok",
                execution_id=execution_id,
                metadata={"from": current, "to": target, "request_id": request_id},
            )
        except Exception:
            pass
        return updated

    def recover_stale(
        self,
        *,
        max_age_seconds: float = 3600.0,
        actor: str = "system-recovery",
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        now = time.time()
        findings: List[Dict[str, Any]] = []
        with self._lock:
            items = list(self._executions.values())
        for snap in items:
            if snap.is_terminal():
                continue
            started = snap.started_at or snap.created_at or now
            age = now - float(started)
            if age < max_age_seconds:
                continue
            findings.append(
                {
                    "execution_id": snap.execution_id,
                    "status": snap.status,
                    "age_seconds": age,
                    "action": "mark_failed" if not dry_run else "would_mark_failed",
                }
            )
            if dry_run:
                continue
            try:
                self.fail(
                    snap.execution_id,
                    f"recovered as stale after {int(age)}s without terminal state",
                    actor=actor,
                )
            except Exception:
                continue
        return findings

    store_cls.__init__ = __init__  # type: ignore
    store_cls.upsert_execution = upsert_execution  # type: ignore
    store_cls._transition = _transition  # type: ignore
    store_cls.recover_stale = recover_stale  # type: ignore
    store_cls._persist_execution = _persist_execution  # type: ignore
    store_cls._execution_path = _execution_path  # type: ignore
    store_cls._lifecycle_installed = True
