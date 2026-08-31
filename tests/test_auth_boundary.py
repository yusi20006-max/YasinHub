"""Production authentication boundary (#109)."""

from __future__ import annotations

import json
from io import BytesIO

import pytest

from yasinhub.auth import (
    AuthError,
    AuthMode,
    Role,
    YasinPrincipal,
    authenticate_http,
    get_auth_mode,
    reset_auth_for_tests,
    resolve_bearer_token,
)
from yasinhub.api.interface_routes import handle_interface_routes
from yasinhub.api.control_routes import handle_control_api_routes
from yasinhub.interface.ai import FakeAIProvider, reset_ai_provider_for_tests, set_ai_provider
from yasinhub.interface.engine import reset_yasin_interface_for_tests
from yasinhub.interface.session import reset_session_store_for_tests
from yasinhub.storage.shared_state import MemorySharedState, reset_shared_state_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_auth_for_tests()
    reset_shared_state_for_tests(MemorySharedState())
    reset_session_store_for_tests()
    reset_yasin_interface_for_tests()
    reset_ai_provider_for_tests()
    set_ai_provider(FakeAIProvider())
    yield
    reset_auth_for_tests()
    reset_yasin_interface_for_tests()
    reset_ai_provider_for_tests()
    reset_shared_state_for_tests(MemorySharedState())


def _tokens():
    return {
        "test-token-admin-xx": YasinPrincipal(
            yasin_user_id="alice",
            role=Role.ADMIN,
            auth_method="bearer_token",
        ),
        "test-token-ops-yyyy": YasinPrincipal(
            yasin_user_id="bob",
            role=Role.OPERATOR,
            auth_method="bearer_token",
        ),
    }


def test_production_mode_requires_token():
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens=_tokens())
    with pytest.raises(AuthError) as ei:
        authenticate_http({}, body_actor="attacker")
    assert ei.value.status == 401
    assert ei.value.code == "missing_token"


def test_production_rejects_invalid_token():
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens=_tokens())
    with pytest.raises(AuthError) as ei:
        authenticate_http({"Authorization": "Bearer wrong-token-zzzzzz"}, body_actor="x")
    assert ei.value.code == "invalid_token"


def test_valid_bearer_establishes_identity():
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens=_tokens())
    ctx = authenticate_http({"Authorization": "Bearer test-token-admin-xx"})
    assert ctx.authenticated is True
    assert ctx.actor == "alice"
    assert ctx.role == Role.ADMIN
    assert ctx.principal.auth_method == "bearer_token"


def test_soft_actor_allowed_only_in_development():
    reset_auth_for_tests(mode=AuthMode.DEVELOPMENT, tokens={})
    ctx = authenticate_http({}, body_actor="local-dev")
    assert ctx.authenticated is False
    assert ctx.actor == "local-dev"
    assert ctx.role == Role.VIEWER
    assert ctx.principal.auth_method == "soft_dev"


def test_token_fingerprint_not_equal_to_token():
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens={})
    assert resolve_bearer_token("test-token-admin-xx") is None
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens=_tokens())
    assert resolve_bearer_token("test-token-admin-xx").yasin_user_id == "alice"


def _iface(body, headers):
    payload = json.dumps(body).encode("utf-8")
    responses = []

    def send_json(data, status=200):
        responses.append((status, data))

    hdrs = {"Content-Length": str(len(payload))}
    hdrs.update(headers)
    handle_interface_routes(
        "/api/interface",
        "POST",
        "/api/interface",
        hdrs,
        BytesIO(payload),
        send_json,
    )
    return responses[0]


def test_interface_production_blocks_unauthenticated_mutation_path():
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens=_tokens())
    status, data = _iface({"text": "retry execution exec_1", "actor": "admin"}, {})
    assert status == 401
    assert data["success"] is False


def test_interface_production_accepts_bearer():
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens=_tokens())
    status, data = _iface(
        {"text": "status", "thread_id": "s1"},
        {"Authorization": "Bearer test-token-ops-yyyy"},
    )
    assert status == 200
    assert data["success"] is True


def test_interface_authenticated_actor_overrides_body_actor():
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens=_tokens())
    status, data = _iface(
        {"text": "status", "actor": "spoofed-admin", "yasin_user_id": "spoofed"},
        {"Authorization": "Bearer test-token-admin-xx"},
    )
    assert status == 200
    assert data["success"] is True


def _ctrl(body, headers):
    payload = json.dumps(body).encode("utf-8")
    responses = []

    def send_json(data, status=200):
        responses.append((status, data))

    hdrs = {"Content-Length": str(len(payload))}
    hdrs.update(headers)
    handle_control_api_routes(
        "/api/control",
        "POST",
        "/api/control",
        hdrs,
        BytesIO(payload),
        send_json,
    )
    return responses[0]


def test_control_production_requires_auth():
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens=_tokens())
    status, data = _ctrl(
        {"action": "status", "actor": "attacker", "source": "http-api"},
        {},
    )
    assert status == 401
    assert data["code"] == "missing_token"


def test_control_production_uses_token_identity_not_body_actor():
    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens=_tokens())
    status, data = _ctrl(
        {"action": "status", "actor": "spoofed", "source": "http-api"},
        {"Authorization": "Bearer test-token-ops-yyyy"},
    )
    assert status == 200
    assert data["success"] is True


def test_get_auth_mode_defaults_to_development_without_tokens(monkeypatch):
    monkeypatch.delenv("YASIN_AUTH_MODE", raising=False)
    monkeypatch.delenv("YASIN_AUTH_TOKENS", raising=False)
    reset_auth_for_tests()
    assert get_auth_mode() == AuthMode.DEVELOPMENT
