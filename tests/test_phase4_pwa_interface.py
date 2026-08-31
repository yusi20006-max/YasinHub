"""Phase 4 PWA conversational path + dedupe fail-closed (#105)."""

from __future__ import annotations

import io
import json

import pytest

from yasinhub.api.interface_routes import handle_interface_routes
from yasinhub.interface.adapters import ChannelMessage, PWAChannelAdapter
from yasinhub.interface.ai import FakeAIProvider, reset_ai_provider_for_tests, set_ai_provider
from yasinhub.interface.engine import YasinInterface, reset_yasin_interface_for_tests
from yasinhub.interface.session import reset_session_store_for_tests
from yasinhub.integrations.slack.events import SlackInboundEvent
from yasinhub.integrations.slack.interactive import InteractionDeduper, InteractiveHandler
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


def _post_chat(text: str, **extra):
    body = {"text": text, "channel": "pwa", "actor": "pwa-user", **extra}
    raw = json.dumps(body).encode("utf-8")
    headers = {"Content-Length": str(len(raw))}
    captured = {}

    def send_json(data, status=200):
        captured["data"] = data
        captured["status"] = status

    ok = handle_interface_routes(
        "/api/interface/chat",
        "POST",
        "/api/interface/chat",
        headers,
        io.BytesIO(raw),
        send_json,
    )
    assert ok is True
    return captured


def test_pwa_read_investigation():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec_pwa1")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "boom")
    out = _post_chat("why did execution exec_pwa1 fail?", client_session_id="sess-a")
    assert out["status"] == 200
    assert out["data"]["success"] is True
    assert out["data"]["intent_kind"] == "INVESTIGATE_FAILURE"
    assert out["data"]["answer"]


def test_pwa_session_continuity():
    store = get_default_store()
    store.create_execution(task_id="t", execution_id="exec_pwa2")
    _post_chat("status of execution exec_pwa2", client_session_id="sess-b")
    out = _post_chat("what about that execution?", client_session_id="sess-b")
    assert out["data"]["answer"]


def test_pwa_control_confirmation():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec_pwa3")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "x")
    out1 = _post_chat(
        "retry execution exec_pwa3",
        client_session_id="sess-c",
        actor="ops1",
        yasin_user_id="ops1",
    )
    assert out1["data"]["confirmation_required"] is True
    token = out1["data"]["confirmation_token"]
    out2 = _post_chat(
        f"confirm {token}",
        client_session_id="sess-c",
        actor="ops1",
        yasin_user_id="ops1",
    )
    assert out2["data"]["success"] is True or out2["data"].get("intent_kind") == "CONFIRM_CONTROL"


def test_confirmation_replay_rejected():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec_rep1")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "x")
    iface = YasinInterface()
    r1 = iface.handle(
        "@Yasin retry execution exec_rep1",
        channel="pwa",
        source="pwa",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="thr-rep",
        require_mention=False,
    )
    token = r1.confirmation_token
    r2 = iface.handle(
        f"confirm {token}",
        channel="pwa",
        source="pwa",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="thr-rep",
        require_mention=False,
    )
    r3 = iface.handle(
        f"confirm {token}",
        channel="pwa",
        source="pwa",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="thr-rep",
        require_mention=False,
    )
    assert r2.success is True
    assert r3.success is False


def test_dedupe_sensitive_fail_closed():
    class BrokenStore:
        def try_acquire(self, *a, **k):
            raise RuntimeError("down")

        def get(self, *a, **k):
            raise RuntimeError("down")

    d = InteractionDeduper(store=BrokenStore())
    with pytest.raises(RuntimeError):
        d.already_processed("k1", sensitive=True)
    assert d.already_processed("k2", sensitive=False) is False


def test_interactive_confirm_when_dedupe_unavailable():
    class BrokenStore:
        def try_acquire(self, *a, **k):
            raise RuntimeError("down")

    from yasinhub.integrations.slack import interactive as ix

    old = ix._deduper
    ix._deduper = InteractionDeduper(store=BrokenStore())
    try:
        event = SlackInboundEvent(
            action_id="yasin_confirm",
            action_value="cfm-x",
            slack_user_id="U1",
            trigger_id="trig-1",
        )
        result = InteractiveHandler().handle(event)
        assert result.ok is False
        assert "unavailable" in result.text.lower() or "shared state" in result.text.lower()
    finally:
        ix._deduper = old


def test_interface_health():
    captured = {}

    def send_json(data, status=200):
        captured["data"] = data
        captured["status"] = status

    ok = handle_interface_routes(
        "/api/interface/health",
        "GET",
        "/api/interface/health",
        {},
        None,
        send_json,
    )
    assert ok is True
    assert captured["data"]["ok"] is True
