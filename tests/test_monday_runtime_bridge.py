"""Tests for monday -> Execution Runtime bridge (#65)."""

from __future__ import annotations

import pytest

from yasinhub.integrations.monday.adapter import MondayAdapter, set_monday_adapter
from yasinhub.integrations.monday.models import MondayNormalizedEvent
from yasinhub.integrations.monday.runtime_bridge import MondayRuntimeBridge, get_runtime_bridge
from yasinhub.observer.execution_store import get_default_store


@pytest.fixture(autouse=True)
def reset():
    set_monday_adapter(None)
    store = get_default_store()
    store.clear()
    yield
    store.clear()
    set_monday_adapter(None)


def _ready_event(item_id: str = "item-1", board_id: str = "board-1") -> MondayNormalizedEvent:
    return MondayNormalizedEvent(
        event_id=f"evt-{item_id}",
        event_type="task.ready",
        board_id=board_id,
        item_id=item_id,
        correlation_id=f"mon-{board_id}-{item_id}",
        name="Test task",
        column_values={"repository": "owner/repo", "agent": "yasin-agent"},
    )


def test_task_ready_creates_one_execution():
    bridge = MondayRuntimeBridge()
    snap = bridge.process_event(_ready_event())
    assert snap is not None
    assert snap.status == "queued"
    assert snap.metadata.get("source") == "monday"
    assert snap.metadata.get("item_id") == "item-1"
    assert snap.agent_id == "yasin-agent"


def test_duplicate_task_ready_idempotent():
    bridge = MondayRuntimeBridge()
    e = _ready_event()
    s1 = bridge.process_event(e)
    s2 = bridge.process_event(e)
    assert s1 is not None
    assert s2 is not None
    assert s1.execution_id == s2.execution_id
    store = get_default_store()
    assert len(store.list_executions()) == 1


def test_non_ready_ignored():
    bridge = MondayRuntimeBridge()
    evt = MondayNormalizedEvent(
        event_id="x",
        event_type="task.updated",
        board_id="b",
        item_id="i",
    )
    assert bridge.process_event(evt) is None


def test_cancel_for_item():
    bridge = MondayRuntimeBridge()
    snap = bridge.process_event(_ready_event("item-c"))
    assert snap is not None
    # start it so cancel is meaningful
    store = get_default_store()
    store.start(snap.execution_id)
    cancelled = bridge.cancel_for_item("item-c")
    assert cancelled is not None
    assert cancelled.status == "cancelled"
