"""HTTP adapter for the channel-neutral Yasin Interface.

The PWA is a thin transport adapter. Conversation state, intent parsing,
context gathering, confirmation, policy, audit, and Control API execution
remain owned by the existing interface/control boundaries.
"""

from __future__ import annotations

from typing import Any, Callable

from ..interface.adapters import ChannelMessage, PWAChannelAdapter
from .control_routes import read_json_body

MAX_INTERFACE_TEXT = 2000


def handle_interface_routes(
    clean_path: str,
    method: str,
    path: str,
    headers,
    rfile,
    send_json: Callable[..., Any],
) -> bool:
    if clean_path not in ("/api/interface", "/v1/interface"):
        return False

    if method != "POST":
        send_json({"success": False, "error": "method not allowed"}, status=405)
        return True

    body = read_json_body(headers, rfile)
    if body.get("__malformed__"):
        send_json({"success": False, "error": "malformed JSON"}, status=400)
        return True

    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        send_json({"success": False, "error": "'text' must be a non-empty string"}, status=400)
        return True
    if len(text) > MAX_INTERFACE_TEXT:
        send_json(
            {"success": False, "error": f"'text' exceeds {MAX_INTERFACE_TEXT} characters"},
            status=400,
        )
        return True

    actor = None
    if hasattr(headers, "get"):
        actor = headers.get("X-Actor")
    actor = actor or body.get("actor") or "pwa-user"

    thread_id = body.get("thread_id")
    if thread_id is not None and not isinstance(thread_id, str):
        send_json({"success": False, "error": "'thread_id' must be a string"}, status=400)
        return True
    channel_id = body.get("channel_id")
    if channel_id is not None and not isinstance(channel_id, str):
        send_json({"success": False, "error": "'channel_id' must be a string"}, status=400)
        return True

    adapter = PWAChannelAdapter()
    response = adapter.handle(
        ChannelMessage(
            text=text,
            channel="pwa",
            source="pwa",
            actor=str(actor),
            yasin_user_id=str(body.get("yasin_user_id") or actor),
            thread_id=thread_id,
            channel_id=channel_id,
            metadata={"transport": "http"},
        )
    )
    send_json(response.as_dict())
    return True
