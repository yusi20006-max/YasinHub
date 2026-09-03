"""Contract and regression tests for Termux / Android ARM64 / Python 3.14 compatibility (Issue #190)."""

import os
import sys
import hashlib
import hmac
import ssl
from pathlib import Path

import pytest
from yasinhub.interface.ai import (
    AICompletion,
    FakeAIProvider,
    HttpAIProvider,
    NullAIProvider,
    create_ai_provider_from_env,
    get_ai_provider,
    reset_ai_provider_for_tests,
)

ROOT = Path(__file__).resolve().parents[1]


def test_crypto_ssl_integrity() -> None:
    """Verify standard library cryptography and SSL work without weakening security."""
    key = b"canonical-yasin-key"
    msg = b"termux-android-arm64-test"
    signature = hmac.new(key, msg, hashlib.sha256).hexdigest()
    assert len(signature) == 64
    assert ssl.OPENSSL_VERSION


def test_termux_compatibility_docs_exist() -> None:
    doc = ROOT / "docs" / "TERMUX_COMPATIBILITY.md"
    assert doc.exists()
    content = doc.read_text(encoding="utf-8")
    assert "Android 11+" in content
    assert "ARM64" in content
    assert "API Level 30+" in content
    assert "ANDROID_API_LEVEL=30" in content
    assert "Python 3.14" in content


def test_ai_provider_canonical_contracts() -> None:
    """Ensure Yasin-AI request and completion contracts remain strict and unchanged."""
    fake = FakeAIProvider()
    res = fake.complete(system="sys", user="user", context={})
    assert isinstance(res, AICompletion)
    assert res.provider == "fake"
    assert res.text

    null_prov = NullAIProvider()
    res_null = null_prov.complete(system="sys", user="user", context={})
    assert isinstance(res_null, AICompletion)
    assert res_null.provider == "null"
    assert res_null.error == "not_configured"


def test_ai_provider_env_creation(monkeypatch) -> None:
    monkeypatch.setenv("YASIN_AI_PROVIDER", "openai")
    monkeypatch.setenv("YASIN_AI_API_KEY", "sk-test123456789012345")
    provider = create_ai_provider_from_env()
    assert isinstance(provider, HttpAIProvider)
    assert provider._name == "openai"


def test_ai_secret_redaction() -> None:
    reset_ai_provider_for_tests()
    from yasinhub.interface.ai import _redact_secrets
    raw = "sk-1234567890abcdef Authorization: Bearer sk-9876543210fedcba"
    redacted = _redact_secrets(raw)
    assert "sk-1234567890abcdef" not in redacted
    assert "sk-9876543210fedcba" not in redacted
    assert "[REDACTED]" in redacted
