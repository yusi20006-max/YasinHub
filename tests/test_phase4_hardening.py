"""Phase 4 interface hardening (#101)."""

from __future__ import annotations

import time

import pytest

from yasinhub.interface.adapters import (
    ChannelMessage,
    CLIChannelAdapter,
    PWAChannelAdapter,
    SlackChannelAdapter,
    get_channel_adapter,
)
from yasinhub.interface.ai import (
    FakeAIProvider,
    NullAIProvider,
    create_ai_provider_from_env,
    reset_ai_provider_for_tests,
    set_ai_provider,
    validate_ai_config,
)
from yasinhub.interface.engine import YasinInterface, reset_yasin_interface_for_tests
from yasinhub.interface.session import SessionStore, reset_session_store_for_tests
from yasinhub.integrations.slack.interactive import InteractionDeduper
from yasinhub.observer.execution_store import get_default_store
from yasinhub.storage.shared_state import FileSharedState, MemorySharedState, reset_shared_state_for_tests


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


def test_validate_ai_config_missing_key_degrades():
    cfg = validate_ai_config(
        provider="openai", api_key="", base_url="https://api.openai.com/v1", model="gpt-4o-mini"
    )
    assert "missing_api_key" in cfg["issues"]
    assert cfg["has_api_key"] is False


def test_validate_ai_config_invalid_base_url():
    cfg = validate_ai_config(provider="openai", api_key="k", base_url="ftp://evil", model="m")
    assert "invalid_base_url" in cfg["issues"]
    assert cfg["ok"] is False


def test_validate_ai_config_invalid_timeout():
    cfg = validate_ai_config(
        provider="openai", api_key="k", base_url="https://x", model="m", timeout=9999
    )
    assert "timeout_out_of_range" in cfg["issues"]


def test_create_provider_invalid_url_uses_null(monkeypatch):
    monkeypatch.setenv("YASIN_AI_PROVIDER", "openai")
    monkeypatch.setenv("YASIN_AI_API_KEY", "sk-test")
    monkeypatch.setenv("YASIN_AI_BASE_URL", "not-a-url")
    monkeypatch.setenv("YASIN_AI_MODEL", "m")
    p = create_ai_provider_from_env()
    assert isinstance(p, NullAIProvider)


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
    sessions = iface.sessions
    pending = sessions.get_pending_control(token)
    assert pending
    pending["expires_at"] = time.time() - 10
    sessions.save_pending_control(token, pending)
    r2 = iface.handle(
        f"@Yasin confirm {token}",
        channel="slack",
        actor="ops1",
        yasin_user_id="ops1",
        thread_id="thr-exp",
    )
    assert r2.success is False
    assert r2.error == "token_expired" or "expired" in r2.answer.lower()


def test_text_confirm_same_secure_path():
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


def test_consume_pending_once():
    sessions = SessionStore()
    sessions.save_pending_control("cfm-once", {"token": "cfm-once", "operation": "retry", "actor": "a"})
    a = sessions.consume_pending_control("cfm-once")
    b = sessions.consume_pending_control("cfm-once")
    assert a is not None
    assert b is None


def test_shared_state_interaction_dedupe(tmp_path):
    root = tmp_path / "d"
    fs = FileSharedState(root)
    d1 = InteractionDeduper(store=fs)
    d2 = InteractionDeduper(store=FileSharedState(root))
    assert d1.already_processed("key-1") is False
    assert d2.already_processed("key-1") is True


def test_adapters_share_engine_path():
    store = get_default_store()
    store.create_execution(task_id="t", execution_id="exec_ad1")
    cli = get_channel_adapter("cli")
    pwa = get_channel_adapter("pwa")
    assert isinstance(cli, CLIChannelAdapter)
    assert isinstance(pwa, PWAChannelAdapter)
    r1 = cli.handle(ChannelMessage(text="status of execution exec_ad1", channel="cli", source="cli", actor="u"))
    r2 = pwa.handle(ChannelMessage(text="status of execution exec_ad1", channel="pwa", source="pwa", actor="u"))
    assert r1.intent_kind == r2.intent_kind
    assert r1.answer and r2.answer


def test_slack_adapter_no_duplicate_logic():
    ad = SlackChannelAdapter()
    r = ad.handle(ChannelMessage(text="@Yasin status", channel="slack", source="slack", actor="u"))
    assert r.answer
