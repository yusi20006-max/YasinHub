"""HTTP route handlers for Execution Observer / Fleet / Control (#50 #51 #52 #54)."""
from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from ..adapters.agent_runtime import IntegrationContext, get_runtime_adapter
from ..auth import AuthError, authenticate_http
from ..execution.policies import get_policy_engine
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


def _authorize_mutation(action: str, target_id: str, body: dict, headers, send_json):
    try:
        auth = authenticate_http(
            headers or {},
            body_actor=str(body.get("actor")) if body.get("actor") else None,
        )
    except AuthError as exc:
        send_json({"success": False, "error": exc.message, "code": exc.code}, status=exc.status)
        return None

    control_event_id = body.get("control_event_id") or body.get("idempotency_key")
    if not control_event_id and hasattr(headers, "get"):
        control_event_id = headers.get("X-Control-Event-ID") or headers.get("X-Idempotency-Key")
    decision = get_policy_engine().authorize_and_record(
        action=action,
        actor=auth.actor,
        source="http-observer",
        execution_id=target_id if action != "fleet_cancel" else None,
        control_event_id=str(control_event_id) if control_event_id else None,
        role=auth.role,
        external_ids={"task_id": target_id} if action == "fleet_cancel" else None,
    )
    if not decision.allowed:
        send_json({
            "success": False,
            "error": decision.reason,
            "policy": decision.policy,
        }, status=403)
        return None

    request_id = (
        body.get("request_id")
        or (headers.get("X-Request-Id") if headers and hasattr(headers, "get") else None)
        or f"req-{__import__('uuid').uuid4().hex[:16]}"
    )
    return IntegrationContext(
        request_id=str(request_id),
        actor=auth.actor,
        source="http-observer",
        metadata={"role": auth.role.value, "auth_method": auth.principal.auth_method},
    )


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
            ctx = _authorize_mutation(action, eid, body, headers, send_json)
            if ctx is None:
                return True
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
        ctx = _authorize_mutation("fleet_cancel", task_id, body, headers, send_json)
        if ctx is None:
            return True
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
