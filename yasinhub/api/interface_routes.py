"""HTTP handlers for Yasin Interface conversational surface (PWA / text).

POST /api/interface/chat → PWAChannelAdapter → Yasin Interface Engine → Control API

No second engine. No Agent bypass. Control API remains the only execution boundary.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable, Dict, Optional

from ..interface.adapters import ChannelMessage, PWAChannelAdapter, get_channel_adapter
from ..interface.engine import get_yasin_interface
from ..interface.response import InterfaceResponse

logger = logging.getLogger(__name__)


def _parse_json_body(headers, rfile) -> Dict[str, Any]:
    try:
        length = int(headers.get("Content-Length", 0) or 0)
    except Exception:
        length = 0
    raw = rfile.read(length) if length > 0 and rfile is not None else b""
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"__malformed__": True}


def _response_payload(resp: InterfaceResponse, *, session_id: Optional[str] = None) -> Dict[str, Any]:
    payload = resp.as_dict()
    if session_id:
        payload["session_id"] = session_id
    # Never leak secrets; engine already redacts, but keep boundary explicit.
    return payload


def handle_interface_routes(
    clean_path: str,
    method: str,
    path: str,
    headers,
    rfile,
    send_json: Callable[..., Any],
) -> bool:
    """Return True if the path was handled."""
    if clean_path != "/api/interface/chat":
        return False

    if method != "POST":
        send_json({"success": False, "error": "method not allowed"}, status=405)
        return True

    body = _parse_json_body(headers, rfile)
    if body.get("__malformed__"):
        send_json({"success": False, "error": "invalid json"}, status=400)
        return True

    text = (body.get("text") or body.get("message") or "").strip()
    if not text:
        send_json({"success": False, "error": "text is required"}, status=400)
        return True

    # Client may pass a session id for continuity; we do not treat it as auth identity.
    client_session_id = (body.get("client_session_id") or body.get("session_id") or "").strip()
    if not client_session_id:
        client_session_id = uuid.uuid4().hex

    # Optional actor hint for confirmation authorization (same as text/Slack path).
    # PWA has no Slack identity mapping; use explicit actor or anonymous.
    actor = (body.get("actor") or body.get("yasin_user_id") or "pwa-user").strip() or "pwa-user"
    yasin_user_id = (body.get("yasin_user_id") or actor).strip() or actor

    try:
        adapter = get_channel_adapter("pwa")
        message = ChannelMessage(
            text=text,
            channel="pwa",
            source="pwa",
            actor=actor,
            yasin_user_id=yasin_user_id,
            thread_id=client_session_id,
            channel_id="pwa",
            require_mention=False,
            metadata={"client_session_id": client_session_id},
        )
        resp = adapter.handle(message)
        payload = _response_payload(resp, session_id=client_session_id)
        send_json({"success": bool(resp.success), **payload})
    except Exception as exc:
        logger.warning("interface_chat_failed error=%s", type(exc).__name__)
        send_json(
            {
                "success": False,
                "error": "interface handling failed",
                "answer": "Request could not be processed; Control Plane remains healthy.",
                "session_id": client_session_id,
            },
            status=500,
        )
    return True
