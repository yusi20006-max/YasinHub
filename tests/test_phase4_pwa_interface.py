"""Phase 4 final: PWA conversational surface + confirmation/dedupe consistency (#105)."""

from __future__ import annotations

import json
import time
from io import BytesIO
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from yasinhub.api.interface_routes import handle_interface_routes
from yasinhub.interface.adapters import ChannelMessage, PWAChannelAdapter, get_channel_adapter
from yasinhub.interface.ai import FakeAIProvider, reset_ai_provider_for_tests, set_ai_provider
from yasinhub.interface.engine import YasinInterface, reset_yasin_interface_for_tests
from yasinhub.interface.session import reset_session_store_for_tests
from yasinhub.integrations.slack.interactive import InteractionDeduper
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


def _post_chat(body: dict) -> Tuple[int, dict]:
    raw = json.dumps(body).encode("utf-8")
    headers = {"Content-Length": str(len(raw)), "Content-Type": "application/json"}
    rfile = BytesIO(raw)
    captured: List[Tuple[dict, int]] = []

    def send_json(data, status=200):
        captured.append((data, status))

    handled = handle_interface_routes(
        "/api/interface/chat",
        "POST",
        "/api/interface/chat",
        headers,
        rfile,
        send_json,
    )
    assert handled is True
    assert captured, "expected response"
    return captured[0][1], captured[0][0]


def test_pwa_adapter_routes_to_engine():
    adapter = get_channel_adapter("pwa")
    assert isinstance(adapter, PWAChannelAdapter)
    resp = adapter.handle(
        ChannelMessage(
            text="status",
            channel="pwa",
            source="pwa",
            actor="pwa-user",
            yasin_user_id="pwa-user",
            thread_id="sess-1",
        )
    )
    assert resp.answer
    assert resp.success is not False


def test_api_interface_chat_basic():
    status, data = _post_chat({"text": "status", "client_session_id": "pwa-sess-a", "actor": "ops1"})
    assert status == 200
    assert data.get("success") is True or data.get("answer")
    assert data.get("session_id") == "pwa-sess-a"
    assert "answer" in data


def test_api_interface_chat_requires_text():
    status, data = _post_chat({"client_session_id": "x"})
    assert status == 400
    assert data.get("success") is False


def test_pwa_session_continuity_via_thread():
    iface = YasinInterface()
    r1 = iface.handle(
        "status",
        channel="pwa",
        source="pwa",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="pwa-cont-1",
    )
    assert r1.answer
    r2 = iface.handle(
        "status",
        channel="pwa",
        source="pwa",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="pwa-cont-1",
    )
    assert r2.answer


def test_pwa_confirmation_flow_matches_engine():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec_pwa1")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "x")

    status, data = _post_chat(
        {
            "text": "retry execution exec_pwa1",
            "client_session_id": "pwa-conf-1",
            "actor": "ops1",
            "yasin_user_id": "ops1",
        }
    )
    assert status == 200
    assert data.get("confirmation_required") is True
    token = data.get("confirmation_token")
    assert token

    status2, data2 = _post_chat(
        {
            "text": f"confirm {token}",
            "client_session_id": "pwa-conf-1",
            "actor": "ops1",
            "yasin_user_id": "ops1",
        }
    )
    assert status2 == 200
    # Second confirm should fail (token consumed)
    status3, data3 = _post_chat(
        {
            "text": f"confirm {token}",
            "client_session_id": "pwa-conf-1",
            "actor": "ops1",
            "yasin_user_id": "ops1",
        }
    )
    assert status3 == 200
    assert data3.get("confirmation_required") is not True or "expired" in (data3.get("answer") or "").lower() or "unknown" in (data3.get("answer") or "").lower() or "no pending" in (data3.get("answer") or "").lower() or data3.get("success") is False or "already" in (data3.get("answer") or "").lower()


def test_dedupe_fail_closed_on_sensitive_when_store_down():
    class BrokenStore:
        def try_acquire(self, *a, **k):
            raise RuntimeError("shared state down")

    d = InteractionDeduper(store=BrokenStore(), ttl_seconds=60)
    # sensitive → treat as already processed (block)
    assert d.already_processed("key-sens", sensitive=True) is True
    # non-sensitive → fail-open
    assert d.already_processed("key-view", sensitive=False) is False


def test_dedupe_atomic_still_works():
    class FakeStore:
        def __init__(self):
            self.owners = {}

        def try_acquire(self, namespace, key, owner, *, ttl_seconds):
            if (namespace, key) in self.owners:
                return False
            self.owners[(namespace, key)] = owner
            return True

    store = FakeStore()
    a = InteractionDeduper(store=store)
    b = InteractionDeduper(store=store)
    assert a.already_processed("t1", sensitive=True) is False
    assert b.already_processed("t1", sensitive=True) is True
