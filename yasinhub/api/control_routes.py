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

    # Observability / reconciliation (#83)
    if clean_path in (
        "/v1/control/reconcile",
        "/api/control/reconcile",
        "/v1/reconciliation",
        "/api/reconciliation",
    ):
        from ..execution.reconciliation import get_reconciliation_engine

        engine = get_reconciliation_engine()
        if method == "GET":
            last = engine.last_report()
            payload = {
                "health": engine.health_snapshot(),
                "last_report": last.as_dict() if last else None,
            }
            send_json(payload)
            return True
        if method == "POST":
            body = read_json_body(headers, rfile)
            if body.get("__malformed__"):
                send_json({"success": False, "error": "malformed JSON"}, status=400)
                return True
            mode = str(body.get("mode") or "report").lower()
            actor = str(
                body.get("actor")
                or (headers.get("X-Actor") if hasattr(headers, "get") else None)
                or "system"
            )
            source = str(body.get("source") or "http-api")
            event_id = body.get("control_event_id") or body.get("idempotency_key")
            report = engine.reconcile(
                mode=mode,
                actor=actor,
                source=source,
                control_event_id=event_id,
            )
            send_json({"success": True, "report": report.as_dict()})
            return True
        send_json({"success": False, "error": "method not allowed"}, status=405)
        return True

    if clean_path in (
        "/v1/control/readiness",
        "/api/control/readiness",
        "/v1/readiness",
        "/api/readiness",
    ) and method == "GET":
        from ..execution.reconciliation import get_reconciliation_engine

        send_json(get_reconciliation_engine().health_snapshot())
        return True

    return False
