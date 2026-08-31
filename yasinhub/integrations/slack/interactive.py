"""
Slack interactive operations: View / Cancel / Retry (#73) + Yasin confirm (#99/#101).

Every action: verify (routes) → identity → authorize → Control API / Interface.
Never trust button payloads alone for authorization.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from ...adapters.agent_runtime import AgentRuntimeAdapter
from ...identity import AuthorizationError, IdentityStore, authorize_command
from ...interface.session import get_session_store
from .events import SlackInboundEvent

logger = logging.getLogger(__name__)

ACTION_TO_COMMAND = {
    "view_execution": "execution",
    "cancel_execution": "cancel",
    "retry_execution": "retry",
}


@dataclass
class InteractionResult:
    ok: bool
    text: str
    data: Optional[dict] = None


class InteractionDeduper:
    """SharedState-backed deduper with an atomic claim operation."""

    def __init__(self, ttl_seconds: float = 300.0, store=None) -> None:
        self.ttl_seconds = ttl_seconds
        self._store = store

    @property
    def store(self):
        return self._store or get_session_store().store

    def already_processed(self, key: str, *, sensitive: bool = False) -> bool:
        """Return True if the key was already claimed (idempotent skip).

        When SharedState is unavailable:
        - sensitive=True (confirm / cancel / retry): fail-closed → treat as
          already processed so a duplicate sensitive action is not executed.
        - sensitive=False (view / non-mutating): fail-open → allow the read.
        """
        if not key:
            return False
        owner = uuid.uuid4().hex
        try:
            return not self.store.try_acquire(
                "yasin_slack_interaction_dedupe",
                key,
                owner,
                ttl_seconds=self.ttl_seconds,
            )
        except Exception as exc:
            logger.warning("slack_interaction_dedupe_unavailable error=%s sensitive=%s", type(exc).__name__, sensitive)
            # Fail-closed for sensitive mutations; fail-open for safe reads.
            return bool(sensitive)


_deduper = InteractionDeduper()


class InteractiveHandler:
    def __init__(self, identity_store: Optional[IdentityStore] = None) -> None:
        self._identities = identity_store or IdentityStore()

    def handle(self, event: SlackInboundEvent) -> InteractionResult:
        action = (event.action_id or "").strip().lower()
        value = (event.action_value or "").strip()

        # Phase 4 Block Kit confirmation (#99/#101) — payload alone is not authorization
        if action in ("yasin_confirm", "yasin_cancel"):
            dedupe_key = event.trigger_id or f"yasin:{action}:{value}:{event.slack_user_id}"
            if _deduper.already_processed(dedupe_key, sensitive=True):
                return InteractionResult(
                    ok=True,
                    text=f"Confirmation action `{action}` already processed (idempotent).",
                )
            return self._handle_yasin_confirmation(event, action, value)

        cmd = ACTION_TO_COMMAND.get(action)
        if not cmd:
            return InteractionResult(ok=False, text=f"Unknown action `{action}`")

        identity = self._identities.resolve(event.slack_user_id)
        try:
            identity = authorize_command(identity, cmd)
        except AuthorizationError as exc:
            if exc.reason == "unmapped_slack_user":
                return InteractionResult(ok=False, text="Your Slack user is not mapped to a Yasin identity.")
            return InteractionResult(ok=False, text="Not authorized for this action.")

        if not value:
            return InteractionResult(ok=False, text="Missing execution id in action payload.")

        # cancel / retry are mutating → fail-closed when SharedState is down
        sensitive = cmd in ("cancel", "retry")
        dedupe_key = event.trigger_id or f"{action}:{value}:{event.slack_user_id}"
        if _deduper.already_processed(dedupe_key, sensitive=sensitive):
            return InteractionResult(ok=True, text=f"Action `{action}` for `{value}` already processed (idempotent).")

        if cmd == "execution":
            return self._view(value)
        if cmd == "cancel":
            return self._cancel(value, identity, event)
        if cmd == "retry":
            return self._retry(value, identity, event)
        return InteractionResult(ok=False, text="Unhandled action")

    def _handle_yasin_confirmation(
        self, event: SlackInboundEvent, action: str, token: str
    ) -> InteractionResult:
        try:
            from ...interface.slack_bridge import handle_slack_confirmation, render_slack_response

            identity = self._identities.resolve(event.slack_user_id)
            resp = handle_slack_confirmation(
                action=action,
                token=token,
                slack_user_id=event.slack_user_id,
                yasin_user_id=getattr(identity, "yasin_user_id", None) if identity else None,
                actor=(getattr(identity, "yasin_user_id", None) if identity else None) or event.slack_user_id or "anonymous",
            )
            text = render_slack_response(resp) if resp else "Confirmation processed."
            return InteractionResult(ok=bool(getattr(resp, "success", True)), text=text)
        except Exception as exc:
            logger.warning("yasin_confirm_failed error=%s", type(exc).__name__)
            return InteractionResult(
                ok=False,
                text="Confirmation handling failed; Control Plane remains healthy.",
            )

    def _view(self, execution_id: str) -> InteractionResult:
        try:
            from ...observer.execution_store import get_default_store

            store = get_default_store()
            snap = store.get(execution_id)
            if not snap:
                return InteractionResult(ok=False, text=f"Execution `{execution_id}` not found.")
            status = getattr(snap, "status", "unknown")
            task = getattr(snap, "task_id", "")
            return InteractionResult(
                ok=True,
                text=f"Execution `{execution_id}` status=`{status}` task=`{task}`",
                data={"execution_id": execution_id, "status": str(status)},
            )
        except Exception as exc:
            logger.warning("view_execution_failed error=%s", type(exc).__name__)
            return InteractionResult(ok=False, text="Could not load execution.")

    def _cancel(self, execution_id: str, identity, event: SlackInboundEvent) -> InteractionResult:
        try:
            adapter = AgentRuntimeAdapter()
            resp = adapter.cancel_execution(
                execution_id,
                actor=getattr(identity, "yasin_user_id", None) or event.slack_user_id or "anonymous",
                source="slack",
            )
            if not getattr(resp, "ok", False):
                return InteractionResult(ok=False, text=f"Cancel failed: {resp.error or 'denied'}")
            return InteractionResult(ok=True, text=f"Cancel requested for `{execution_id}`.")
        except Exception as exc:
            logger.warning("cancel_failed error=%s", type(exc).__name__)
            return InteractionResult(ok=False, text="Cancel request failed.")

    def _retry(self, execution_id: str, identity, event: SlackInboundEvent) -> InteractionResult:
        try:
            adapter = AgentRuntimeAdapter()
            resp = adapter.retry_execution(
                execution_id,
                actor=getattr(identity, "yasin_user_id", None) or event.slack_user_id or "anonymous",
                source="slack",
            )
            if not getattr(resp, "ok", False):
                return InteractionResult(ok=False, text=f"Retry failed: {resp.error or 'denied'}")
            return InteractionResult(ok=True, text=f"Retry requested for `{execution_id}`.")
        except Exception as exc:
            logger.warning("retry_failed error=%s", type(exc).__name__)
            return InteractionResult(ok=False, text="Retry request failed.")
