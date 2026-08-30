"""monday.com webhook ingress, challenge handling, and verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from .config import MondayConfig, get_monday_config
from .models import MondayNormalizedEvent
from .mapper import normalize_monday_payload

logger = logging.getLogger(__name__)


def verify_monday_challenge(payload: Dict[str, Any]) -> Optional[str]:
    """Handle monday webhook challenge (subscription verification).

    Returns the challenge string if present, else None.
    """
    if not isinstance(payload, dict):
        return None
    # monday sends {"challenge": "..."} on subscription
    challenge = payload.get("challenge")
    if challenge is not None:
        return str(challenge)
    # nested form sometimes used
    event = payload.get("event")
    if isinstance(event, dict) and "challenge" in event:
        return str(event["challenge"])
    return None


def _verify_signature(
    body: bytes,
    signature_header: Optional[str],
    secret: Optional[str],
) -> bool:
    """Verify HMAC signature when a signing secret is configured.

    If no secret is configured, verification is skipped (dev mode) but
    the caller should still treat the request carefully.
    """
    if not secret:
        return True
    if not signature_header:
        return False
    # monday uses various header styles; support common ones
    try:
        expected = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        # header may be "sha256=<hex>" or raw hex
        provided = signature_header.strip()
        if provided.lower().startswith("sha256="):
            provided = provided[7:]
        return hmac.compare_digest(expected, provided)
    except Exception:
        logger.exception("monday signature verification error")
        return False


def handle_monday_webhook(
    body: bytes,
    *,
    headers: Optional[Any] = None,
    config: Optional[MondayConfig] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Process an incoming monday webhook request.

    Returns (http_status, response_dict).

    - Handles challenge
    - Validates payload
    - Verifies signature when secret present
    - Normalizes into MondayNormalizedEvent
    - Does NOT dispatch Agents
    """
    cfg = config or get_monday_config()
    headers = headers or {}

    def _hdr(name: str) -> Optional[str]:
        if hasattr(headers, "get"):
            return headers.get(name) or headers.get(name.lower()) or headers.get(name.upper())
        if isinstance(headers, dict):
            for k, v in headers.items():
                if str(k).lower() == name.lower():
                    return v
        return None

    # Parse JSON
    try:
        if not body:
            return 400, {"success": False, "error": "empty body"}
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            return 400, {"success": False, "error": "payload must be a JSON object"}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, {"success": False, "error": "invalid JSON"}

    # Challenge first (monday subscription handshake)
    challenge = verify_monday_challenge(payload)
    if challenge is not None:
        return 200, {"challenge": challenge}

    # Signature verification
    sig = _hdr("X-Monday-Signature") or _hdr("Authorization") or _hdr("X-Hub-Signature-256")
    if cfg.has_signing_secret() and not _verify_signature(body, sig, cfg.signing_secret):
        logger.warning("monday webhook signature verification failed")
        return 401, {"success": False, "error": "invalid signature"}

    # Normalize
    try:
        events = normalize_monday_payload(payload, config=cfg)
    except ValueError as exc:
        return 400, {"success": False, "error": str(exc)}
    except Exception:
        logger.exception("monday normalize failed")
        return 400, {"success": False, "error": "normalization failed"}

    if not events:
        return 200, {
            "success": True,
            "accepted": 0,
            "message": "no actionable events",
        }

    # Emit / store normalized events via adapter (no Agent dispatch)
    from .adapter import get_monday_adapter

    adapter = get_monday_adapter()
    accepted = []
    for evt in events:
        try:
            adapter.ingest_normalized_event(evt)
            accepted.append(
                {
                    "event_id": evt.event_id,
                    "event_type": evt.event_type,
                    "board_id": evt.board_id,
                    "item_id": evt.item_id,
                    "correlation_id": evt.correlation_id,
                }
            )
        except Exception:
            logger.exception("failed to ingest monday event %s", evt.event_id)

    return 200, {
        "success": True,
        "accepted": len(accepted),
        "events": accepted,
    }
