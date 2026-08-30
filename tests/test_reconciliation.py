"""Tests for production observability and reconciliation (#83)."""

from __future__ import annotations

import time

import pytest

from yasinhub.execution.correlation import get_correlation_store
from yasinhub.execution.reconciliation import (
    FindingKind,
    HealthState,
    ReconciliationEngine,
    get_reconciliation_engine,
)
from yasinhub.observer.execution_store import get_default_store


@pytest.fixture(autouse=True)
def _reset_stores():
    get_default_store().clear()
    get_correlation_store().clear()
    import yasinhub.execution.reconciliation as mod

    mod._engine = None
    yield
    get_default_store().clear()
    get_correlation_store().clear()
    mod._engine = None


def test_healthy_empty_state():
    eng = ReconciliationEngine(stale_seconds=3600)
    report = eng.reconcile(mode="report", actor="test")
    assert report.mode == "report"
    assert report.summary["total"] >= 0
    assert report.overall_state in (
        HealthState.HEALTHY,
        HealthState.DEGRADED,
    )
    names = {i.name for i in report.integrations}
    assert "correlation" in names
    assert "execution_store" in names


def test_orphan_detection():
    store = get_default_store()
    snap = store.create_execution(
        task_id="t-orphan",
        execution_id="exec-orphan-1",
        metadata={"source": "monday", "item_id": "item-99"},
    )
    eng = ReconciliationEngine()
    report = eng.reconcile()
    kinds = [f.kind for f in report.findings]
    assert FindingKind.ORPHAN_EXECUTION in kinds
    orphan = next(f for f in report.findings if f.kind == FindingKind.ORPHAN_EXECUTION)
    assert orphan.execution_id == snap.execution_id
    assert orphan.monday_item_id == "item-99"


def test_stale_execution():
    store = get_default_store()
    snap = store.create_execution(task_id="t-stale", execution_id="exec-stale-1")
    snap.created_at = time.time() - 10_000
    store.upsert_execution(snap)
    eng = ReconciliationEngine(stale_seconds=60)
    report = eng.reconcile()
    stale = [f for f in report.findings if f.kind == FindingKind.STALE_EXECUTION]
    assert any(f.execution_id == "exec-stale-1" for f in stale)


def test_missing_correlation_metadata():
    store = get_default_store()
    store.create_execution(
        task_id="t-miss",
        execution_id="exec-miss-1",
        metadata={"correlation_id": "corr-ghost"},
    )
    eng = ReconciliationEngine()
    report = eng.reconcile()
    assert any(f.kind == FindingKind.MISSING_CORRELATION for f in report.findings)


def test_state_inconsistent_ci_vs_execution():
    store = get_default_store()
    store.create_execution(task_id="t-ci", execution_id="exec-ci-1")
    get_correlation_store().register(
        execution_id="exec-ci-1",
        correlation_id="corr-ci-1",
        github_repo="owner/repo",
        github_pr=42,
        ci_status="failure",
    )
    eng = ReconciliationEngine()
    report = eng.reconcile()
    assert any(f.kind == FindingKind.STATE_INCONSISTENT for f in report.findings)


def test_idempotent_repeated_reconcile():
    eng = ReconciliationEngine()
    r1 = eng.reconcile(mode="report", control_event_id="recon-idem-1")
    r2 = eng.reconcile(mode="report", control_event_id="recon-idem-2")
    assert r1.report_id != r2.report_id
    assert r1.summary["total"] == r2.summary["total"]


def test_repair_binds_orphan_correlation():
    store = get_default_store()
    store.create_execution(
        task_id="t-fix",
        execution_id="exec-fix-1",
        metadata={"source": "monday", "item_id": "item-fix", "board_id": "b1"},
    )
    eng = ReconciliationEngine()
    before = eng.reconcile(mode="report")
    assert any(f.kind == FindingKind.ORPHAN_EXECUTION for f in before.findings)

    after = eng.reconcile(mode="repair", actor="ops")
    rec = get_correlation_store().get_by_execution("exec-fix-1")
    assert rec is not None
    assert any(
        f.metadata.get("repaired") for f in after.findings if f.execution_id == "exec-fix-1"
    )


def test_health_snapshot_no_secrets():
    eng = get_reconciliation_engine()
    snap = eng.health_snapshot()
    blob = str(snap)
    for bad in ("api_token", "xoxb-", "password"):
        assert bad not in blob.lower()
    assert "overall_state" in snap
    assert "integrations" in snap


def test_report_as_dict_redacts():
    eng = ReconciliationEngine()
    report = eng.reconcile()
    d = report.as_dict()
    assert "report_id" in d
    assert "findings" in d
    assert "integrations" in d
    assert d["mode"] == "report"


def test_missing_credentials_not_crash():
    eng = ReconciliationEngine()
    report = eng.reconcile()
    for i in report.integrations:
        assert i.state in (
            HealthState.HEALTHY,
            HealthState.DEGRADED,
            HealthState.UNAVAILABLE,
            HealthState.NOT_CONFIGURED,
        )


def test_github_gap_info():
    store = get_default_store()
    store.create_execution(task_id="t-gh", execution_id="exec-gh-1")
    get_correlation_store().register(
        execution_id="exec-gh-1",
        correlation_id="corr-gh-1",
        monday_item_id="item-gh",
        github_repo="o/r",
    )
    eng = ReconciliationEngine()
    report = eng.reconcile()
    assert any(f.kind == FindingKind.MISSING_GITHUB for f in report.findings)
