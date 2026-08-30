"""
Production observability and reconciliation control plane (#83/#93).

Detects inconsistencies across monday ↔ YasinHub execution ↔ GitHub ↔ Agent
without performing privileged mutations by default.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .correlation import get_correlation_store
from ..observer.execution_store import get_default_store

logger = logging.getLogger(__name__)


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class FindingKind(str, Enum):
    STALE_EXECUTION = "stale_execution"
    ORPHAN_EXECUTION = "orphan_execution"
    MISSING_CORRELATION = "missing_correlation"
    CONFLICTING_STATE = "conflicting_state"
    STALE_MONDAY = "stale_monday"
    MISSING_GITHUB = "missing_github"
    FAILED_SYNC = "failed_sync"
    INCOMPLETE_SYNC = "incomplete_sync"
    REPEATED_RECONCILE = "repeated_reconcile"


@dataclass
class Finding:
    kind: FindingKind
    severity: str
    execution_id: Optional[str] = None
    correlation_id: Optional[str] = None
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "severity": self.severity,
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass
class IntegrationHealth:
    name: str
    state: HealthState
    detail: str = ""
    configured: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "detail": self.detail,
            "configured": self.configured,
        }


@dataclass
class ReconciliationReport:
    generated_at: float
    findings: List[Finding]
    integrations: List[IntegrationHealth]
    summary: Dict[str, int]
    dry_run: bool = True
    pass_number: int = 1

    def as_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "dry_run": self.dry_run,
            "pass_number": self.pass_number,
            "summary": dict(self.summary),
            "findings": [f.as_dict() for f in self.findings],
            "integrations": [i.as_dict() for i in self.integrations],
        }


_reconcile_passes = 0
_last_report: Optional[ReconciliationReport] = None

STALE_SECONDS_DEFAULT = 3600.0


def _monday_health() -> IntegrationHealth:
    try:
        from ..integrations.monday.config import load_monday_config

        cfg = load_monday_config()
        if not getattr(cfg, "enabled", False) and not getattr(cfg, "api_token", None):
            return IntegrationHealth(
                name="monday",
                state=HealthState.NOT_CONFIGURED,
                detail="monday credentials not configured",
                configured=False,
            )
        token = getattr(cfg, "api_token", None) or ""
        if not token:
            return IntegrationHealth(
                name="monday",
                state=HealthState.NOT_CONFIGURED,
                detail="api token missing",
                configured=False,
            )
        return IntegrationHealth(
            name="monday",
            state=HealthState.HEALTHY,
            detail="configured",
            configured=True,
        )
    except Exception as exc:
        return IntegrationHealth(
            name="monday",
            state=HealthState.UNAVAILABLE,
            detail=type(exc).__name__,
            configured=False,
        )


def _slack_health() -> IntegrationHealth:
    try:
        from ..integrations.slack.config import load_slack_config, is_slack_enabled

        cfg = load_slack_config()
        if not is_slack_enabled(cfg):
            return IntegrationHealth(
                name="slack",
                state=HealthState.NOT_CONFIGURED,
                detail="slack disabled or missing credentials",
                configured=False,
            )
        return IntegrationHealth(
            name="slack",
            state=HealthState.HEALTHY,
            detail="configured",
            configured=True,
        )
    except Exception as exc:
        return IntegrationHealth(
            name="slack",
            state=HealthState.UNAVAILABLE,
            detail=type(exc).__name__,
            configured=False,
        )


def _github_health() -> IntegrationHealth:
    try:
        import os

        secret = os.environ.get("YASIN_GITHUB_WEBHOOK_SECRET") or os.environ.get(
            "GITHUB_WEBHOOK_SECRET"
        )
        if not secret:
            return IntegrationHealth(
                name="github",
                state=HealthState.NOT_CONFIGURED,
                detail="webhook secret not configured",
                configured=False,
            )
        return IntegrationHealth(
            name="github",
            state=HealthState.HEALTHY,
            detail="webhook secret present",
            configured=True,
        )
    except Exception as exc:
        return IntegrationHealth(
            name="github",
            state=HealthState.UNAVAILABLE,
            detail=type(exc).__name__,
            configured=False,
        )


def integration_health() -> List[IntegrationHealth]:
    return [_monday_health(), _github_health(), _slack_health()]


def control_plane_readiness() -> Dict[str, Any]:
    integrations = integration_health()
    optional_down = [i for i in integrations if i.state in (HealthState.UNAVAILABLE,)]
    not_cfg = [i for i in integrations if i.state == HealthState.NOT_CONFIGURED]
    core = HealthState.HEALTHY
    overall = HealthState.DEGRADED if optional_down else HealthState.HEALTHY
    return {
        "status": overall.value,
        "core": core.value,
        "integrations": [i.as_dict() for i in integrations],
        "not_configured": [i.name for i in not_cfg],
        "degraded": [i.name for i in optional_down],
        "message": (
            "optional integrations unconfigured is not a core failure"
            if not_cfg and not optional_down
            else overall.value
        ),
    }


def reconcile(
    *,
    dry_run: bool = True,
    stale_seconds: float = STALE_SECONDS_DEFAULT,
    now: Optional[float] = None,
    worker_id: Optional[str] = None,
    skip_lock: bool = False,
) -> ReconciliationReport:
    """Idempotent dry-run by default. Coordinated across workers via shared lock (#93)."""
    import uuid as _uuid

    owner = worker_id or f"worker-{_uuid.uuid4().hex[:8]}"
    lock_acquired = True
    if not skip_lock:
        try:
            from ..storage.shared_state import NS_RECONCILE_LOCKS, get_shared_state

            lock_acquired = get_shared_state().try_acquire(
                NS_RECONCILE_LOCKS, "global", owner, ttl_seconds=30.0
            )
        except Exception:
            lock_acquired = True

    if not lock_acquired:
        if _last_report is not None:
            return _last_report
        return ReconciliationReport(
            generated_at=now if now is not None else time.time(),
            findings=[
                Finding(
                    kind=FindingKind.REPEATED_RECONCILE,
                    severity="info",
                    message="reconcile skipped — another worker holds the lock",
                    details={"owner_attempt": owner},
                )
            ],
            integrations=integration_health(),
            summary={"total": 1, "skipped": 1},
            dry_run=dry_run,
            pass_number=_reconcile_passes,
        )

    try:
        return _reconcile_body(dry_run=dry_run, stale_seconds=stale_seconds, now=now)
    finally:
        if not skip_lock and lock_acquired:
            try:
                from ..storage.shared_state import NS_RECONCILE_LOCKS, get_shared_state

                get_shared_state().release(NS_RECONCILE_LOCKS, "global", owner)
            except Exception:
                pass


def _reconcile_body(
    *,
    dry_run: bool = True,
    stale_seconds: float = STALE_SECONDS_DEFAULT,
    now: Optional[float] = None,
) -> ReconciliationReport:
    global _reconcile_passes, _last_report
    _reconcile_passes += 1
    ts = now if now is not None else time.time()
    findings: List[Finding] = []
    store = get_default_store()
    corr_store = get_correlation_store()

    try:
        executions = store.list_executions()
    except Exception as exc:
        logger.warning("reconcile_list_failed error=%s", type(exc).__name__)
        findings.append(
            Finding(
                kind=FindingKind.FAILED_SYNC,
                severity="error",
                message=f"cannot list executions: {type(exc).__name__}",
            )
        )
        executions = []

    for snap in executions:
        eid = getattr(snap, "execution_id", None) or ""
        status = getattr(snap, "status", None) or ""
        meta = getattr(snap, "metadata", None) or {}
        if not isinstance(meta, dict):
            meta = {}
        created = getattr(snap, "created_at", None) or 0.0
        started = getattr(snap, "started_at", None)
        finished = getattr(snap, "finished_at", None)
        updated = finished or started or created

        if status in ("queued", "running", "paused") and updated:
            age = ts - float(updated)
            if age > stale_seconds:
                findings.append(
                    Finding(
                        kind=FindingKind.STALE_EXECUTION,
                        severity="warning",
                        execution_id=eid,
                        message=f"execution non-terminal for {int(age)}s",
                        details={"status": status, "age_seconds": int(age)},
                    )
                )

        corr = None
        try:
            corr = corr_store.get_by_execution(eid)
        except Exception:
            corr = None

        source = meta.get("source") or ""
        if source in ("monday", "slack", "github") and corr is None:
            findings.append(
                Finding(
                    kind=FindingKind.MISSING_CORRELATION,
                    severity="warning",
                    execution_id=eid,
                    message="integration-originated execution lacks correlation record",
                    details={"source": source},
                )
            )

        if corr is None and not meta.get("item_id") and not meta.get("pr_number"):
            if status in ("succeeded", "failed", "cancelled") and updated and (ts - float(updated)) > stale_seconds:
                findings.append(
                    Finding(
                        kind=FindingKind.ORPHAN_EXECUTION,
                        severity="info",
                        execution_id=eid,
                        message="terminal execution with no external correlation",
                        details={"status": status},
                    )
                )

        if (meta.get("repository") or meta.get("pr_number")) and corr is not None:
            gh_pr = getattr(corr, "github_pr", None) if not isinstance(corr, dict) else corr.get("github_pr")
            if meta.get("pr_number") and not gh_pr:
                findings.append(
                    Finding(
                        kind=FindingKind.INCOMPLETE_SYNC,
                        severity="info",
                        execution_id=eid,
                        correlation_id=getattr(corr, "correlation_id", None)
                        if not isinstance(corr, dict)
                        else corr.get("correlation_id"),
                        message="PR number in metadata but correlation github_pr empty",
                    )
                )
        elif meta.get("pr_number") and corr is None:
            findings.append(
                Finding(
                    kind=FindingKind.MISSING_GITHUB,
                    severity="warning",
                    execution_id=eid,
                    message="execution references PR without correlation record",
                    details={"pr_number": meta.get("pr_number")},
                )
            )

        if meta.get("external_status") and str(meta.get("external_status")) != str(status):
            findings.append(
                Finding(
                    kind=FindingKind.CONFLICTING_STATE,
                    severity="warning",
                    execution_id=eid,
                    message="external_status metadata disagrees with execution status",
                    details={
                        "execution_status": status,
                        "external_status": meta.get("external_status"),
                    },
                )
            )

    if _reconcile_passes > 1:
        findings.append(
            Finding(
                kind=FindingKind.REPEATED_RECONCILE,
                severity="info",
                message=f"reconcile pass #{_reconcile_passes} (idempotent, dry_run={dry_run})",
                details={"pass": _reconcile_passes},
            )
        )

    integrations = integration_health()
    summary: Dict[str, int] = {}
    for f in findings:
        summary[f.kind.value] = summary.get(f.kind.value, 0) + 1
    summary["total"] = len(findings)

    report = ReconciliationReport(
        generated_at=ts,
        findings=findings,
        integrations=integrations,
        summary=summary,
        dry_run=dry_run,
        pass_number=_reconcile_passes,
    )
    _last_report = report
    return report


def get_last_report() -> Optional[ReconciliationReport]:
    return _last_report


def reset_reconcile_state_for_tests() -> None:
    global _reconcile_passes, _last_report
    _reconcile_passes = 0
    _last_report = None
