"""Tests for production observability and reconciliation (#83)."""

from __future__ import annotations

import time

from yasinhub.execution.reconciliation import (
    FindingKind,
    HealthState,
    control_plane_readiness,
    reconcile,
    reset_reconcile_state_for_tests,
)
from yasinhub.observer.execution_store import get_default_store


def setup_function():
    reset_reconcile_state_for_tests()


def test_readiness_optional_not_configured_is_not_core_failure():
    r = control_plane_readiness()
    assert r["core"] == "healthy"
    assert "status" in r
    assert "integrations" in r
    blob = str(r)
    assert "xoxb" not in blob
    assert "token" not in blob.lower() or "not configured" in blob.lower() or "missing" in blob.lower()


def test_healthy_empty_store():
    report = reconcile(dry_run=True)
    assert report.dry_run is True
    assert isinstance(report.summary.get("total"), int)


def test_stale_execution_detected():
    store = get_default_store()
    snap = store.create_execution(task_id="stale-task", execution_id="exec-stale-1")
    snap.created_at = time.time() - 10_000
    store.upsert_execution(snap)
    report = reconcile(dry_run=True, stale_seconds=60)
    kinds = [f.kind for f in report.findings]
    assert FindingKind.STALE_EXECUTION in kinds


def test_missing_correlation_for_slack_source():
    store = get_default_store()
    store.create_execution(
        task_id="t",
        execution_id="exec-slack-corr",
        metadata={"source": "slack", "actor": "u1"},
    )
    report = reconcile(dry_run=True)
    assert any(
        f.kind == FindingKind.MISSING_CORRELATION and f.execution_id == "exec-slack-corr"
        for f in report.findings
    )


def test_conflicting_state():
    store = get_default_store()
    snap = store.create_execution(
        task_id="t",
        execution_id="exec-conflict-1",
        metadata={"external_status": "failed"},
    )
    assert snap.status == "queued"
    report = reconcile(dry_run=True)
    assert any(f.kind == FindingKind.CONFLICTING_STATE for f in report.findings)


def test_repeated_reconcile_idempotent():
    r1 = reconcile(dry_run=True)
    r2 = reconcile(dry_run=True)
    assert r2.pass_number >= r1.pass_number
    assert any(f.kind == FindingKind.REPEATED_RECONCILE for f in r2.findings)


def test_dry_run_does_not_mutate():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec-dry-1")
    before = snap.status
    reconcile(dry_run=True, stale_seconds=1)
    after = store.get_execution("exec-dry-1")
    assert after is not None
    assert after.status == before


def test_health_states_enum():
    assert HealthState.HEALTHY.value == "healthy"
    assert HealthState.NOT_CONFIGURED.value == "not_configured"
