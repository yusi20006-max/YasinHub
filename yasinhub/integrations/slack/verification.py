"""
Slack request signature verification (HMAC-SHA256).

Rejects invalid signatures and replayed timestamps outside the allowed window.
Never logs the signing secret or full payload body.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Mapping, Optional, Union

logger = logging.getLogger(__name__)


class SlackVerificationError(Exception):
    """Raised when a Slack request fails authenticity or replay checks."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _get_header(headers: Mapping[str, str], name: str) -> Optional[str]:
    """Case-insensitive header lookup."""
    lower = name.lower()
    for key, value in headers.items():
        if key.lower() == lower:
            return value
    return None


def verify_slack_request(
    *,
    body: Union[str, bytes],
    headers: Mapping[str, str],
    signing_secret: str,
    max_age_seconds: int = 300,
    now: Optional[float] = None,
) -> None:
    """
    Verify Slack signature headers.

    Required headers:
      X-Slack-Signature: v0=<hex>
      X-Slack-Request-Timestamp: <unix seconds>

    Raises SlackVerificationError on failure.
    """
    if not signing_secret:
        raise SlackVerificationError("missing_signing_secret")

    timestamp_raw = _get_header(headers, "X-Slack-Request-Timestamp")
    signature = _get_header(headers, "X-Slack-Signature")

    if not timestamp_raw or not signature:
        raise SlackVerificationError("missing_signature_headers")

    try:
        ts = int(timestamp_raw)
    except (TypeError, ValueError):
        raise SlackVerificationError("invalid_timestamp")

    current = now if now is not None else time.time()
    if abs(current - ts) > max_age_seconds:
        raise SlackVerificationError("timestamp_out_of_range")

    if isinstance(body, bytes):
        body_bytes = body
    else:
        body_bytes = body.encode("utf-8")

    basestring = b"v0:" + str(ts).encode("utf-8") + b":" + body_bytes
    digest = hmac.new(
        signing_secret.encode("utf-8"),
        basestring,
        hashlib.sha256,
    ).hexdigest()
    expected = "v0=" + digest

    if not hmac.compare_digest(expected, signature):
        # Do not log body or secret
        logger.warning("slack_signature_mismatch")
        raise SlackVerificationError("invalid_signature")
