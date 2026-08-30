"""
Inbound Slack event normalization.

Slack-specific payloads are converted into a stable internal envelope so
core YasinHub code does not depend on Slack wire formats.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class SlackEventType(str, Enum):
    URL_VERIFICATION = "url_verification"
    EVENT_CALLBACK = "event_callback"
    SLASH_COMMAND = "slash_command"
    INTERACTIVE = "interactive"
    UNKNOWN = "unknown"


@dataclass
class SlackInboundEvent:
    """Normalized inbound Slack event (Yasin domain envelope)."""

    source: str = "slack"
    event_type: SlackEventType = SlackEventType.UNKNOWN
    request_id: str = field(default_factory=lambda: f"slack-{uuid.uuid4().hex[:16]}")
    correlation_id: Optional[str] = None
    slack_user_id: Optional[str] = None
    slack_team_id: Optional[str] = None
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    text: Optional[str] = None
    command: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    received_at: float = field(default_factory=time.time)
    action_id: Optional[str] = None
    action_value: Optional[str] = None
    trigger_id: Optional[str] = None
    response_url: Optional[str] = None
    challenge: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "event_type": self.event_type.value,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "slack_user_id": self.slack_user_id,
            "slack_team_id": self.slack_team_id,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "text": self.text,
            "command": self.command,
            "action_id": self.action_id,
            "action_value": self.action_value,
            "trigger_id": self.trigger_id,
            "received_at": self.received_at,
        }


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def normalize_slack_event(
    payload: Dict[str, Any],
    *,
    content_type: Optional[str] = None,
) -> SlackInboundEvent:
    """
    Convert a parsed Slack request body into SlackInboundEvent.

    Supports:
    - Events API JSON (url_verification, event_callback)
    - Slash commands (application/x-www-form-urlencoded already parsed to dict)
    - Interactive components (payload JSON string under 'payload' key)
    """
    if not isinstance(payload, dict):
        return SlackInboundEvent(event_type=SlackEventType.UNKNOWN)

    if payload.get("type") == "url_verification":
        return SlackInboundEvent(
            event_type=SlackEventType.URL_VERIFICATION,
            challenge=_safe_str(payload.get("challenge")),
            slack_team_id=_safe_str(payload.get("team_id")),
            raw_payload={"type": "url_verification"},
        )

    if payload.get("type") == "event_callback":
        event = payload.get("event") or {}
        if not isinstance(event, dict):
            event = {}
        return SlackInboundEvent(
            event_type=SlackEventType.EVENT_CALLBACK,
            slack_user_id=_safe_str(event.get("user") or event.get("user_id")),
            slack_team_id=_safe_str(payload.get("team_id")),
            channel_id=_safe_str(event.get("channel") or event.get("channel_id")),
            text=_safe_str(event.get("text")),
            correlation_id=_safe_str(payload.get("event_id")),
            raw_payload={"type": "event_callback", "event_type": event.get("type")},
        )

    if "payload" in payload and isinstance(payload.get("payload"), str):
        import json

        try:
            nested = json.loads(payload["payload"])
            if isinstance(nested, dict):
                payload = nested
        except (json.JSONDecodeError, TypeError):
            pass

    if payload.get("type") in ("block_actions", "interactive_message", "message_action"):
        actions = payload.get("actions") or []
        action = actions[0] if actions and isinstance(actions[0], dict) else {}
        user = payload.get("user") or {}
        channel = payload.get("channel") or {}
        return SlackInboundEvent(
            event_type=SlackEventType.INTERACTIVE,
            slack_user_id=_safe_str(user.get("id") if isinstance(user, dict) else None),
            slack_team_id=_safe_str(
                (payload.get("team") or {}).get("id") if isinstance(payload.get("team"), dict) else None
            ),
            channel_id=_safe_str(channel.get("id") if isinstance(channel, dict) else None),
            channel_name=_safe_str(channel.get("name") if isinstance(channel, dict) else None),
            action_id=_safe_str(action.get("action_id") or action.get("name")),
            action_value=_safe_str(action.get("value")),
            trigger_id=_safe_str(payload.get("trigger_id")),
            response_url=_safe_str(payload.get("response_url")),
            correlation_id=_safe_str(payload.get("trigger_id")),
            raw_payload={"type": payload.get("type"), "action_id": action.get("action_id")},
        )

    if "command" in payload or payload.get("type") == "slash_command":
        return SlackInboundEvent(
            event_type=SlackEventType.SLASH_COMMAND,
            command=_safe_str(payload.get("command")),
            text=_safe_str(payload.get("text")),
            slack_user_id=_safe_str(payload.get("user_id")),
            slack_team_id=_safe_str(payload.get("team_id")),
            channel_id=_safe_str(payload.get("channel_id")),
            channel_name=_safe_str(payload.get("channel_name")),
            response_url=_safe_str(payload.get("response_url")),
            trigger_id=_safe_str(payload.get("trigger_id")),
            correlation_id=_safe_str(payload.get("trigger_id")),
            raw_payload={"command": payload.get("command")},
        )

    return SlackInboundEvent(
        event_type=SlackEventType.UNKNOWN,
        raw_payload={"keys": list(payload.keys())[:20]},
    )
