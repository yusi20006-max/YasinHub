"""Production AI runtime integration (#110)."""

from __future__ import annotations

import pytest

from yasinhub.interface.ai import (
    FakeAIProvider,
    NullAIProvider,
    ai_runtime_status,
    create_ai_provider_from_env,
    reset_ai_provider_for_tests,
    sanitize_ai_context,
    set_ai_provider,
)
from yasinhub.interface.engine import YasinInterface, reset_yasin_interface_for_tests
from yasinhub.interface.session import Session, reset_session_store_for_tests
from yasinhub.storage.shared_state import MemorySharedState, reset_shared_state_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_shared_state_for_tests(MemorySharedState())
    reset_session_store_for_tests()
    reset_yasin_interface_for_tests()
    reset_ai_provider_for_tests()
    set_ai_provider(FakeAIProvider())
    yield
    reset_ai_provider_for_tests()
    reset_session_store_for_tests()
    reset_shared_state_for_tests(MemorySharedState())


def test_sanitize_strips_secrets_and_unknown_keys():
    ctx = sanitize_ai_context(
        {
            "actor": "alice",
            "source": "pwa",
            "api_key": "super-secret",
            "Authorization": "Bearer tok",
            "execution_id": "exec_1",
            "error": "failed token: sk-abcdefghijklmnop",
            "blob": "x" * 10000,
        }
    )
    assert ctx["actor"] == "alice"
    assert ctx["execution_id"] == "exec_1"
    assert "api_key" not in ctx
    assert "Authorization" not in ctx
    assert "blob" not in ctx
    assert "sk-abcdefghijklmnop" not in ctx.get("error", "")


def test_cancel_requested_short_circuits_provider():
    provider = FakeAIProvider()
    result = provider.complete(
        system="s",
        user="u",
        context={"cancel_requested": True, "execution_id": "exec_1"},
    )
    assert result.error == "cancelled"
    assert result.confidence == 0.0


def test_ai_runtime_status_never_includes_secrets(monkeypatch):
    monkeypatch.setenv("YASIN_AI_PROVIDER", "null")
    monkeypatch.setenv("YASIN_AI_API_KEY", "super-secret-key")
    reset_ai_provider_for_tests()
    status = ai_runtime_status()
    assert "super-secret-key" not in str(status)
    assert status["credentials_present"] is True
    assert status["status"] in ("ready", "degraded")


def test_engine_propagates_actor_source_into_ai_context():
    seen = {}

    class CaptureProvider:
        def complete(self, *, system, user, context):
            seen.update(context)
            return type("C", (), {"text": "ok", "confidence": 0.9, "provider": "cap", "error": None})()

    iface = YasinInterface(ai=CaptureProvider())
    resp = iface.handle(
        "status",
        channel="pwa",
        source="pwa",
        actor="alice",
        yasin_user_id="alice",
        require_mention=False,
        thread_id="t1",
    )
    assert resp.success is True
    assert seen.get("actor") == "alice"
    assert seen.get("source") == "pwa"


def test_missing_credentials_degrade_without_raising(monkeypatch):
    monkeypatch.setenv("YASIN_AI_PROVIDER", "openai")
    monkeypatch.delenv("YASIN_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = create_ai_provider_from_env()
    assert isinstance(provider, NullAIProvider)
