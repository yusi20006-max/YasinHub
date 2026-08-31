"""Confirmation expiry and atomic consume (#101 remaining)."""

from __future__ import annotations

import time

import pytest

from yasinhub.interface.ai import FakeAIProvider, reset_ai_provider_for_tests, set_ai_provider
from yasinhub.interface.engine import YasinInterface, reset_yasin_interface_for_tests
from yasinhub.interface.session import SessionStore, reset_session_store_for_tests
from yasinhub.observer.execution_store import get_default_store
from yasinhub.storage.shared_state import MemorySharedState, reset_shared_state_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_shared_state_for_tests(MemorySharedState())
    reset_session_store_for_tests()
    reset_yasin_interface_for_tests()
    reset_ai_provider_for_tests()
    set_ai_provider(FakeAIProvider())
    yield
    reset_yasin_interface_for_tests()
    reset_ai_provider_for_tests()
    reset_shared_state_for_tests(MemorySharedState())


def test_confirmation_expired_token():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec_exp1")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "x")
    iface = YasinInterface()
    r1 = iface.handle(
        "@Yasin retry execution exec_exp1",
        channel="slack",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="thr-exp",
    )
    token = r1.confirmation_token
    pending = iface.sessions.get_pending_control(token)
    assert pending
    pending["expires_at"] = time.time() - 10
    iface.sessions.save_pending_control(token, pending)
    r2 = iface.handle(
        f"@Yasin confirm {token}",
        channel="slack",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="thr-exp",
    )
    assert r2.success is False
    assert r2.error == "token_expired" or "expired" in r2.answer.lower()


def test_consume_pending_once():
    sessions = SessionStore()
    sessions.save_pending_control("cfm-once", {"token": "cfm-once", "operation": "retry", "actor": "a"})
    a = sessions.consume_pending_control("cfm-once")
    b = sessions.consume_pending_control("cfm-once")
    assert a is not None
    assert b is None


def test_text_confirm_same_path():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec_txt1")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "x")
    iface = YasinInterface()
    r1 = iface.handle(
        "@Yasin retry execution exec_txt1",
        channel="slack",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="thr-txt",
    )
    r2 = iface.handle(
        f"@Yasin confirm {r1.confirmation_token}",
        channel="slack",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="thr-txt",
    )
    assert r2.success is True
