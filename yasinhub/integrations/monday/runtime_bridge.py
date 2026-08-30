"""Bridge normalized monday events to YasinHub Execution Runtime / Agent.

Path: monday -> YasinHub -> Execution Runtime -> Yasin-Agent
Agent remains unaware of monday.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Dict, Optional, Set

from ...adapters.agent_runtime import IntegrationContext, get_runtime_adapter
from ...execution.correlation import get_correlation_store
from ...observer.execution_store import get_default_store
from ...observer.models import ExecutionSnapshot
from .adapter import get_monday_adapter
from .models import MondayNormalizedEvent

logger = logging.getLogger(__name__)


class MondayRuntimeBridge:
    """Consumes task.ready events and creates governed executions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._processed_corr: Set[str] = set()
        self._item_to_execution: Dict[str, str] = {}

    def process_event(self, event: MondayNormalizedEvent) -> Optional[ExecutionSnapshot]:
        if event.event_type != "task.ready":
            return None

        corr = event.correlation_id or f"mon-{event.board_id}-{event.item_id}"
        with self._lock:
            if corr in self._processed_corr:
                logger.info("duplicate task.ready ignored corr=%s", corr)
                return self._lookup_existing(event.item_id)
            self._processed_corr.add(corr)

        meta = dict(event.column_values or {})
        project = str(meta.get("project") or meta.get("project_id") or "default")
        repository = str(meta.get("repository") or meta.get("repo") or "")
        task_name = event.name or f"monday-item-{event.item_id}"
        agent_id = meta.get("agent") or meta.get("agent_id")
        priority = meta.get("priority") or "normal"

        if not event.item_id:
            logger.warning("task.ready missing item_id")
            return None

        store = get_default_store()
        execution_id = f"exec-mon-{uuid.uuid4().hex[:12]}"
        metadata = {
            "source": "monday",
            "board_id": event.board_id,
            "item_id": event.item_id,
            "correlation_id": corr,
            "project": project,
            "repository": repository,
            "priority": priority,
            "monday_event_id": event.event_id,
        }

        snap = store.create_execution(
            task_id=task_name,
            session_id=f"sess-mon-{event.item_id}",
            agent_id=str(agent_id) if agent_id else None,
            metadata=metadata,
            execution_id=execution_id,
        )

        with self._lock:
            self._item_to_execution[event.item_id] = execution_id

        try:
            get_correlation_store().register(
                execution_id=execution_id,
                correlation_id=corr,
                monday_board_id=event.board_id,
                monday_item_id=event.item_id,
                agent_run_id=snap.session_id,
                github_repo=repository or None,
            )
        except Exception:
            logger.exception("correlation register failed for %s", execution_id)

        store.emit_event(
            event_type="integration.monday.task_ready",
            execution_id=execution_id,
            task_id=task_name,
            session_id=snap.session_id,
            status="queued",
            metadata=metadata,
            agent_id=snap.agent_id,
        )

        logger.info(
            "created execution %s for monday item %s corr=%s",
            execution_id,
            event.item_id,
            corr,
        )
        return snap

    def _lookup_existing(self, item_id: str) -> Optional[ExecutionSnapshot]:
        eid = self._item_to_execution.get(item_id)
        if not eid:
            rec = get_correlation_store().get_by_monday_item(item_id)
            if rec:
                eid = rec.execution_id
        if not eid:
            return None
        return get_default_store().get_execution(eid)

    def cancel_for_item(self, item_id: str, *, actor: str = "monday") -> Optional[ExecutionSnapshot]:
        eid = self._item_to_execution.get(item_id)
        if not eid:
            rec = get_correlation_store().get_by_monday_item(item_id)
            eid = rec.execution_id if rec else None
        if not eid:
            return None
        ctx = IntegrationContext(
            request_id=f"req-{uuid.uuid4().hex[:12]}", actor=actor, source="monday"
        )
        try:
            get_runtime_adapter().cancel(eid, context=ctx)
            return get_default_store().get_execution(eid)
        except Exception:
            logger.exception("cancel failed for %s", eid)
            return None

    def retry_for_item(self, item_id: str, *, actor: str = "monday") -> Optional[ExecutionSnapshot]:
        existing = self._lookup_existing(item_id)
        if existing and not existing.is_terminal():
            return existing
        adapter = get_monday_adapter()
        events = adapter.list_events(item_id=item_id, event_type="task.ready", limit=1)
        if not events:
            return None
        corr = events[0].correlation_id
        with self._lock:
            if corr:
                self._processed_corr.discard(corr)
        return self.process_event(events[0])

    def drain_pending(self) -> int:
        adapter = get_monday_adapter()
        count = 0
        for evt in adapter.list_events(event_type="task.ready", limit=100):
            if self.process_event(evt):
                count += 1
        return count


_bridge: Optional[MondayRuntimeBridge] = None
_bridge_lock = threading.Lock()


def get_runtime_bridge() -> MondayRuntimeBridge:
    global _bridge
    with _bridge_lock:
        if _bridge is None:
            _bridge = MondayRuntimeBridge()
        return _bridge
