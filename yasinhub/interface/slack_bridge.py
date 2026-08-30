"""Slack bridge for @Yasin natural-language interface (#96)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .engine import get_yasin_interface
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
    iface = get_yasin_interface()
    return iface.handle(
        text,
        channel="slack",
        source="slack",
        thread_id=thread_id,
        channel_id=channel_id,
        yasin_user_id=yasin_user_id,
        slack_user_id=slack_user_id,
        actor=yasin_user_id or slack_user_id or "anonymous",
        require_mention=True,
        bot_user_id=bot_user_id,
    )


def render_slack_response(resp: InterfaceResponse) -> Dict[str, Any]:
    return {
        "text": resp.to_slack_text() if resp.answer or resp.confirmation_required else (
            resp.error or "No response."
        ),
        "confirmation_required": resp.confirmation_required,
        "confirmation_token": resp.confirmation_token,
        "success": resp.success,
    }
