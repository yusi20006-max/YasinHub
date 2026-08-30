"""Tests for Slack Integration Foundation (#70)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Dict

import pytest

from yasinhub.integrations.slack.config import SlackConfig, is_slack_enabled, load_slack_config
from yasinhub.integrations.slack.verification import (
    SlackVerificationError,
    verify_slack_request,
)
from yasinhub.integrations.slack.events import (
    SlackEventType,
    normalize_slack_event,
)
from yasinhub.integrations.slack.client import (
    NullSlackClient,
)
from yasinhub.integrations.slack.adapter import SlackAdapter
from yasinhub.api.slack_routes import handle_slack_routes


def _sign(secret: str, body: bytes, ts: int) -> str:
    basestring = b"v0:" + str(ts).encode() + b":" + body
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return "v0=" + digest


class TestSlackConfig:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("YASIN_SLACK_ENABLED", raising=False)
        monkeypatch.delenv("YASIN_SLACK_BOT_TOKEN", raising=False)
        monkeypatch.delenv("YASIN_SLACK_SIGNING_SECRET", raising=False)
        cfg = load_slack_config()
        assert cfg.enabled is False
        assert is_slack_enabled(cfg) is False

    def test_auto_enable_with_credentials(self, monkeypatch):
        monkeypatch.setenv("YASIN_SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("YASIN_SLACK_SIGNING_SECRET", "sec")
        monkeypatch.delenv("YASIN_SLACK_ENABLED", raising=False)
        cfg = load_slack_config()
        assert cfg.enabled is True
        assert cfg.has_credentials() is True

    def test_explicit_enable_without_credentials_stays_disabled(self, monkeypatch):
        monkeypatch.setenv("YASIN_SLACK_ENABLED", "true")
        monkeypatch.delenv("YASIN_SLACK_BOT_TOKEN", raising=False)
        monkeypatch.delenv("YASIN_SLACK_SIGNING_SECRET", raising=False)
        cfg = load_slack_config()
        assert cfg.enabled is False

    def test_safe_dict_redacts_secrets(self):
        cfg = SlackConfig(
            enabled=True,
            bot_token="xoxb-secret",
            signing_secret="super-secret",
        )
        safe = cfg.safe_dict()
        assert "xoxb-secret" not in str(safe)
        assert "super-secret" not in str(safe)
        assert safe["has_bot_token"] is True
        assert safe["has_signing_secret"] is True


class TestVerification:
    def test_valid_signature(self):
        secret = "signing-secret"
        body = b'{"type":"url_verification"}'
        ts = int(time.time())
        headers = {
            "X-Slack-Request-Timestamp": str(ts),
            "X-Slack-Signature": _sign(secret, body, ts),
        }
        verify_slack_request(body=body, headers=headers, signing_secret=secret, now=float(ts))

    def test_invalid_signature(self):
        secret = "signing-secret"
        body = b'{"type":"event_callback"}'
        ts = int(time.time())
        headers = {
            "X-Slack-Request-Timestamp": str(ts),
            "X-Slack-Signature": "v0=deadbeef",
        }
        with pytest.raises(SlackVerificationError) as exc:
            verify_slack_request(body=body, headers=headers, signing_secret=secret, now=float(ts))
        assert exc.value.reason == "invalid_signature"

    def test_replay_rejected(self):
        secret = "signing-secret"
        body = b"{}"
        ts = int(time.time()) - 10_000
        headers = {
            "X-Slack-Request-Timestamp": str(ts),
            "X-Slack-Signature": _sign(secret, body, ts),
        }
        with pytest.raises(SlackVerificationError) as exc:
            verify_slack_request(
                body=body,
                headers=headers,
                signing_secret=secret,
                max_age_seconds=300,
                now=time.time(),
            )
        assert exc.value.reason == "timestamp_out_of_range"

    def test_missing_headers(self):
        with pytest.raises(SlackVerificationError) as exc:
            verify_slack_request(body=b"{}", headers={}, signing_secret="s")
        assert exc.value.reason == "missing_signature_headers"

    def test_missing_secret(self):
        with pytest.raises(SlackVerificationError) as exc:
            verify_slack_request(body=b"{}", headers={"X-Slack-Signature": "v0=x"}, signing_secret="")
        assert exc.value.reason == "missing_signing_secret"


class TestNormalize:
    def test_url_verification(self):
        event = normalize_slack_event({"type": "url_verification", "challenge": "abc123"})
        assert event.event_type == SlackEventType.URL_VERIFICATION
        assert event.challenge == "abc123"

    def test_slash_command(self):
        event = normalize_slack_event(
            {
                "command": "/status",
                "text": "",
                "user_id": "U123",
                "team_id": "T1",
                "channel_id": "C1",
            }
        )
        assert event.event_type == SlackEventType.SLASH_COMMAND
        assert event.command == "/status"
        assert event.slack_user_id == "U123"

    def test_event_callback(self):
        event = normalize_slack_event(
            {
                "type": "event_callback",
                "team_id": "T9",
                "event_id": "Ev1",
                "event": {"type": "message", "user": "U9", "channel": "C9", "text": "hi"},
            }
        )
        assert event.event_type == SlackEventType.EVENT_CALLBACK
        assert event.slack_user_id == "U9"
        assert event.correlation_id == "Ev1"

    def test_interactive_block_actions(self):
        event = normalize_slack_event(
            {
                "type": "block_actions",
                "user": {"id": "U1"},
                "team": {"id": "T1"},
                "channel": {"id": "C1", "name": "yasin"},
                "actions": [{"action_id": "cancel", "value": "exec_1"}],
                "trigger_id": "trig",
            }
        )
        assert event.event_type == SlackEventType.INTERACTIVE
        assert event.action_id == "cancel"
        assert event.action_value == "exec_1"

    def test_unknown(self):
        event = normalize_slack_event({"foo": "bar"})
        assert event.event_type == SlackEventType.UNKNOWN


class TestNullClient:
    def test_post_returns_disabled(self):
        client = NullSlackClient()
        result = client.post_message("#yasin", "hello")
        assert result.ok is False
        assert result.error == "slack_disabled"


class TestSlackAdapter:
    def test_disabled_adapter_post_is_safe(self):
        cfg = SlackConfig(enabled=False)
        adapter = SlackAdapter(config=cfg, client=NullSlackClient())
        assert adapter.enabled is False
        result = adapter.post_message("#yasin", "x")
        assert result.ok is False

    def test_verify_and_normalize_flow(self):
        secret = "test-secret"
        cfg = SlackConfig(enabled=True, bot_token="xoxb-t", signing_secret=secret)
        adapter = SlackAdapter(config=cfg, client=NullSlackClient())
        body = json.dumps({"type": "url_verification", "challenge": "ch"}).encode()
        ts = int(time.time())
        headers = {
            "X-Slack-Request-Timestamp": str(ts),
            "X-Slack-Signature": _sign(secret, body, ts),
            "Content-Type": "application/json",
        }
        adapter.verify_request(body, headers, now=float(ts))
        event = adapter.normalize(json.loads(body))
        assert event.challenge == "ch"
        assert adapter.handle_url_verification(event) == {"challenge": "ch"}

    def test_health_safe(self):
        cfg = SlackConfig(enabled=True, bot_token="xoxb-t", signing_secret="s")
        adapter = SlackAdapter(config=cfg, client=NullSlackClient())
        h = adapter.health()
        assert "xoxb-t" not in str(h)
        assert h["has_bot_token"] is True
        assert "signing_secret" not in h or h.get("signing_secret") is None


class _FakeRFile:
    def __init__(self, data: bytes):
        self._data = data

    def read(self, n: int) -> bytes:
        return self._data[:n]


def _send_json_collector():
    captured = {}

    def send_json(data, status: int = 200):
        captured["data"] = data
        captured["status"] = status

    return send_json, captured


class TestSlackRoutes:
    def _enabled_adapter(self, secret: str = "sec") -> SlackAdapter:
        cfg = SlackConfig(
            enabled=True,
            bot_token="xoxb-test",
            signing_secret=secret,
        )
        return SlackAdapter(config=cfg, client=NullSlackClient())

    def test_health_when_disabled(self):
        cfg = SlackConfig(enabled=False)
        adapter = SlackAdapter(config=cfg, client=NullSlackClient())
        send_json, captured = _send_json_collector()
        handled = handle_slack_routes(
            "/api/integrations/slack/health",
            "GET",
            "/api/integrations/slack/health",
            {},
            None,
            send_json,
            adapter=adapter,
        )
        assert handled is True
        assert captured["data"]["enabled"] is False

    def test_events_rejects_bad_signature(self):
        adapter = self._enabled_adapter()
        body = b'{"type":"event_callback"}'
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "X-Slack-Request-Timestamp": str(int(time.time())),
            "X-Slack-Signature": "v0=bad",
        }
        send_json, captured = _send_json_collector()
        handled = handle_slack_routes(
            "/api/integrations/slack/events",
            "POST",
            "/api/integrations/slack/events",
            headers,
            _FakeRFile(body),
            send_json,
            adapter=adapter,
        )
        assert handled is True
        assert captured["status"] == 401

    def test_url_verification_success(self):
        secret = "sec"
        adapter = self._enabled_adapter(secret)
        payload = {"type": "url_verification", "challenge": "challenge-token"}
        body = json.dumps(payload).encode()
        ts = int(time.time())
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "X-Slack-Request-Timestamp": str(ts),
            "X-Slack-Signature": _sign(secret, body, ts),
        }
        send_json, captured = _send_json_collector()
        handled = handle_slack_routes(
            "/api/integrations/slack/events",
            "POST",
            "/api/integrations/slack/events",
            headers,
            _FakeRFile(body),
            send_json,
            adapter=adapter,
        )
        assert handled is True
        assert captured["data"]["challenge"] == "challenge-token"

    def test_disabled_returns_503(self):
        adapter = SlackAdapter(config=SlackConfig(enabled=False), client=NullSlackClient())
        send_json, captured = _send_json_collector()
        handled = handle_slack_routes(
            "/api/integrations/slack/events",
            "POST",
            "/api/integrations/slack/events",
            {"Content-Length": "2"},
            _FakeRFile(b"{}"),
            send_json,
            adapter=adapter,
        )
        assert handled is True
        assert captured["status"] == 503

    def test_unrelated_path_not_handled(self):
        send_json, _ = _send_json_collector()
        handled = handle_slack_routes(
            "/api/other",
            "POST",
            "/api/other",
            {},
            None,
            send_json,
        )
        assert handled is False
