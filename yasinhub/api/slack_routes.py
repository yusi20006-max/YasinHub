"""HTTP handlers for Slack ingress (Events API, slash commands, interactions)."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs

from ..integrations.slack import (
    SlackAdapter,
    SlackVerificationError,
    get_slack_adapter,
    is_slack_enabled,
)
from ..integrations.slack.events import SlackEventType

logger = logging.getLogger(__name__)


def _parse_body(headers, rfile) -> tuple:
    try:
        length = int(headers.get("Content-Length", 0) or 0)
    except Exception:
        length = 0
    raw = rfile.read(length) if length > 0 and rfile is not None else b""
    content_type = ""
    for k, v in headers.items():
        if k.lower() == "content-type":
            content_type = (v or "").lower()
            break

    payload: Dict[str, Any] = {}
    if not raw:
        return raw, payload

    if "application/json" in content_type:
        try:
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                payload = data
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"__malformed__": True}
    elif "application/x-www-form-urlencoded" in content_type:
        try:
            form = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
            payload = {k: (v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in form.items()}
        except UnicodeDecodeError:
            payload = {"__malformed__": True}
    else:
        try:
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                payload = data
        except Exception:
            try:
                form = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
                payload = {k: (v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in form.items()}
            except Exception:
                payload = {"__malformed__": True}

    return raw, payload


def handle_slack_routes(
    clean_path: str,
    method: str,
    path: str,
    headers,
    rfile,
    send_json: Callable[..., Any],
    *,
    adapter: Optional[SlackAdapter] = None,
) -> bool:
    """
    Handle Slack-related HTTP routes. Returns True if the request was consumed.

    Routes:
      POST /api/integrations/slack/events
      POST /api/integrations/slack/commands
      POST /api/integrations/slack/interactions
      GET  /api/integrations/slack/health
    """
    if not clean_path.startswith("/api/integrations/slack"):
        return False

    slack = adapter if adapter is not None else get_slack_adapter()

    if method == "GET" and clean_path in (
        "/api/integrations/slack/health",
        "/api/integrations/slack",
    ):
        send_json(slack.health())
        return True

    if method != "POST":
        send_json({"ok": False, "error": "method_not_allowed"}, status=405)
        return True

    if clean_path not in (
        "/api/integrations/slack/events",
        "/api/integrations/slack/commands",
        "/api/integrations/slack/interactions",
    ):
        send_json({"ok": False, "error": "not_found"}, status=404)
        return True

    if not is_slack_enabled(slack.config):
        send_json({"ok": False, "error": "slack_disabled"}, status=503)
        return True

    raw, payload = _parse_body(headers, rfile)
    header_map = {str(k): str(v) for k, v in headers.items()}

    try:
        slack.verify_request(raw, header_map)
    except SlackVerificationError as exc:
        logger.warning("slack_verification_failed reason=%s", exc.reason)
        send_json({"ok": False, "error": "unauthorized"}, status=401)
        return True

    if payload.get("__malformed__"):
        send_json({"ok": False, "error": "malformed_payload"}, status=400)
        return True

    event = slack.normalize(payload)

    if event.event_type == SlackEventType.URL_VERIFICATION:
        result = slack.handle_url_verification(event)
        send_json(result)
        return True

    # Slash commands (#71)
    if event.event_type == SlackEventType.SLASH_COMMAND or clean_path.endswith("/commands"):
        if not slack.config.feature_commands:
            send_json({"ok": False, "error": "commands_disabled"}, status=503)
            return True
        from ..integrations.slack.commands import CommandDispatcher
        dispatcher = CommandDispatcher()
        result = dispatcher.dispatch(event)
        send_json(
            {
                "ok": result.ok,
                "response_type": "ephemeral",
                "text": result.text,
                "request_id": event.request_id,
            },
            status=200,
        )
        return True

    logger.info(
        "slack_event_accepted type=%s request_id=%s",
        event.event_type.value,
        event.request_id,
    )
    send_json(
        {
            "ok": True,
            "request_id": event.request_id,
            "event_type": event.event_type.value,
            "accepted": True,
        }
    )
    return True
