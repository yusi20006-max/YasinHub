"""GitHub adapter — normalize, correlate, update execution state."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Set

from ...execution.correlation import get_correlation_store
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
        """Update matching executions using deterministic correlation only."""
        store = get_default_store()
        corr_store = get_correlation_store()

        rec, reason = corr_store.resolve_github_event(
            repository=event.get("repository"),
            pr_number=event.get("pr_number"),
            sha=event.get("sha"),
            correlation_hint=event.get("correlation_hint"),
        )
        if reason == "ambiguous":
            logger.warning("ambiguous github correlation; skipping mutation")
            return
        if reason == "not_found" or rec is None:
            # no deterministic match — do not heuristic-scan all executions
            return

        snap = store.get_execution(rec.execution_id)
        if snap is None:
            return

        pr_number = event.get("pr_number")
        check_conclusion = event.get("check_conclusion")
        check_status = event.get("check_status")
        pr_state = event.get("pr_state")
        pr_merged = event.get("pr_merged")

        # persist correlation enrichment
        try:
            corr_store.register(
                execution_id=rec.execution_id,
                correlation_id=rec.correlation_id,
                github_repo=event.get("repository") or rec.github_repo,
                github_pr=pr_number if pr_number is not None else rec.github_pr,
                github_sha=event.get("sha") or rec.github_sha,
                ci_status=check_conclusion or check_status or rec.ci_status,
            )
        except Exception:
            logger.exception("correlation enrich failed")

        try:
            if pr_merged:
                if snap.status not in ("succeeded", "failed", "cancelled"):
                    store.complete(
                        snap.execution_id, result={"merged": True, "pr": pr_number}
                    )
            elif check_conclusion == "failure" and snap.status == "running":
                store.fail(
                    snap.execution_id, error=f"CI failed: {event.get('check_name')}"
                )
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
