"""HTTP route handlers for external integrations (monday, GitHub)."""

from __future__ import annotations

from typing import Any, Callable


def read_raw_body(headers, rfile) -> bytes:
    if rfile is None:
        return b""
    try:
        length = int(headers.get("Content-Length", 0) or 0)
    except Exception:
        return b""
    if length <= 0:
        return b""
    return rfile.read(length)


def handle_integration_routes(
    clean_path: str,
    method: str,
    path: str,
    headers,
    rfile,
    send_json: Callable[..., Any],
) -> bool:
    """Return True if request was handled."""

    # --- monday ---
    if clean_path in (
        "/v1/integrations/monday/webhook",
        "/api/integrations/monday/webhook",
    ):
        if method != "POST":
            send_json({"success": False, "error": "method not allowed"}, status=405)
            return True
        body = read_raw_body(headers, rfile)
        from ..integrations.monday.webhook import handle_monday_webhook

        status, result = handle_monday_webhook(body, headers=headers)
        send_json(result, status=status)
        return True

    if clean_path in (
        "/v1/integrations/monday/health",
        "/api/integrations/monday/health",
    ):
        if method != "GET":
            send_json({"success": False, "error": "method not allowed"}, status=405)
            return True
        from ..integrations.monday import get_monday_adapter

        send_json(get_monday_adapter().health())
        return True

    if clean_path in (
        "/v1/integrations/monday/sync",
        "/api/integrations/monday/sync",
    ):
        if method not in ("POST", "GET"):
            send_json({"success": False, "error": "method not allowed"}, status=405)
            return True
        from ..integrations.monday import get_monday_adapter

        send_json(get_monday_adapter().sync_status())
        return True

    return False
