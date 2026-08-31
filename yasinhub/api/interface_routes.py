"""HTTP routes for the Yasin Interface conversational surface (#105).

PWA / CLI clients post natural-language messages here.
All control still goes through the Interface Engine → Control API.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from ..interface.adapters import ChannelMessage, get_channel_adapter
from ..interface.response import InterfaceResponse

logger = logging.getLogger(__name__)


def _response_payload(resp: InterfaceResponse) -> dict:
    return {
        "success": resp.success,
        "answer": resp.answer,
        "intent_kind": resp.intent_kind,
        "confirmation_required": resp.confirmation_required,
        "confirmation_token": resp.confirmation_token,
        "confirmation_summary": resp.confirmation_summary,
        "suggested_next_actions": list(resp.suggested_next_actions or []),
        "execution_refs": list(resp.execution_refs or []),
        "confidence": resp.confidence,
        "error": resp.error,
        "uncertainty": resp.uncertainty,
    }


def handle_interface_routes(
    clean_path: str,
    method: str,
    path: str,
    headers,
    rfile,
    send_json: Callable[..., Any],
) -> bool:
    if not clean_path.startswith("/api/interface"):
        return False

    if clean_path in ("/api/interface/health", "/api/interface") and method == "GET":
        send_json({"ok": True, "service": "yasin-interface", "channels": ["pwa", "cli", "slack"]})
        return True

    if clean_path not in ("/api/interface/chat", "/api/interface/message"):
        send_json({"success": False, "error": "not_found"}, status=404)
        return True

    if method != "POST":
        send_json({"success": False, "error": "method_not_allowed"}, status=405)
        return True

    try:
        length = int(headers.get("Content-Length", 0) or 0)
    except Exception:
        length = 0
    raw = rfile.read(length) if length > 0 and rfile is not None else b""
    body: dict = {}
    if raw:
        try:
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                body = data
            else:
                send_json({"success": False, "error": "malformed_json"}, status=400)
                return True
        except Exception:
            send_json({"success": False, "error": "malformed_json"}, status=400)
            return True

    text = (body.get("text") or body.get("message") or "").strip()
    if not text:
        send_json({"success": False, "error": "missing_text"}, status=400)
        return True

    channel = (body.get("channel") or "pwa").strip().lower()
    if channel not in ("pwa", "cli", "http"):
        channel = "pwa"

    actor = (
        body.get("actor")
        or body.get("yasin_user_id")
        or (headers.get("X-Actor") if hasattr(headers, "get") else None)
        or "pwa-user"
    )
    thread_id = body.get("thread_id") or body.get("session_key") or body.get("conversation_id")
    if not thread_id and body.get("client_session_id"):
        thread_id = f"pwa:{body['client_session_id']}"

    try:
        adapter = get_channel_adapter(channel)
        resp = adapter.handle(
            ChannelMessage(
                text=text,
                channel=channel,
                source=channel,
                actor=str(actor),
                yasin_user_id=str(body.get("yasin_user_id") or actor),
                thread_id=str(thread_id) if thread_id else None,
                channel_id=body.get("channel_id"),
                require_mention=False,
            )
        )
        send_json(_response_payload(resp))
        return True
    except Exception as exc:
        logger.warning("interface_chat_failed error=%s", type(exc).__name__)
        send_json(
            {
                "success": False,
                "error": "interface_error",
                "answer": "Yasin Interface encountered an error; Control Plane remains healthy.",
            },
            status=500,
        )
        return True
