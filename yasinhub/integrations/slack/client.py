"""
Outbound Slack API client abstraction.

Failures are isolated: callers must treat Slack as best-effort.
Never log tokens or full request/response bodies containing secrets.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackClientError(Exception):
    """Outbound Slack API failure (network, auth, or API error)."""

    def __init__(self, message: str, *, status: Optional[int] = None, slack_error: Optional[str] = None):
        self.status = status
        self.slack_error = slack_error
        super().__init__(message)


@dataclass
class SlackMessageResult:
    ok: bool
    channel: Optional[str] = None
    ts: Optional[str] = None
    thread_ts: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class BaseSlackClient(ABC):
    @abstractmethod
    def post_message(
        self,
        channel: str,
        text: str,
        *,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SlackMessageResult:
        ...

    @abstractmethod
    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        *,
        blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> SlackMessageResult:
        ...

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        ...


class NullSlackClient(BaseSlackClient):
    """No-op client used when Slack is disabled or unconfigured."""

    def post_message(
        self,
        channel: str,
        text: str,
        *,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SlackMessageResult:
        return SlackMessageResult(ok=False, error="slack_disabled")

    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        *,
        blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> SlackMessageResult:
        return SlackMessageResult(ok=False, error="slack_disabled")

    def health(self) -> Dict[str, Any]:
        return {"enabled": False, "reachable": False}


class SlackClient(BaseSlackClient):
    """Minimal HTTP Slack Web API client (chat.postMessage / chat.update)."""

    def __init__(self, bot_token: str, *, timeout_seconds: float = 10.0) -> None:
        if not bot_token:
            raise ValueError("bot_token is required")
        self._token = bot_token
        self._timeout = timeout_seconds

    def _request(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{SLACK_API_BASE}/{method}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                status = getattr(resp, "status", 200)
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                err_body = ""
            logger.warning("slack_http_error status=%s", exc.code)
            raise SlackClientError(
                f"slack_http_{exc.code}",
                status=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            logger.warning("slack_network_error")
            raise SlackClientError("slack_network_error") from exc

        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise SlackClientError("slack_invalid_json", status=status) from exc

        if not isinstance(parsed, dict):
            raise SlackClientError("slack_unexpected_payload", status=status)

        if not parsed.get("ok"):
            err = str(parsed.get("error") or "unknown")
            logger.warning("slack_api_error error=%s", err)
            raise SlackClientError(f"slack_api_{err}", status=status, slack_error=err)

        return parsed

    def post_message(
        self,
        channel: str,
        text: str,
        *,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SlackMessageResult:
        payload: Dict[str, Any] = {
            "channel": channel,
            "text": text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts
        if blocks:
            payload["blocks"] = blocks
        if metadata:
            payload["metadata"] = metadata

        try:
            data = self._request("chat.postMessage", payload)
            return SlackMessageResult(
                ok=True,
                channel=data.get("channel"),
                ts=data.get("ts"),
                thread_ts=data.get("message", {}).get("thread_ts") or thread_ts,
                raw={"ok": True, "channel": data.get("channel"), "ts": data.get("ts")},
            )
        except SlackClientError as exc:
            return SlackMessageResult(ok=False, error=str(exc))

    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        *,
        blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> SlackMessageResult:
        payload: Dict[str, Any] = {
            "channel": channel,
            "ts": ts,
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks
        try:
            data = self._request("chat.update", payload)
            return SlackMessageResult(
                ok=True,
                channel=data.get("channel"),
                ts=data.get("ts"),
                raw={"ok": True},
            )
        except SlackClientError as exc:
            return SlackMessageResult(ok=False, error=str(exc))

    def health(self) -> Dict[str, Any]:
        try:
            data = self._request("auth.test", {})
            return {
                "enabled": True,
                "reachable": True,
                "team": data.get("team"),
                "user": data.get("user"),
            }
        except SlackClientError as exc:
            return {
                "enabled": True,
                "reachable": False,
                "error": str(exc),
            }


def build_slack_client(bot_token: Optional[str]) -> BaseSlackClient:
    if bot_token:
        return SlackClient(bot_token)
    return NullSlackClient()
