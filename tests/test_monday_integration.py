"""Tests for monday.com integration foundation (#64)."""

from __future__ import annotations

import json

import pytest

from yasinhub.integrations.monday import (
    MondayAdapter,
    MondayConfig,
    get_monday_adapter,
    handle_monday_webhook,
    verify_monday_challenge,
)
from yasinhub.integrations.monday.adapter import set_monday_adapter
from yasinhub.integrations.monday.mapper import normalize_monday_payload
from yasinhub.integrations.monday.models import MondayNormalizedEvent


@pytest.fixture(autouse=True)
def clean_adapter():
    set_monday_adapter(None)
    yield
    set_monday_adapter(None)


def test_challenge_handling():
    payload = {"challenge": "abc123challenge"}
    assert verify_monday_challenge(payload) == "abc123challenge"
    assert verify_monday_challenge({"event": {"challenge": "nested"}}) == "nested"
    assert verify_monday_challenge({"type": "create"}) is None


def test_webhook_challenge_response():
    body = json.dumps({"challenge": "xyz"}).encode()
    status, result = handle_monday_webhook(body)
    assert status == 200
    assert result["challenge"] == "xyz"


def test_invalid_json_rejected():
    status, result = handle_monday_webhook(b"not-json")
    assert status == 400
    assert result["success"] is False


def test_empty_body_rejected():
    status, result = handle_monday_webhook(b"")
    assert status == 400


def test_normalize_task_ready():
    payload = {
        "event": {
            "type": "update_column_value",
            "boardId": "12345",
            "pulseId": "67890",
            "pulseName": "Implement feature X",
            "columnValues": {"status": {"text": "Ready"}},
        }
    }
    cfg = MondayConfig(status_ready_values=["Ready"])
    events = normalize_monday_payload(payload, config=cfg)
    assert len(events) == 1
    evt = events[0]
    assert evt.event_type == "task.ready"
    assert evt.board_id == "12345"
    assert evt.item_id == "67890"
    assert evt.correlation_id.startswith("mon-")
    assert evt.name == "Implement feature X"


def test_idempotent_ingest():
    adapter = MondayAdapter()
    evt = MondayNormalizedEvent(
        event_id="evt-1",
        event_type="task.ready",
        board_id="b1",
        item_id="i1",
        correlation_id="corr-1",
    )
    assert adapter.ingest_normalized_event(evt) is True
    assert adapter.ingest_normalized_event(evt) is False
    assert len(adapter.list_events()) == 1


def test_health_endpoint_shape():
    adapter = get_monday_adapter()
    h = adapter.health()
    assert h["service"] == "monday-integration"
    assert "has_credentials" in h
    assert "config" in h
    raw = json.dumps(h)
    # actual secret values must never appear; boolean flags are OK
    assert ": \"tok\"" not in raw
    assert ": \"sec\"" not in raw
    assert "supersecret" not in raw


def test_signature_required_when_configured():
    cfg = MondayConfig(signing_secret="supersecret")
    body = json.dumps(
        {
            "event": {
                "type": "create_pulse",
                "boardId": "1",
                "pulseId": "2",
            }
        }
    ).encode()
    status, result = handle_monday_webhook(body, headers={}, config=cfg)
    assert status == 401
    assert result["error"] == "invalid signature"


def test_valid_webhook_accepted_without_secret():
    body = json.dumps(
        {
            "event": {
                "type": "create_pulse",
                "boardId": "111",
                "pulseId": "222",
                "pulseName": "New task",
            }
        }
    ).encode()
    status, result = handle_monday_webhook(body)
    assert status == 200
    assert result["success"] is True
    assert result["accepted"] >= 1


def test_config_safe_dict_hides_secrets():
    cfg = MondayConfig(api_token="tok_secret_value", signing_secret="sec_secret_value", enabled=True)
    d = cfg.as_safe_dict()
    assert d["has_api_token"] is True
    assert "tok_secret_value" not in str(d)
    assert "sec_secret_value" not in str(d)
