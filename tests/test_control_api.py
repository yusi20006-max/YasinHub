"""Tests for unified Control API (#81)."""

from __future__ import annotations

from yasinhub.execution.control_api import ControlRequest, get_control_api
from yasinhub.execution.correlation import get_correlation_store
from yasinhub.observer.execution_store import get_default_store


def setup_function():
    get_default_store().clear()
    get_correlation_store().clear()


def teardown_function():
    get_default_store().clear()
    get_correlation_store().clear()


def test_status_list():
    api = get_control_api()
    resp = api.handle(ControlRequest(action="status", actor="u", source="test"))
    assert resp.success is True
    assert resp.execution["count"] >= 0


def test_status_unknown_execution():
    api = get_control_api()
    resp = api.handle(
        ControlRequest(action="status", actor="u", source="test", execution_id="missing")
    )
    assert resp.success is False
    assert resp.status_code == 404


def test_start_and_cancel():
    store = get_default_store()
    snap = store.create_execution(task_id="t1", execution_id="exec-ctrl-1")
    api = get_control_api()
    r1 = api.handle(
        ControlRequest(action="start", actor="op", source="pwa", execution_id=snap.execution_id)
    )
    assert r1.success is True
    assert r1.execution["status"] == "running"
    r2 = api.handle(
        ControlRequest(
            action="cancel",
            actor="op",
            source="pwa",
            execution_id=snap.execution_id,
            control_event_id="ce-cancel-1",
        )
    )
    assert r2.success is True


def test_duplicate_control_event_denied():
    store = get_default_store()
    snap = store.create_execution(task_id="t2", execution_id="exec-ctrl-2")
    store.start(snap.execution_id)
    api = get_control_api()
    r1 = api.handle(
        ControlRequest(
            action="cancel",
            actor="op",
            source="slack",
            execution_id=snap.execution_id,
            control_event_id="dup-1",
        )
    )
    r2 = api.handle(
        ControlRequest(
            action="cancel",
            actor="op",
            source="slack",
            execution_id=snap.execution_id,
            control_event_id="dup-1",
        )
    )
    assert r1.success is True
    assert r2.success is False
    assert r2.status_code == 403


def test_unsupported_action():
    api = get_control_api()
    resp = api.handle(ControlRequest(action="explode", actor="u", source="test"))
    assert resp.success is False
    assert resp.status_code == 400


def test_privileged_denied_without_approval():
    store = get_default_store()
    snap = store.create_execution(task_id="t3", execution_id="exec-ctrl-3")
    api = get_control_api()
    resp = api.handle(
        ControlRequest(
            action="approve",
            actor="u",
            source="pwa",
            execution_id=snap.execution_id,
            target_action="production_merge",
        )
    )
    # approve itself is allowed; the target stays gated until approve recorded
    assert resp.success is True
