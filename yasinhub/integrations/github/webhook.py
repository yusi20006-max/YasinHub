"""GitHub webhook ingress with signature verification and normalization."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _get_secret() -> Optional[str]:
    return os.environ.get("YASINHUB_GITHUB_WEBHOOK_SECRET") or os.environ.get("GITHUB_WEBHOOK_SECRET")


def verify_github_signature(body: bytes, signature_header: Optional[str], secret: Optional[str]) -> bool:
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def normalize_github_event(
    event_name: str,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Produce a minimal internal event dict."""
    delivery_id = payload.get("delivery") or str(uuid.uuid4())
    action = payload.get("action")
    repo = (payload.get("repository") or {}).get("full_name") or ""
    pr = payload.get("pull_request") or {}
    check = payload.get("check_run") or {}

    correlation = None
    # Prefer labels / body markers that Hub may have set
    if pr:
        correlation = pr.get("body")  # may contain correlation marker
        head = (pr.get("head") or {}).get("ref") or ""
        if head.startswith("yasin/"):
            correlation = correlation or head

    internal = {
        "event_id": f"gh-{uuid.uuid4().hex[:16]}",
        "event_type": f"github.{event_name}",
        "source": "github",
        "action": action,
        "repository": repo,
        "timestamp": time.time(),
        "correlation_hint": correlation,
        "pr_number": pr.get("number"),
        "pr_state": pr.get("state"),
        "pr_merged": pr.get("merged"),
        "check_name": check.get("name"),
        "check_status": check.get("status"),
        "check_conclusion": check.get("conclusion"),
        "sha": (check.get("head_sha") or (pr.get("head") or {}).get("sha")),
    }
    return internal


def handle_github_webhook(
    body: bytes,
    *,
    headers: Optional[Any] = None,
) -> Tuple[int, Dict[str, Any]]:
    headers = headers or {}

    def _hdr(name: str) -> Optional[str]:
        if hasattr(headers, "get"):
            return headers.get(name) or headers.get(name.lower())
        if isinstance(headers, dict):
            for k, v in headers.items():
                if str(k).lower() == name.lower():
                    return v
        return None

    secret = _get_secret()
    sig = _hdr("X-Hub-Signature-256")
    if secret and not verify_github_signature(body, sig, secret):
        return 401, {"success": False, "error": "invalid signature"}

    try:
        payload = json.loads(body.decode("utf-8") if body else "{}")
        if not isinstance(payload, dict):
            return 400, {"success": False, "error": "invalid payload"}
    except Exception:
        return 400, {"success": False, "error": "invalid JSON"}

    event_name = _hdr("X-GitHub-Event") or payload.get("action") or "unknown"
    if event_name not in (
        "pull_request",
        "pull_request_review",
        "check_run",
        "check_suite",
        "push",
        "status",
        "ping",
    ):
        return 200, {"success": True, "accepted": 0, "message": f"ignored event {event_name}"}

    if event_name == "ping":
        return 200, {"success": True, "message": "pong"}

    internal = normalize_github_event(str(event_name), payload)
    if not internal:
        return 200, {"success": True, "accepted": 0}

    from .adapter import get_github_adapter

    adapter = get_github_adapter()
    accepted = adapter.ingest(internal)

    # Correlate and update execution state when possible
    adapter.apply_to_executions(internal)

    return 200, {
        "success": True,
        "accepted": 1 if accepted else 0,
        "event_type": internal["event_type"],
    }
