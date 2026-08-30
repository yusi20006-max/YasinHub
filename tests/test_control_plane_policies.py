"""Tests for Control Plane policies and audit (#68)."""

from __future__ import annotations

from yasinhub.execution.policies import PolicyEngine


def test_privileged_default_deny():
    eng = PolicyEngine()
    d = eng.evaluate(action="production_merge", execution_id="e1")
    assert d.allowed is False
    assert d.requires_approval is True


def test_approve_unlocks_privileged():
    eng = PolicyEngine()
    eng.approve("e1", "production_merge", actor="admin")
    d = eng.evaluate(action="production_merge", execution_id="e1")
    assert d.allowed is True


def test_standard_actions_allowed():
    eng = PolicyEngine()
    for action in ("start", "cancel", "retry", "re-run"):
        d = eng.evaluate(action=action)
        assert d.allowed is True


def test_idempotent_control_events():
    eng = PolicyEngine()
    d1 = eng.authorize_and_record(
        action="cancel", actor="u", source="monday", control_event_id="ce-1"
    )
    d2 = eng.authorize_and_record(
        action="cancel", actor="u", source="monday", control_event_id="ce-1"
    )
    assert d1.allowed is True
    assert d2.allowed is False
    assert "duplicate" in d2.reason


def test_audit_no_secrets():
    eng = PolicyEngine()
    eng.authorize_and_record(
        action="start",
        actor="user",
        source="hub",
        execution_id="ex1",
        metadata={"token": "secret-value"},  # type: ignore
    )
    audits = eng.list_audit()
    assert len(audits) >= 1
    raw = str(audits)
    assert "secret-value" not in raw or "***" in raw
