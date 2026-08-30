"""
Outbound Slack notifications for execution lifecycle events (#72/#93).

Best-effort only: notification failure must never fail the underlying execution.
Thread correlation groups updates under a root message per execution.
Thread map uses SharedStateStore so multiple workers resolve the same thread.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from .adapter import SlackAdapter, get_slack_adapter
from .client import SlackMessageResult
from .config import SlackConfig, is_slack_enabled, load_slack_config

logger = logging.getLogger(__name__)

NOTIFY_EVENTS = {
    "execution.started",
    "execution.completed",
    "execution.failed",
    "execution.cancelled",
    "execution.created",
    "ci.failed",
    "deployment.failed",
}

ALERT_EVENTS = {
    "execution.failed",
    "ci.failed",
    "deployment.failed",
}


def _format_lifecycle(event_type: str, execution_id: str, extra: Optional[Dict[str, Any]] = None) -> str:
    extra = extra or {}
    status = extra.get("status") or event_type.split(".")[-1]
    task = extra.get("task_id") or ""
    emoji = {
        "started": "🚀",
        "created": "📋",
        "completed": "✅",
        "succeeded": "✅",
        "failed": "❌",
        "cancelled": "⏹️",
    }.get(status, "•")
    line = f"{emoji} Execution `{execution_id}` — *{status}*"
    if task:
        line += f" (task `{task}`)"
    if extra.get("error"):
        line += f"\nerror: {extra['error']}"
    return line


class SlackNotifier:
    """Publishes filtered lifecycle events to Slack channels with optional threads."""

    def __init__(self, adapter: Optional[SlackAdapter] = None, config: Optional[SlackConfig] = None) -> None:
        self._adapter = adapter
        self._config = config or load_slack_config()
        self._threads: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._failures = 0

    @property
    def adapter(self) -> SlackAdapter:
        if self._adapter is None:
            self._adapter = get_slack_adapter()
        return self._adapter

    def should_notify(self, event_type: str) -> bool:
        return event_type in NOTIFY_EVENTS

    def channel_for(self, event_type: str) -> str:
        if event_type in ALERT_EVENTS:
            return self._config.alerts_channel
        return self._config.agent_channel

    def notify_execution_event(
        self,
        event_type: str,
        execution_id: str,
        *,
        status: Optional[str] = None,
        task_id: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SlackMessageResult:
        """Best-effort notify. Never raises."""
        if not is_slack_enabled(self._config) or not self._config.feature_notifications:
            return SlackMessageResult(ok=False, error="slack_disabled")
        if not self.should_notify(event_type):
            return SlackMessageResult(ok=False, error="filtered")

        extra = {"status": status or event_type.split(".")[-1], "task_id": task_id, "error": error}
        if metadata:
            extra.update({k: v for k, v in metadata.items() if k not in ("token", "secret")})
        text = _format_lifecycle(event_type, execution_id, extra)
        channel = self.channel_for(event_type)

        thread_ts: Optional[str] = None
        with self._lock:
            thread_ts = self._threads.get(execution_id)
        if thread_ts is None:
            try:
                from ...storage.shared_state import NS_SLACK_THREADS, get_shared_state

                shared = get_shared_state().get(NS_SLACK_THREADS, execution_id)
                if isinstance(shared, dict):
                    thread_ts = shared.get("thread_ts") or shared.get("ts")
                elif isinstance(shared, str):
                    thread_ts = shared
                if thread_ts:
                    with self._lock:
                        self._threads[execution_id] = thread_ts
            except Exception:
                logger.debug("slack_thread_lookup_failed", exc_info=True)

        try:
            result = self.adapter.post_message(channel, text, thread_ts=thread_ts)
            if result.ok and result.ts and thread_ts is None:
                with self._lock:
                    self._threads[execution_id] = result.ts
                try:
                    from ...storage.shared_state import NS_SLACK_THREADS, get_shared_state

                    get_shared_state().set(
                        NS_SLACK_THREADS,
                        execution_id,
                        {"thread_ts": result.ts, "channel": channel, "updated_at": time.time()},
                    )
                except Exception:
                    logger.debug("slack_thread_persist_failed", exc_info=True)
            if not result.ok:
                self._failures += 1
                logger.warning(
                    "slack_notify_failed execution_id=%s event=%s error=%s",
                    execution_id,
                    event_type,
                    result.error,
                )
            return result
        except Exception as exc:  # pragma: no cover
            self._failures += 1
            logger.warning("slack_notify_exception error=%s", type(exc).__name__)
            return SlackMessageResult(ok=False, error=str(exc))

    @property
    def failure_count(self) -> int:
        return self._failures


_default_notifier: Optional[SlackNotifier] = None


def get_slack_notifier() -> SlackNotifier:
    global _default_notifier
    if _default_notifier is None:
        _default_notifier = SlackNotifier()
    return _default_notifier


def set_slack_notifier(notifier: Optional[SlackNotifier]) -> None:
    global _default_notifier
    _default_notifier = notifier
