"""HTTP route handlers for Execution Observer / Fleet / Control (#50 #51 #52 #54)."""
from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from ..adapters.agent_runtime import get_runtime_adapter, resolve_integration_context
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
    adapter = get_runtime_adapter()

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
            # Prefer adapter projection (may sync from Agent)
            try:
                data = adapter.get_execution(eid)
            except Exception:
                data = None
            if data is None:
                rec = store.get_execution(eid)
                if rec is None:
                    send_json(
                        {"success": False, "error": "unknown execution", "execution_id": eid},
                        status=404,
                    )
                    return True
                send_json({"execution": rec.as_dict()})
                return True
            send_json({"execution": data if isinstance(data, dict) else data})
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
            ctx = resolve_integration_context(body, headers=headers)
            try:
                if action == "pause":
                    rec = adapter.pause(eid, context=ctx)
                elif action == "resume":
                    rec = adapter.resume(eid, context=ctx)
                else:
                    rec = adapter.cancel(eid, context=ctx)
                send_json({
                    "success": True,
                    "action": action,
                    "execution": rec if isinstance(rec, dict) else rec,
                    "request_id": ctx.request_id,
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
        ctx = resolve_integration_context(body, headers=headers)
        try:
            fleet = adapter.cancel_fleet(task_id, context=ctx)
            send_json({
                "success": True,
                "action": "cancel",
                "fleet": fleet if isinstance(fleet, dict) else fleet,
                "request_id": ctx.request_id,
            })
        except KeyError:
            send_json(
                {"success": False, "error": "unknown fleet", "task_id": task_id},
                status=404,
            )
        return True

    return False
