"""Slack bridge for @Yasin natural-language interface (#96/#99)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .adapters import ChannelMessage, SlackChannelAdapter
from .parser import is_yasin_addressed
from .response import InterfaceResponse

logger = logging.getLogger(__name__)


def handle_slack_message(
    text: str,
    *,
    slack_user_id: Optional[str] = None,
    yasin_user_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
    event_ts: Optional[str] = None,
    bot_user_id: Optional[str] = None,
    identity_role: Optional[str] = None,
) -> InterfaceResponse:
    if not is_yasin_addressed(text, bot_user_id=bot_user_id):
        return InterfaceResponse(answer="", success=False, error="not_addressed")

    thread_id = thread_ts or event_ts
    adapter = SlackChannelAdapter()
    return adapter.handle(
        ChannelMessage(
            text=text,
            channel="slack",
            source="slack",
            actor=yasin_user_id or slack_user_id or "anonymous",
            yasin_user_id=yasin_user_id,
            slack_user_id=slack_user_id,
            thread_id=thread_id,
            channel_id=channel_id,
            bot_user_id=bot_user_id,
            require_mention=True,
        )
    )


def handle_slack_confirmation(
    *,
    action_id: str,
    token: str,
    slack_user_id: Optional[str] = None,
    yasin_user_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> InterfaceResponse:
    """Process Block Kit Confirm/Cancel. Button payload is NOT authorization."""
    actor = yasin_user_id or slack_user_id or "anonymous"
    adapter = SlackChannelAdapter()
    if action_id == "yasin_confirm":
        text = f"@Yasin confirm {token}"
    elif action_id == "yasin_cancel":
        text = "@Yasin cancel control"
    else:
        return InterfaceResponse(answer="Unknown confirmation action.", success=False, error="unknown_action")
    return adapter.handle(
        ChannelMessage(
            text=text,
            channel="slack",
            source="slack",
            actor=actor,
            yasin_user_id=yasin_user_id,
            slack_user_id=slack_user_id,
            thread_id=thread_ts,
            channel_id=channel_id,
            require_mention=True,
        )
    )


def render_slack_response(resp: InterfaceResponse) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "text": resp.to_slack_text() if resp.answer or resp.confirmation_required else (resp.error or "No response."),
        "confirmation_required": resp.confirmation_required,
        "confirmation_token": resp.confirmation_token,
        "success": resp.success,
    }
    if resp.confirmation_required and resp.confirmation_token:
        out["blocks"] = resp.to_slack_blocks()
    return out
