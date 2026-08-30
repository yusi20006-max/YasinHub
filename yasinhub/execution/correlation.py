"""Canonical correlation: monday → execution → Agent → GitHub Issue/PR/CI.

Deterministic identifiers only. Ambiguous matches never mutate the wrong execution.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ..observer.execution_store import get_default_store, redact_secrets
from ..observer.models import ExecutionSnapshot

logger = logging.getLogger(__name__)


@dataclass
class CorrelationRecord:
    correlation_id: str
    execution_id: str
    monday_board_id: Optional[str] = None
    monday_item_id: Optional[str] = None
    agent_run_id: Optional[str] = None
    github_repo: Optional[str] = None
    github_issue: Optional[int] = None
    github_pr: Optional[int] = None
    github_sha: Optional[str] = None
    ci_status: Optional[str] = None
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return redact_secrets(
            {
                "correlation_id": self.correlation_id,
                "execution_id": self.execution_id,
                "monday_board_id": self.monday_board_id,
                "monday_item_id": self.monday_item_id,
                "agent_run_id": self.agent_run_id,
                "github_repo": self.github_repo,
                "github_issue": self.github_issue,
                "github_pr": self.github_pr,
                "github_sha": self.github_sha,
                "ci_status": self.ci_status,
                "updated_at": self.updated_at,
                "metadata": dict(self.metadata),
            }
        )


class CorrelationConflict(Exception):
    """Raised when two distinct executions claim the same external identity."""


class CorrelationStore:
    """In-process correlation index with conflict detection."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_corr: Dict[str, CorrelationRecord] = {}
        self._by_execution: Dict[str, str] = {}
        self._by_monday_item: Dict[str, str] = {}
        self._by_pr: Dict[str, str] = {}  # repo#pr -> correlation_id
        self._by_sha: Dict[str, str] = {}

    def register(
        self,
        *,
        execution_id: str,
        correlation_id: Optional[str] = None,
        monday_board_id: Optional[str] = None,
        monday_item_id: Optional[str] = None,
        agent_run_id: Optional[str] = None,
        github_repo: Optional[str] = None,
        github_issue: Optional[int] = None,
        github_pr: Optional[int] = None,
        github_sha: Optional[str] = None,
        ci_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CorrelationRecord:
        cid = correlation_id or f"corr-{uuid.uuid4().hex[:16]}"
        with self._lock:
            # Conflict: monday item already bound to different execution
            if monday_item_id:
                existing_cid = self._by_monday_item.get(str(monday_item_id))
                if existing_cid and existing_cid != cid:
                    existing = self._by_corr.get(existing_cid)
                    if existing and existing.execution_id != execution_id:
                        raise CorrelationConflict(
                            f"monday item {monday_item_id} already bound to {existing.execution_id}"
                        )
            if github_pr is not None and github_repo:
                pr_key = f"{github_repo}#{github_pr}"
                existing_cid = self._by_pr.get(pr_key)
                if existing_cid and existing_cid != cid:
                    existing = self._by_corr.get(existing_cid)
                    if existing and existing.execution_id != execution_id:
                        raise CorrelationConflict(
                            f"PR {pr_key} already bound to {existing.execution_id}"
                        )

            rec = self._by_corr.get(cid)
            if rec is None:
                rec = CorrelationRecord(
                    correlation_id=cid,
                    execution_id=execution_id,
                )
            else:
                if rec.execution_id != execution_id:
                    raise CorrelationConflict(
                        f"correlation {cid} bound to {rec.execution_id}, not {execution_id}"
                    )

            if monday_board_id:
                rec.monday_board_id = str(monday_board_id)
            if monday_item_id:
                rec.monday_item_id = str(monday_item_id)
            if agent_run_id:
                rec.agent_run_id = str(agent_run_id)
            if github_repo:
                rec.github_repo = str(github_repo)
            if github_issue is not None:
                rec.github_issue = int(github_issue)
            if github_pr is not None:
                rec.github_pr = int(github_pr)
            if github_sha:
                rec.github_sha = str(github_sha)
            if ci_status is not None:
                rec.ci_status = str(ci_status)
            if metadata:
                rec.metadata.update(redact_secrets(dict(metadata)))
            rec.updated_at = time.time()

            self._by_corr[cid] = rec
            self._by_execution[execution_id] = cid
            if rec.monday_item_id:
                self._by_monday_item[rec.monday_item_id] = cid
            if rec.github_pr is not None and rec.github_repo:
                self._by_pr[f"{rec.github_repo}#{rec.github_pr}"] = cid
            if rec.github_sha:
                self._by_sha[rec.github_sha] = cid
            return rec

    def get_by_correlation(self, correlation_id: str) -> Optional[CorrelationRecord]:
        with self._lock:
            return self._by_corr.get(correlation_id)

    def get_by_execution(self, execution_id: str) -> Optional[CorrelationRecord]:
        with self._lock:
            cid = self._by_execution.get(execution_id)
            return self._by_corr.get(cid) if cid else None

    def get_by_monday_item(self, item_id: str) -> Optional[CorrelationRecord]:
        with self._lock:
            cid = self._by_monday_item.get(str(item_id))
            return self._by_corr.get(cid) if cid else None

    def get_by_pr(self, repo: str, pr_number: int) -> Optional[CorrelationRecord]:
        with self._lock:
            cid = self._by_pr.get(f"{repo}#{pr_number}")
            return self._by_corr.get(cid) if cid else None

    def get_by_sha(self, sha: str) -> Optional[CorrelationRecord]:
        with self._lock:
            cid = self._by_sha.get(sha)
            return self._by_corr.get(cid) if cid else None

    def resolve_github_event(
        self,
        *,
        repository: Optional[str] = None,
        pr_number: Optional[int] = None,
        sha: Optional[str] = None,
        correlation_hint: Optional[str] = None,
    ) -> Tuple[Optional[CorrelationRecord], str]:
        """Resolve a GitHub event to at most one correlation record.

        Returns (record, reason). Ambiguous → (None, "ambiguous").
        """
        candidates: List[CorrelationRecord] = []
        seen: Set[str] = set()

        def add(rec: Optional[CorrelationRecord]) -> None:
            if rec and rec.correlation_id not in seen:
                seen.add(rec.correlation_id)
                candidates.append(rec)

        if correlation_hint:
            add(self.get_by_correlation(str(correlation_hint)))
        if pr_number is not None and repository:
            add(self.get_by_pr(repository, int(pr_number)))
        if sha:
            add(self.get_by_sha(sha))

        if len(candidates) == 0:
            return None, "not_found"
        if len(candidates) > 1:
            # only accept if they all point to same execution
            execs = {c.execution_id for c in candidates}
            if len(execs) > 1:
                return None, "ambiguous"
        return candidates[0], "matched"

    def list_orphans(self) -> List[Dict[str, Any]]:
        """Executions with source=monday but no correlation record."""
        store = get_default_store()
        orphans = []
        with self._lock:
            known = set(self._by_execution.keys())
        for snap in store.list_executions():
            meta = snap.metadata or {}
            if meta.get("source") == "monday" and snap.execution_id not in known:
                orphans.append(
                    {
                        "execution_id": snap.execution_id,
                        "item_id": meta.get("item_id"),
                        "status": snap.status,
                    }
                )
        return orphans

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.as_dict() for r in self._by_corr.values()]

    def clear(self) -> None:
        with self._lock:
            self._by_corr.clear()
            self._by_execution.clear()
            self._by_monday_item.clear()
            self._by_pr.clear()
            self._by_sha.clear()


_store: Optional[CorrelationStore] = None
_store_lock = threading.Lock()


def get_correlation_store() -> CorrelationStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = CorrelationStore()
        return _store


def bind_execution_from_snapshot(snap: ExecutionSnapshot) -> Optional[CorrelationRecord]:
    """Register correlation from an execution snapshot metadata."""
    meta = snap.metadata or {}
    try:
        return get_correlation_store().register(
            execution_id=snap.execution_id,
            correlation_id=meta.get("correlation_id"),
            monday_board_id=meta.get("board_id"),
            monday_item_id=meta.get("item_id"),
            agent_run_id=snap.session_id,
            github_repo=meta.get("repository"),
            github_issue=meta.get("github_issue"),
            github_pr=meta.get("github_pr"),
            github_sha=meta.get("github_sha"),
            ci_status=meta.get("ci_status"),
        )
    except CorrelationConflict:
        logger.warning("correlation conflict for execution %s", snap.execution_id)
        return None
