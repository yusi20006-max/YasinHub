"""
Slack Adapter — the only boundary between Slack and YasinHub.

Inbound: verify → normalize → hand off to YasinHub control surfaces.
Outbound: format Yasin events → Slack API (best-effort).

Never calls Yasin-Agent directly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .client import BaseSlackClient, NullSlackClient, SlackMessageResult, build_slack_client
from .config import SlackConfig, is_slack_enabled, load_slack_config
from .events import SlackInboundEvent, normalize_slack_event
from .verification import SlackVerificationError, verify_slack_request

logger = logging.getLogger(__name__)


class SlackAdapter:
    """
    Facade for Slack integration.

    Construction is cheap; credentials are read from config at call time
    so the adapter can be instantiated even when Slack is disabled.
    """

    def __init__(
        self,
        config: Optional[SlackConfig] = None,
        client: Optional[BaseSlackClient] = None,
    ) -> None:
        self._config = config if config is not None else load_slack_config()
        if client is not None:
            self._client = client
        elif is_slack_enabled(self._config):
            self._client = build_slack_client(self._config.bot_token)
        else:
            self._client = NullSlackClient()

    @property
    def config(self) -> SlackConfig:
        return self._config

    @property
    def enabled(self) -> bool:
        return is_slack_enabled(self._config)

    def verify_request(
        self,
        body: bytes,
        headers: Dict[str, str],
        *,
        now: Optional[float] = None,
    ) -> None:
        """Raise SlackVerificationError if the request is not authentic."""
        if not self._config.signing_secret:
            raise SlackVerificationError("missing_signing_secret")
        verify_slack_request(
            body=body,
            headers=headers,
            signing_secret=self._config.signing_secret,
            max_age_seconds=self._config.request_timestamp_max_age_seconds,
            now=now,
        )

    def normalize(self, payload: Dict[str, Any], *, content_type: Optional[str] = None) -> SlackInboundEvent:
        return normalize_slack_event(payload, content_type=content_type)

    def handle_url_verification(self, event: SlackInboundEvent) -> Dict[str, Any]:
        if event.challenge:
            return {"challenge": event.challenge}
        return {"ok": False, "error": "missing_challenge"}

    def post_message(
        self,
        channel: str,
        text: str,
        *,
        thread_ts: Optional[str] = None,
        blocks: Optional[list] = None,
    ) -> SlackMessageResult:
        """Best-effort outbound message. Never raises into the execution path."""
        if not self.enabled:
            return SlackMessageResult(ok=False, error="slack_disabled")
        try:
            return self._client.post_message(
                channel,
                text,
                thread_ts=thread_ts,
                blocks=blocks,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("slack_post_message_failed error=%s", type(exc).__name__)
            return SlackMessageResult(ok=False, error=str(exc))

    def health(self) -> Dict[str, Any]:
        base = self._config.safe_dict()
        if not self.enabled:
            base["client"] = {"enabled": False, "reachable": False}
            return base
        try:
            base["client"] = self._client.health()
        except Exception as exc:  # pragma: no cover
            base["client"] = {"enabled": True, "reachable": False, "error": type(exc).__name__}
        return base


_default_adapter: Optional[SlackAdapter] = None


def get_slack_adapter() -> SlackAdapter:
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = SlackAdapter()
    return _default_adapter


def set_slack_adapter(adapter: Optional[SlackAdapter]) -> None:
    """Override the process-wide adapter (tests / DI)."""
    global _default_adapter
    _default_adapter = adapter
