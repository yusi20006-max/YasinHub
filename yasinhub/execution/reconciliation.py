"""Production observability and reconciliation for the YasinHub Control Plane.

Detects inconsistencies between monday items, executions, GitHub PR/CI, and
correlation records. Default mode is report-only (non-destructive). Privileged
mutations must still go through the Control API + PolicyEngine.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..observer.execution_store import get_default_store, redact_secrets
from .correlation import get_correlation_store
from .policies import get_policy_engine

logger = logging.getLogger(__name__)

DEFAULT_STALE_SECONDS = 6 * 3600
TERMINAL_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "completed_with_failures"}
)


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class FindingKind(str, Enum):
    STALE_EXECUTION = "stale_execution"
    ORPHAN_EXECUTION = "orphan_execution"
    MISSING_CORRELATION = "missing_correlation"
    CONFLICT = "conflict"
    STALE_MONDAY = "stale_monday"
    MISSING_GITHUB = "missing_github"
    STATE_INCONSISTENT = "state_inconsistent"
    SYNC_INCOMPLETE = "sync_incomplete"
    EXTERNAL_UNAVAILABLE = "external_unavailable"


@dataclass
class Finding:
    kind: FindingKind
    severity: str
    message: str
    execution_id: Optional[str] = None
    correlation_id: Optional[str] = None
    monday_item_id: Optional[str] = None
    github_pr: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return redact_secrets(
            {
                "kind": self.kind.value,
                "severity": self.severity,
                "message": self.message,
                "execution_id": self.execution_id,
                "correlation_id": self.correlation_id,
                "monday_item_id": self.monday_item_id,
                "github_pr": self.github_pr,
                "metadata": dict(self.metadata),
            }
        )


@dataclass
class IntegrationHealth:
    name: str
    state: HealthState
    detail: str
    configured: bool = False
    live_ready: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "detail": self.detail,
            "configured": self.configured,
            "live_ready": self.live_ready,
        }


@dataclass
class ReconcileReport:
    report_id: str
    started_at: float
    finished_at: float
    findings: List[Finding]
    integrations: List[IntegrationHealth]
    summary: Dict[str, int]
    overall_state: HealthState
    mode: str

    def as_dict(self) -> Dict[str, Any]:
        return redact_secrets(
            {
                "report_id": self.report_id,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "duration_ms": int((self.finished_at - self.started_at) * 1000),
                "overall_state": self.overall_state.value,
                "mode": self.mode,
                "summary": dict(self.summary),
                "findings": [f.as_dict() for f in self.findings],
                "integrations": [i.as_dict() for i in self.integrations],
            }
        )


class ReconciliationEngine:
    """Idempotent, policy-aware reconciliation (report-first)."""

    def __init__(self, *, stale_seconds: float = DEFAULT_STALE_SECONDS) -> None:
        self._lock = threading.RLock()
        self._stale_seconds = stale_seconds
        self._last_report: Optional[ReconcileReport] = None
        self._run_count = 0

    def health_snapshot(self) -> Dict[str, Any]:
        integrations = self._probe_integrations()
        states = [i.state for i in integrations]
        if any(s == HealthState.UNAVAILABLE for s in states):
            overall = HealthState.DEGRADED
        elif all(s in (HealthState.HEALTHY, HealthState.NOT_CONFIGURED) for s in states):
            overall = HealthState.HEALTHY
        else:
            overall = HealthState.DEGRADED
        return redact_secrets(
            {
                "overall_state": overall.value,
                "integrations": [i.as_dict() for i in integrations],
                "last_report_id": self._last_report.report_id if self._last_report else None,
                "run_count": self._run_count,
            }
        )

    def reconcile(
        self,
        *,
        mode: str = "report",
        actor: str = "system",
        source: str = "reconciliation",
        control_event_id: Optional[str] = None,
    ) -> ReconcileReport:
        mode = (mode or "report").lower().strip()
        if mode not in ("report", "repair"):
            mode = "report"

        started = time.time()
        report_id = control_event_id or f"recon-{uuid.uuid4().hex[:12]}"
        findings: List[Finding] = []

        with self._lock:
            self._run_count += 1
            findings.extend(self._check_orphans())
            findings.extend(self._check_stale())
            findings.extend(self._check_missing_correlation())
            findings.extend(self._check_github_gaps())
            findings.extend(self._check_state_consistency())
            integrations = self._probe_integrations()

            if mode == "repair":
                findings.extend(self._safe_repair(actor=actor, source=source))

            summary = {
                "total": len(findings),
                "error": sum(1 for f in findings if f.severity == "error"),
                "warning": sum(1 for f in findings if f.severity == "warning"),
                "info": sum(1 for f in findings if f.severity == "info"),
            }
            overall = self._overall(findings, integrations)
            report = ReconcileReport(
                report_id=report_id,
                started_at=started,
                finished_at=time.time(),
                findings=findings,
                integrations=integrations,
                summary=summary,
                overall_state=overall,
                mode=mode,
            )
            self._last_report = report

            try:
                get_policy_engine().authorize_and_record(
                    action="reconcile",
                    actor=actor,
                    source=source,
                    control_event_id=report_id,
                    external_ids={
                        "mode": mode,
                        "overall_state": overall.value,
                        "findings": str(summary.get("total", 0)),
                    },
                )
            except Exception:
                logger.exception("reconcile audit failed")

            return report

    def last_report(self) -> Optional[ReconcileReport]:
        return self._last_report

    def _check_orphans(self) -> List[Finding]:
        out: List[Finding] = []
        try:
            orphans = get_correlation_store().list_orphans()
        except Exception as e:
            logger.exception("orphan scan failed")
            return [
                Finding(
                    FindingKind.EXTERNAL_UNAVAILABLE,
                    "warning",
                    f"orphan scan failed: {e}",
                )
            ]
        for o in orphans:
            out.append(
                Finding(
                    FindingKind.ORPHAN_EXECUTION,
                    "warning",
                    f"execution {o.get('execution_id')} has monday source but no correlation",
                    execution_id=o.get("execution_id"),
                    monday_item_id=str(o.get("item_id")) if o.get("item_id") else None,
                    metadata={"status": o.get("status")},
                )
            )
        return out

    def _check_stale(self) -> List[Finding]:
        out: List[Finding] = []
        now = time.time()
        store = get_default_store()
        try:
            executions = store.list_executions()
        except Exception as e:
            return [
                Finding(
                    FindingKind.EXTERNAL_UNAVAILABLE,
                    "warning",
                    f"execution list failed: {e}",
                )
            ]
        for snap in executions:
            status = (snap.status or "").lower()
            if status in TERMINAL_STATUSES:
                continue
            ts = getattr(snap, "started_at", None) or getattr(snap, "created_at", None)
            if ts is None:
                continue
            age = now - float(ts)
            if age >= self._stale_seconds:
                out.append(
                    Finding(
                        FindingKind.STALE_EXECUTION,
                        "warning",
                        f"execution {snap.execution_id} non-terminal for {int(age)}s",
                        execution_id=snap.execution_id,
                        metadata={"status": status, "age_seconds": int(age)},
                    )
                )
        return out

    def _check_missing_correlation(self) -> List[Finding]:
        out: List[Finding] = []
        corr = get_correlation_store()
        store = get_default_store()
        try:
            records = corr.list_all()
        except Exception:
            return out
        known_execs = {r.get("execution_id") for r in records if r.get("execution_id")}
        for snap in store.list_executions():
            meta = snap.metadata or {}
            if meta.get("correlation_id") and snap.execution_id not in known_execs:
                out.append(
                    Finding(
                        FindingKind.MISSING_CORRELATION,
                        "warning",
                        f"execution {snap.execution_id} metadata has correlation_id but store has no record",
                        execution_id=snap.execution_id,
                        correlation_id=str(meta.get("correlation_id")),
                    )
                )
        for r in records:
            eid = r.get("execution_id")
            if eid and store.get_execution(eid) is None:
                out.append(
                    Finding(
                        FindingKind.STATE_INCONSISTENT,
                        "error",
                        f"correlation {r.get('correlation_id')} points to missing execution {eid}",
                        execution_id=eid,
                        correlation_id=r.get("correlation_id"),
                    )
                )
        return out

    def _check_github_gaps(self) -> List[Finding]:
        out: List[Finding] = []
        for r in get_correlation_store().list_all():
            if r.get("github_pr") and not r.get("ci_status"):
                out.append(
                    Finding(
                        FindingKind.MISSING_GITHUB,
                        "info",
                        f"PR {r.get('github_repo')}#{r.get('github_pr')} has no CI status yet",
                        execution_id=r.get("execution_id"),
                        correlation_id=r.get("correlation_id"),
                        github_pr=f"{r.get('github_repo')}#{r.get('github_pr')}",
                    )
                )
            if r.get("execution_id") and not r.get("github_pr") and not r.get("github_sha"):
                if r.get("monday_item_id"):
                    out.append(
                        Finding(
                            FindingKind.MISSING_GITHUB,
                            "info",
                            f"monday item {r.get('monday_item_id')} has no GitHub PR/SHA yet",
                            execution_id=r.get("execution_id"),
                            correlation_id=r.get("correlation_id"),
                            monday_item_id=str(r.get("monday_item_id")),
                        )
                    )
        return out

    def _check_state_consistency(self) -> List[Finding]:
        out: List[Finding] = []
        store = get_default_store()
        for r in get_correlation_store().list_all():
            eid = r.get("execution_id")
            if not eid:
                continue
            snap = store.get_execution(eid)
            if not snap:
                continue
            status = (snap.status or "").lower()
            ci = (r.get("ci_status") or "").lower()
            if ci in ("failure", "failed", "error") and status not in TERMINAL_STATUSES:
                out.append(
                    Finding(
                        FindingKind.STATE_INCONSISTENT,
                        "warning",
                        f"CI {ci} but execution {eid} still {status}",
                        execution_id=eid,
                        correlation_id=r.get("correlation_id"),
                        metadata={"ci_status": ci, "execution_status": status},
                    )
                )
        return out

    def _safe_repair(self, *, actor: str, source: str) -> List[Finding]:
        from .correlation import bind_execution_from_snapshot

        out: List[Finding] = []
        store = get_default_store()
        for snap in store.list_executions():
            meta = snap.metadata or {}
            if meta.get("source") == "monday" and meta.get("item_id"):
                corr = get_correlation_store().get_by_execution(snap.execution_id)
                if corr is None:
                    try:
                        bound = bind_execution_from_snapshot(snap)
                        if bound:
                            out.append(
                                Finding(
                                    FindingKind.MISSING_CORRELATION,
                                    "info",
                                    f"repaired correlation for {snap.execution_id}",
                                    execution_id=snap.execution_id,
                                    correlation_id=bound.correlation_id,
                                    metadata={
                                        "repaired": True,
                                        "actor": actor,
                                        "source": source,
                                    },
                                )
                            )
                    except Exception as e:
                        out.append(
                            Finding(
                                FindingKind.SYNC_INCOMPLETE,
                                "warning",
                                f"repair failed for {snap.execution_id}: {e}",
                                execution_id=snap.execution_id,
                            )
                        )
        return out

    def _probe_integrations(self) -> List[IntegrationHealth]:
        results: List[IntegrationHealth] = []

        try:
            from ..integrations.monday.adapter import get_monday_adapter

            h = get_monday_adapter().health()
            configured = bool(h.get("configured") or h.get("has_token") or h.get("valid"))
            live = bool(h.get("live_ready") or h.get("live_writes_enabled"))
            if not configured:
                state = HealthState.NOT_CONFIGURED
                detail = "monday credentials not configured"
            elif h.get("ok") is False or h.get("error"):
                state = HealthState.UNAVAILABLE
                detail = str(h.get("error") or h.get("detail") or "monday unhealthy")
            else:
                state = HealthState.HEALTHY
                detail = "monday reachable" if live else "monday configured (dry-run)"
            results.append(
                IntegrationHealth("monday", state, detail, configured=configured, live_ready=live)
            )
        except Exception as e:
            results.append(
                IntegrationHealth(
                    "monday",
                    HealthState.NOT_CONFIGURED,
                    f"monday probe skipped: {type(e).__name__}",
                    configured=False,
                )
            )

        try:
            from ..integrations.slack.adapter import get_slack_adapter

            h = get_slack_adapter().health()
            configured = bool(h.get("configured") or h.get("has_token"))
            if not configured:
                state = HealthState.NOT_CONFIGURED
                detail = "slack not configured"
            elif h.get("ok") is False:
                state = HealthState.UNAVAILABLE
                detail = str(h.get("error") or "slack unhealthy")
            else:
                state = HealthState.HEALTHY
                detail = "slack configured"
            results.append(
                IntegrationHealth("slack", state, detail, configured=configured)
            )
        except Exception as e:
            results.append(
                IntegrationHealth(
                    "slack",
                    HealthState.NOT_CONFIGURED,
                    f"slack probe skipped: {type(e).__name__}",
                    configured=False,
                )
            )

        try:
            n = len(get_correlation_store().list_all())
            results.append(
                IntegrationHealth(
                    "correlation",
                    HealthState.HEALTHY,
                    f"{n} correlation records",
                    configured=True,
                    live_ready=True,
                )
            )
        except Exception as e:
            results.append(
                IntegrationHealth(
                    "correlation",
                    HealthState.UNAVAILABLE,
                    str(e),
                    configured=True,
                )
            )

        try:
            n = len(get_default_store().list_executions())
            results.append(
                IntegrationHealth(
                    "execution_store",
                    HealthState.HEALTHY,
                    f"{n} executions",
                    configured=True,
                    live_ready=True,
                )
            )
        except Exception as e:
            results.append(
                IntegrationHealth(
                    "execution_store",
                    HealthState.UNAVAILABLE,
                    str(e),
                    configured=True,
                )
            )

        return results

    def _overall(
        self, findings: List[Finding], integrations: List[IntegrationHealth]
    ) -> HealthState:
        if any(i.state == HealthState.UNAVAILABLE for i in integrations):
            return HealthState.DEGRADED
        if any(f.severity == "error" for f in findings):
            return HealthState.DEGRADED
        if any(f.severity == "warning" for f in findings):
            return HealthState.DEGRADED
        return HealthState.HEALTHY


_engine: Optional[ReconciliationEngine] = None
_engine_lock = threading.Lock()


def get_reconciliation_engine() -> ReconciliationEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = ReconciliationEngine()
        return _engine
