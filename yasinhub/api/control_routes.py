"""HTTP routes for the unified YasinHub Control API."""

from __future__ import annotations

import json
from typing import Any, Callable

from ..execution.control_api import ControlRequest, get_control_api


def read_json_body(headers, rfile) -> dict:
    if rfile is None:
        return {}
    try:
        length = int(headers.get("Content-Length", 0) or 0)
    except Exception:
        return {}
    if length <= 0:
        return {}
    raw = rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"__malformed__": True}


def handle_control_api_routes(
    clean_path: str,
    method: str,
    path: str,
    headers,
    rfile,
    send_json: Callable[..., Any],
) -> bool:
    if clean_path in ("/v1/control", "/api/control", "/v1/control/command", "/api/control/command"):
        if method != "POST":
            send_json({"success": False, "error": "method not allowed"}, status=405)
            return True
        body = read_json_body(headers, rfile)
        if body.get("__malformed__"):
            send_json({"success": False, "error": "malformed JSON"}, status=400)
            return True
        if not body.get("actor"):
            # default actor from header if present
            if hasattr(headers, "get"):
                body["actor"] = headers.get("X-Actor") or body.get("actor") or "hub-user"
            else:
                body.setdefault("actor", "hub-user")
        if not body.get("source"):
            body["source"] = "http-api"
        req = ControlRequest.from_dict(body)
        resp = get_control_api().handle(req)
        send_json(resp.as_dict(), status=resp.status_code)
        return True

    if clean_path in ("/v1/control/actions", "/api/control/actions") and method == "GET":
        from ..execution.control_api import SUPPORTED_ACTIONS

        send_json({"actions": list(SUPPORTED_ACTIONS)})
        return True

    return False
