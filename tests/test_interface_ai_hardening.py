import logging

import pytest

from yasinhub.interface.ai import (
    HttpAIProvider,
    NullAIProvider,
    _redact_secrets,
    create_ai_provider_from_env,
)


def test_missing_credentials_degrades_to_null(monkeypatch):
    monkeypatch.setenv("YASIN_AI_PROVIDER", "openai")
    monkeypatch.delenv("YASIN_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert isinstance(create_ai_provider_from_env(), NullAIProvider)


@pytest.mark.parametrize(
    "base_url",
    [
        "not-a-url",
        "ftp://example.com/v1",
        "https://user:secret@example.com/v1",
        "https://example.com/v1?token=secret",
        "https://example.com/v1#fragment",
    ],
)
def test_invalid_base_url_degrades_to_null(monkeypatch, base_url):
    monkeypatch.setenv("YASIN_AI_PROVIDER", "http")
    monkeypatch.setenv("YASIN_AI_API_KEY", "test-key")
    monkeypatch.setenv("YASIN_AI_BASE_URL", base_url)
    assert isinstance(create_ai_provider_from_env(), NullAIProvider)


@pytest.mark.parametrize("timeout", ["0", "-1", "121", "not-a-number"])
def test_invalid_timeout_degrades_to_null(monkeypatch, timeout):
    monkeypatch.setenv("YASIN_AI_PROVIDER", "http")
    monkeypatch.setenv("YASIN_AI_API_KEY", "test-key")
    monkeypatch.setenv("YASIN_AI_TIMEOUT", timeout)
    assert isinstance(create_ai_provider_from_env(), NullAIProvider)


def test_valid_openai_compatible_configuration(monkeypatch):
    monkeypatch.setenv("YASIN_AI_PROVIDER", "openai_compatible")
    monkeypatch.setenv("YASIN_AI_API_KEY", "test-key")
    monkeypatch.setenv("YASIN_AI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("YASIN_AI_MODEL", "test-model")
    monkeypatch.setenv("YASIN_AI_TIMEOUT", "20")
    provider = create_ai_provider_from_env()
    assert isinstance(provider, HttpAIProvider)
    assert provider._base_url == "https://example.com/v1"
    assert provider._model == "test-model"
    assert provider._timeout == 20.0
    assert provider._name == "openai"


def test_constructor_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        HttpAIProvider(api_key="", base_url="https://example.com/v1")
    with pytest.raises(ValueError):
        HttpAIProvider(api_key="key", base_url="bad")
    with pytest.raises(ValueError):
        HttpAIProvider(api_key="key", base_url="https://example.com/v1", model="")
    with pytest.raises(ValueError):
        HttpAIProvider(api_key="key", base_url="https://example.com/v1", timeout=0)


def test_invalid_provider_name_does_not_expose_configuration(monkeypatch, caplog):
    monkeypatch.setenv("YASIN_AI_PROVIDER", "secret-vendor")
    monkeypatch.setenv("YASIN_AI_API_KEY", "super-secret-key")
    with caplog.at_level(logging.INFO):
        provider = create_ai_provider_from_env()
    assert isinstance(provider, NullAIProvider)
    assert "super-secret-key" not in caplog.text
    assert "secret-vendor" not in caplog.text


def test_redaction_covers_common_secret_forms():
    text = "api_key=supersecret Bearer abc123 token: xyz sk-abcdefghijklmnop"
    redacted = _redact_secrets(text)
    assert "supersecret" not in redacted
    assert "abc123" not in redacted
    assert "xyz" not in redacted
    assert "sk-abcdefghijklmnop" not in redacted
