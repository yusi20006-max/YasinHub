"""Tests for execution correlation model (#80)."""

from __future__ import annotations

import pytest

from yasinhub.execution.correlation import (
    CorrelationConflict,
    CorrelationStore,
    get_correlation_store,
)
from yasinhub.observer.execution_store import get_default_store


@pytest.fixture(autouse=True)
def reset():
    get_correlation_store().clear()
    get_default_store().clear()
    yield
    get_correlation_store().clear()
    get_default_store().clear()


def test_register_and_lookup():
    store = CorrelationStore()
    rec = store.register(
        execution_id="exec-1",
        correlation_id="corr-1",
        monday_item_id="item-9",
        github_repo="o/r",
        github_pr=12,
    )
    assert store.get_by_execution("exec-1").correlation_id == "corr-1"
    assert store.get_by_monday_item("item-9").execution_id == "exec-1"
    assert store.get_by_pr("o/r", 12).execution_id == "exec-1"
    assert rec.as_dict()["github_pr"] == 12


def test_conflict_on_monday_item():
    store = CorrelationStore()
    store.register(execution_id="e1", correlation_id="c1", monday_item_id="i1")
    with pytest.raises(CorrelationConflict):
        store.register(execution_id="e2", correlation_id="c2", monday_item_id="i1")


def test_conflict_on_pr():
    store = CorrelationStore()
    store.register(execution_id="e1", correlation_id="c1", github_repo="o/r", github_pr=1)
    with pytest.raises(CorrelationConflict):
        store.register(execution_id="e2", correlation_id="c2", github_repo="o/r", github_pr=1)


def test_resolve_github_deterministic():
    store = CorrelationStore()
    store.register(
        execution_id="e1",
        correlation_id="c1",
        github_repo="o/r",
        github_pr=5,
        github_sha="abc123",
    )
    rec, reason = store.resolve_github_event(repository="o/r", pr_number=5)
    assert reason == "matched"
    assert rec.execution_id == "e1"


def test_resolve_ambiguous():
    store = CorrelationStore()
    store.register(execution_id="e1", correlation_id="c1", github_sha="sha1")
    store.register(execution_id="e2", correlation_id="c2", github_repo="o/r", github_pr=9)
    # force same sha index collision path by resolving with both pointing different
    rec, reason = store.resolve_github_event(repository="o/r", pr_number=9, sha="sha1")
    assert reason == "ambiguous"
    assert rec is None


def test_orphans():
    store = get_default_store()
    store.create_execution(
        task_id="t",
        metadata={"source": "monday", "item_id": "orphan-1"},
        execution_id="exec-orphan",
    )
    orphans = get_correlation_store().list_orphans()
    assert any(o["execution_id"] == "exec-orphan" for o in orphans)


def test_duplicate_register_same_execution_ok():
    store = CorrelationStore()
    store.register(execution_id="e1", correlation_id="c1", monday_item_id="i1")
    rec = store.register(execution_id="e1", correlation_id="c1", github_pr=3, github_repo="o/r")
    assert rec.github_pr == 3
    assert rec.monday_item_id == "i1"
