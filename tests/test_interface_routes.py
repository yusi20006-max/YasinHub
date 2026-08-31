"""PWA conversational adapter coverage for Issue #105."""

from __future__ import annotations

import json
from io import BytesIO

import pytest

from yasinhub.interface.ai import FakeAIProvider, reset_ai_provider_for_tests, set_ai_provider
from yasinhub.interface.engine import reset_yasin_interface_for_tests
from yasinhub.interface.session import reset_session_store_for_tests
from yasinhub.observer.execution_store import get_default_store
from yasinhub.storage.shared_state import MemorySharedState, reset_shared_state_for_tests
from yasinhub.api.interface_routes import handle_interface_routes


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


def _call(body, *, method="POST", actor="ops1"):
    payload = json.dumps(body).encode("utf-8")
    responses = []

    def send_json(data, status=200):
        responses.append((status, data))

    handled = handle_interface_routes(
        "/api/interface",
        method,
        "/api/interface",
        {"Content-Length": str(len(payload)), "X-Actor": actor},
        BytesIO(payload),
        send_json,
    )
    assert handled is True
    assert len(responses) == 1
    return responses[0]


def test_pwa_read_request_uses_existing_interface_engine():
    status, data = _call(
        {"text": "status", "thread_id": "pwa-session-1"},
    )

    assert status == 200
    assert data["success"] is True
    assert data["intent_kind"] == "READ_STATUS"


def test_pwa_session_continuity_reuses_execution_context():
    store = get_default_store()
    snap = store.create_execution(task_id="pwa", execution_id="exec_pwa_1")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "provider unavailable")

    status, first = _call(
        {"text": "status of execution exec_pwa_1", "thread_id": "pwa-session-2"},
    )
    assert status == 200
    assert first["execution_refs"] == ["exec_pwa_1"]

    status, second = _call(
        {"text": "why did it fail", "thread_id": "pwa-session-2"},
    )
    assert status == 200
    assert second["execution_refs"] == ["exec_pwa_1"]


def test_pwa_control_request_returns_confirmation_token():
    store = get_default_store()
    snap = store.create_execution(task_id="pwa", execution_id="exec_pwa_2")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "failure")

    status, data = _call(
        {"text": "retry execution exec_pwa_2", "thread_id": "pwa-session-3"},
    )

    assert status == 200
    assert data["confirmation_required"] is True
    assert data["confirmation_token"]


def test_pwa_confirmation_uses_same_secure_path():
    store = get_default_store()
    snap = store.create_execution(task_id="pwa", execution_id="exec_pwa_3")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "failure")

    _, proposal = _call(
        {"text": "retry execution exec_pwa_3", "thread_id": "pwa-session-4"},
    )
    token = proposal["confirmation_token"]

    status, result = _call(
        {"text": f"confirm {token}", "thread_id": "pwa-session-4"},
    )

    assert status == 200
    assert result["success"] is True
    assert result["error"] is None

    _, replay = _call(
        {"text": f"confirm {token}", "thread_id": "pwa-session-4"},
    )
    assert replay["success"] is False
    assert replay["error"] in {"token_expired_or_unknown", "token_already_used"}


def test_pwa_route_rejects_invalid_requests():
    status, data = _call({})
    assert status == 400
    assert "text" in data["error"]

    status, data = _call({"text": "x" * 2001})
    assert status == 400
    assert "exceeds" in data["error"]

    status, data = _call({"text": "status"}, method="GET")
    assert status == 405
    assert data["error"] == "method not allowed"
