"""HTTP route handlers for Execution Observer / Fleet / Control (#50 #51 #52)."""
from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from ..observer import get_default_store
from ..observer.execution_store import InvalidTransitionError


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
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"__malformed__": True}


def handle_execution_observer(
    clean_path: str,
    method: str,
    path: str,
    headers,
    rfile,
    send_json: Callable[..., Any],
) -> bool:
    """Return True if request was handled."""
    store = get_default_store()

    if method == "GET" and clean_path == "/api/executions":
        qs = parse_qs(urlparse(path).query)
        items = store.list_executions(
            task_id=(qs.get("task_id") or [None])[0],
            session_id=(qs.get("session_id") or [None])[0],
            status=(qs.get("status") or [None])[0],
        )
        send_json({"count": len(items), "executions": [e.as_dict() for e in items]})
        return True

    if method == "GET" and clean_path.startswith("/api/executions/"):
        parts = [p for p in clean_path.split("/") if p]
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "executions":
            eid = parts[2]
            rec = store.get_execution(eid)
            if rec is None:
                send_json(
                    {"success": False, "error": "unknown execution", "execution_id": eid},
                    status=404,
                )
                return True
            send_json({"execution": rec.as_dict()})
            return True
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "executions" and parts[3] == "events":
            eid = parts[2]
            events = store.list_events(execution_id=eid)
            send_json({
                "execution_id": eid,
                "count": len(events),
                "events": [e.as_dict() for e in events],
            })
            return True

    if method == "GET" and clean_path == "/api/execution-events":
        qs = parse_qs(urlparse(path).query)
        events = store.list_events(
            execution_id=(qs.get("execution_id") or [None])[0],
            task_id=(qs.get("task_id") or [None])[0],
            session_id=(qs.get("session_id") or [None])[0],
            worker_id=(qs.get("worker_id") or [None])[0],
            event_type=(qs.get("event_type") or qs.get("type") or [None])[0],
            limit=(qs.get("limit") or [None])[0],
        )
        send_json({"count": len(events), "events": [e.as_dict() for e in events]})
        return True

    if method == "GET" and clean_path == "/api/fleets":
        fleets = store.list_fleets()
        send_json({"count": len(fleets), "fleets": [f.as_dict() for f in fleets]})
        return True

    if method == "GET" and clean_path.startswith("/api/fleets/"):
        task_id = clean_path[len("/api/fleets/"):].strip("/")
        if not task_id or "/" in task_id:
            send_json({"success": False, "error": "invalid fleet path"}, status=400)
            return True
        fleet = store.get_fleet(task_id)
        if fleet is None:
            send_json(
                {"success": False, "error": "unknown fleet", "task_id": task_id},
                status=404,
            )
            return True
        send_json({"fleet": fleet.as_dict()})
        return True

    if method == "POST" and clean_path.startswith("/api/executions/"):
        parts = [p for p in clean_path.split("/") if p]
        if (
            len(parts) == 4
            and parts[0] == "api"
            and parts[1] == "executions"
            and parts[3] in ("pause", "resume", "cancel")
        ):
            eid = parts[2]
            action = parts[3]
            body = read_json_body(headers, rfile)
            if body.get("__malformed__"):
                send_json({"success": False, "error": "malformed request body"}, status=400)
                return True
            actor = body.get("actor")
            request_id = body.get("request_id") or f"req-{eid[:12]}"
            try:
                if action == "pause":
                    rec = store.pause(eid, actor=actor, request_id=request_id)
                elif action == "resume":
                    rec = store.resume(eid, actor=actor, request_id=request_id)
                else:
                    rec = store.cancel(eid, actor=actor, request_id=request_id)
                send_json({
                    "success": True,
                    "action": action,
                    "execution": rec.as_dict(),
                    "request_id": request_id,
                })
            except KeyError:
                send_json(
                    {
                        "success": False,
                        "error": "unknown execution",
                        "execution_id": eid,
                        "action": action,
                    },
                    status=404,
                )
            except InvalidTransitionError as exc:
                send_json(
                    {
                        "success": False,
                        "error": "invalid transition",
                        "detail": str(exc),
                        "current": exc.current,
                        "target": exc.target,
                        "action": action,
                        "execution_id": eid,
                    },
                    status=409,
                )
            return True

    if method == "POST" and clean_path.startswith("/api/fleets/") and clean_path.endswith("/cancel"):
        task_id = clean_path[len("/api/fleets/"):-len("/cancel")].strip("/")
        if not task_id or "/" in task_id:
            send_json({"success": False, "error": "invalid fleet path"}, status=400)
            return True
        body = read_json_body(headers, rfile)
        if body.get("__malformed__"):
            send_json({"success": False, "error": "malformed request body"}, status=400)
            return True
        try:
            fleet = store.cancel_fleet(
                task_id, actor=body.get("actor"), request_id=body.get("request_id")
            )
            send_json({
                "success": True,
                "action": "cancel",
                "fleet": fleet.as_dict(),
                "request_id": body.get("request_id"),
            })
        except KeyError:
            send_json(
                {"success": False, "error": "unknown fleet", "task_id": task_id},
                status=404,
            )
        return True

    return False
