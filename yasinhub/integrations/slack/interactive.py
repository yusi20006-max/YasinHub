"""
Slack interactive operations: View / Cancel / Retry (#73).

Every action: verify (done by routes) → identity → authorize → validate resource → execute via YasinHub.
Idempotent cancel/retry; never trust button payloads as authorization.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from ...adapters.agent_runtime import IntegrationContext, get_runtime_adapter
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


@dataclass
class InteractionDeduper:
    """Simple in-process idempotency for interactive action trigger_ids / action keys."""

    ttl_seconds: float = 300.0
    _seen: Dict[str, float] = field(default_factory=dict)
    _lock_keys: Set[str] = field(default_factory=set)

    def already_processed(self, key: str) -> bool:
        now = time.time()
        expired = [k for k, t in self._seen.items() if now - t > self.ttl_seconds]
        for k in expired:
            self._seen.pop(k, None)
        if key in self._seen:
            return True
        self._seen[key] = now
        return False


_deduper = InteractionDeduper()


class InteractiveHandler:
    def __init__(self, identity_store: Optional[IdentityStore] = None) -> None:
        self._identities = identity_store or IdentityStore()

    def handle(self, event: SlackInboundEvent) -> InteractionResult:
        action = (event.action_id or "").strip().lower()
        value = (event.action_value or "").strip()
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
        if _deduper.already_processed(dedupe_key):
            return InteractionResult(ok=True, text=f"Action `{action}` for `{value}` already processed (idempotent).")

        if cmd == "execution":
            return self._view(value)
        if cmd == "cancel":
            return self._cancel(value, identity, event)
        if cmd == "retry":
            return self._retry(value, identity, event)
        return InteractionResult(ok=False, text="Unhandled action")

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
        ctx = IntegrationContext(
            request_id=event.request_id or f"slack-ix-{uuid.uuid4().hex[:12]}",
            actor=identity.yasin_user_id,
            source="slack-interactive",
            metadata={"slack_user_id": identity.slack_user_id, "action": "cancel"},
        )
        try:
            result = get_runtime_adapter().cancel(eid, context=ctx)
        except Exception as exc:
            return InteractionResult(ok=False, text=f"Cancel failed: {type(exc).__name__}")
        return InteractionResult(ok=True, text=f"Cancel requested for `{eid}`", data=result if isinstance(result, dict) else None)

    def _retry(self, eid: str, identity: YasinIdentity, event: SlackInboundEvent) -> InteractionResult:
        store = get_default_store()
        existing = store.get_execution(eid)
        if existing is None:
            return InteractionResult(ok=False, text=f"Unknown execution `{eid}`")
        status = getattr(existing, "status", None)
        if status not in ("failed", "cancelled"):
            return InteractionResult(ok=False, text=f"Cannot retry `{eid}` in status `{status}`")
        new_id = f"exec-{uuid.uuid4().hex[:12]}"
        task_id = getattr(existing, "task_id", "") or ""
        snap = store.create_execution(
            execution_id=new_id,
            task_id=str(task_id),
            session_id=f"slack-ix-retry-{event.request_id}",
            metadata={"source": "slack-interactive", "actor": identity.yasin_user_id, "retry_of": eid},
        )
        return InteractionResult(ok=True, text=f"Retry queued as `{new_id}` (from `{eid}`)", data=snap.as_dict())
