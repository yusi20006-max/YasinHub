"""GitHub adapter — normalize, correlate, update execution state."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Set

from ...observer.execution_store import get_default_store

logger = logging.getLogger(__name__)


class GitHubAdapter:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: List[Dict[str, Any]] = []
        self._seen: Set[str] = set()

    def ingest(self, event: Dict[str, Any]) -> bool:
        eid = str(event.get("event_id") or "")
        with self._lock:
            if eid and eid in self._seen:
                return False
            if eid:
                self._seen.add(eid)
            self._events.append(event)
        return True

    def apply_to_executions(self, event: Dict[str, Any]) -> None:
        """Update matching executions based on PR/CI lifecycle."""
        store = get_default_store()
        pr_number = event.get("pr_number")
        check_conclusion = event.get("check_conclusion")
        check_status = event.get("check_status")
        pr_state = event.get("pr_state")
        pr_merged = event.get("pr_merged")

        for snap in store.list_executions():
            meta = snap.metadata or {}
            # match by repository or explicit pr in metadata
            if event.get("repository") and meta.get("repository") != event.get("repository"):
                if meta.get("pr_number") != pr_number:
                    continue

            try:
                if pr_merged:
                    if snap.status not in ("succeeded", "failed", "cancelled"):
                        # mark completed via success path when merged
                        store.complete(snap.execution_id, result={"merged": True, "pr": pr_number})
                elif check_conclusion == "failure" and snap.status == "running":
                    store.fail(snap.execution_id, error=f"CI failed: {event.get('check_name')}")
                elif check_status == "in_progress" and snap.status == "queued":
                    store.start(snap.execution_id)
                elif pr_state == "open" and snap.status == "queued":
                    store.start(snap.execution_id)
            except Exception:
                logger.exception("apply github event to %s failed", snap.execution_id)

    def list_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._events)[-limit:]


_adapter: Optional[GitHubAdapter] = None
_lock = threading.Lock()


def get_github_adapter() -> GitHubAdapter:
    global _adapter
    with _lock:
        if _adapter is None:
            _adapter = GitHubAdapter()
        return _adapter
