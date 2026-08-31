"""
Slack interactive operations: View / Cancel / Retry (#73) + Yasin confirm (#99/#101/#105).

Every action: verify (routes) → identity → authorize → Control API / Interface.
Never trust button payloads as authorization.
Interactive deduplication is backed by SharedState; sensitive ops fail closed if unavailable.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from ...adapters.agent_runtime import get_runtime_adapter
from ...execution.control_api import ControlRequest, get_control_api
from ...interface.session import get_session_store
from ...observer import get_default_store
from .events import SlackInboundEvent
from .permissions import (
    AuthorizationError,
    IdentityStore,
    YasinIdentity,
    authorize_command,
)

logger = logging.getLogger(__name__)

ACTION_TO_COMMAND = {
    "view": "execution",
    "view_execution": "execution",
    "cancel": "cancel",
    "cancel_execution": "cancel",
    "retry": "retry",
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
        """Return True if duplicate.

        When SharedState is unavailable:
          - sensitive=True → raise RuntimeError (fail-closed for control mutations)
          - sensitive=False → return False (allow read/view; Control API still authoritative)
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
            logger.warning(
                "slack_interaction_dedupe_unavailable error=%s sensitive=%s",
                type(exc).__name__,
                sensitive,
            )
            if sensitive:
                raise RuntimeError("interaction_dedupe_unavailable") from exc
            return False


_deduper = InteractionDeduper()


class InteractiveHandler:
    def __init__(self, identity_store: Optional[IdentityStore] = None) -> None:
        self._identities = identity_store or IdentityStore()

    def handle(self, event: SlackInboundEvent) -> InteractionResult:
        action = (event.action_id or "").strip().lower()
        value = (event.action_value or "").strip()

        if action in ("yasin_confirm", "yasin_cancel"):
            dedupe_key = event.trigger_id or f"yasin:{action}:{value}:{event.slack_user_id}"
            try:
                if _deduper.already_processed(dedupe_key, sensitive=True):
                    return InteractionResult(
                        ok=True,
                        text=f"Confirmation action `{action}` already processed (idempotent).",
                    )
            except RuntimeError:
                return InteractionResult(
                    ok=False,
                    text="Confirmation temporarily unavailable (shared state). Retry shortly.",
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

        dedupe_key = event.trigger_id or f"{action}:{value}:{event.slack_user_id}"
        sensitive = cmd in ("cancel", "retry")
        try:
            if _deduper.already_processed(dedupe_key, sensitive=sensitive):
                return InteractionResult(ok=True, text=f"Action `{action}` for `{value}` already processed (idempotent).")
        except RuntimeError:
            return InteractionResult(
                ok=False,
                text="Action temporarily unavailable (shared state). Control Plane remains healthy; retry shortly.",
            )

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
            yasin_uid = getattr(identity, "yasin_user_id", None) if identity else None
            resp = handle_slack_confirmation(
                action_id=action,
                token=token,
                slack_user_id=event.slack_user_id,
                yasin_user_id=yasin_uid,
                channel_id=event.channel_id,
                thread_ts=event.correlation_id,
            )
            rendered = render_slack_response(resp)
            return InteractionResult(
                ok=resp.success or bool(resp.answer),
                text=rendered.get("text") or resp.answer or "",
            )
        except Exception as exc:
            logger.warning("yasin_confirm_failed error=%s", type(exc).__name__)
            return InteractionResult(
                ok=False,
                text="Confirmation handling failed; Control Plane remains healthy.",
            )

    def _view(self, eid: str) -> InteractionResult:
        adapter = get_runtime_adapter()
        data = None
        try:
            data = adapter.get_execution(eid)
        except Exception:
            data = None
        if data is None:
            rec = get_default_store().get_execution(eid)
            if rec is None:
                return InteractionResult(ok=False, text=f"Unknown execution `{eid}`")
            data = rec.as_dict()
        if not isinstance(data, dict):
            data = {"execution_id": eid, "status": str(data)}
        status = data.get("status", "?")
        return InteractionResult(ok=True, text=f"Execution `{eid}` — *{status}*", data=data)

    def _cancel(self, eid: str, identity: YasinIdentity, event: SlackInboundEvent) -> InteractionResult:
        resp = get_control_api().handle(
            ControlRequest(
                action="cancel",
                actor=identity.yasin_user_id,
                source="slack",
                execution_id=eid,
                control_event_id=event.request_id or event.trigger_id or f"slack-ix-{uuid.uuid4().hex[:10]}",
                metadata={"slack_user_id": identity.slack_user_id, "action": "cancel"},
            )
        )
        if not resp.success:
            return InteractionResult(ok=False, text=f"Cancel failed: {resp.error or 'denied'}")
        return InteractionResult(ok=True, text=f"Cancel requested for `{eid}`", data=resp.execution)

    def _retry(self, eid: str, identity: YasinIdentity, event: SlackInboundEvent) -> InteractionResult:
        resp = get_control_api().handle(
            ControlRequest(
                action="retry",
                actor=identity.yasin_user_id,
                source="slack",
                execution_id=eid,
                control_event_id=event.request_id or event.trigger_id or f"slack-ix-retry-{uuid.uuid4().hex[:10]}",
                metadata={"slack_user_id": identity.slack_user_id, "action": "retry"},
            )
        )
        if not resp.success:
            return InteractionResult(ok=False, text=f"Retry failed: {resp.error or 'denied'}")
        new_id = (resp.execution or {}).get("execution_id") if isinstance(resp.execution, dict) else None
        label = f"`{new_id}`" if new_id else "new execution"
        return InteractionResult(ok=True, text=f"Retry queued as {label} (from `{eid}`)", data=resp.execution)
