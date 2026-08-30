"""Tests for monday state sync (#67)."""

from __future__ import annotations

from yasinhub.integrations.monday.sync import MondaySyncService, STATUS_MAP
from yasinhub.observer.execution_store import get_default_store


def test_status_map():
    assert STATUS_MAP["running"] == "Running"
    assert STATUS_MAP["succeeded"] == "Done"


def test_push_dry_run_without_credentials():
    store = get_default_store()
    store.clear()
    snap = store.create_execution(
        task_id="t1",
        metadata={"source": "monday", "board_id": "b1", "item_id": "i1"},
    )
    svc = MondaySyncService()
    result = svc.push_execution_to_monday(snap.execution_id)
    assert result["success"] is True
    assert result.get("dry_run") is True
    assert result["mapped_status"] == "Queued"
    store.clear()


def test_reconcile():
    store = get_default_store()
    store.clear()
    store.create_execution(
        task_id="t2",
        metadata={"source": "monday", "board_id": "b", "item_id": "i2"},
    )
    svc = MondaySyncService()
    out = svc.reconcile()
    assert out["success"] is True
    assert out["reconciled"] >= 1
    store.clear()
