"""HTTP adapter for the channel-neutral Yasin Interface.

The PWA is a thin transport adapter. Conversation state, intent parsing,
context gathering, confirmation, policy, audit, and Control API execution
remain owned by the existing interface/control boundaries.

Authentication (#109) establishes identity for HTTP/PWA. Authorization
remains with Policy / Control API.
"""

from __future__ import annotations

from typing import Any, Callable

from ..auth import AuthError, authenticate_http
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

    body_actor = None
    if hasattr(headers, "get"):
        body_actor = headers.get("X-Actor")
    body_actor = body_actor or body.get("actor")

    try:
        auth = authenticate_http(headers, body_actor=str(body_actor) if body_actor else None)
    except AuthError as exc:
        send_json(
            {"success": False, "error": exc.message, "code": exc.code},
            status=exc.status,
        )
        return True

    actor = auth.actor
    # Authenticated principal always wins over client-supplied identity fields.
    yasin_user_id = auth.principal.yasin_user_id
    if not auth.authenticated:
        # Soft path (dev/test only): allow optional body yasin_user_id for continuity.
        yasin_user_id = str(body.get("yasin_user_id") or actor)

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
            yasin_user_id=str(yasin_user_id),
            thread_id=thread_id,
            channel_id=channel_id,
            metadata={
                "transport": "http",
                "auth_method": auth.principal.auth_method,
                "auth_mode": auth.mode.value,
                "role": auth.role.value,
                "authenticated": auth.authenticated,
            },
        )
    )
    send_json(response.as_dict())
    return True
