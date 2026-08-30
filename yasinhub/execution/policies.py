"""Control Plane policies, approvals, and audit for external integrations."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..observer.execution_store import redact_secrets

logger = logging.getLogger(__name__)

PRIVILEGED_OPS = {"merge", "production_merge", "force_push", "delete_branch"}


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    policy: str
    requires_approval: bool = False


@dataclass
class AuditRecord:
    audit_id: str
    actor: str
    source: str
    timestamp: float
    correlation_id: Optional[str]
    execution_id: Optional[str]
    external_ids: Dict[str, str]
    policy_decision: str
    action: str
    outcome: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return redact_secrets(
            {
                "audit_id": self.audit_id,
                "actor": self.actor,
                "source": self.source,
                "timestamp": self.timestamp,
                "correlation_id": self.correlation_id,
                "execution_id": self.execution_id,
                "external_ids": dict(self.external_ids),
                "policy_decision": self.policy_decision,
                "action": self.action,
                "outcome": self.outcome,
                "metadata": dict(self.metadata),
            }
        )


class PolicyEngine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._approvals: Dict[str, Dict[str, Any]] = {}
        self._audit: List[AuditRecord] = []
        self._seen_control: Set[str] = set()

    def evaluate(
        self,
        *,
        action: str,
        agent_id: Optional[str] = None,
        repository: Optional[str] = None,
        branch: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> PolicyDecision:
        action_l = action.lower()
        if action_l in PRIVILEGED_OPS:
            key = f"{execution_id}:{action_l}"
            with self._lock:
                if key in self._approvals and self._approvals[key].get("status") == "approved":
                    return PolicyDecision(True, "explicit approval granted", "privileged", False)
            return PolicyDecision(
                False,
                f"privileged operation '{action}' requires approval",
                "privileged",
                requires_approval=True,
            )
        if action_l in (
            "start",
            "cancel",
            "retry",
            "re-run",
            "approve",
            "reject",
            "pause",
            "resume",
        ):
            return PolicyDecision(True, "standard control action", "default-allow", False)
        return PolicyDecision(True, "default allow", "default", False)

    def approve(
        self,
        execution_id: str,
        action: str,
        *,
        actor: str,
        source: str = "control-plane",
        correlation_id: Optional[str] = None,
    ) -> AuditRecord:
        key = f"{execution_id}:{action.lower()}"
        with self._lock:
            self._approvals[key] = {
                "status": "approved",
                "actor": actor,
                "timestamp": time.time(),
                "action": action,
            }
        return self._audit_record(
            actor=actor,
            source=source,
            correlation_id=correlation_id,
            execution_id=execution_id,
            action=f"approve:{action}",
            policy_decision="approved",
            outcome="ok",
        )

    def reject(
        self,
        execution_id: str,
        action: str,
        *,
        actor: str,
        source: str = "control-plane",
        correlation_id: Optional[str] = None,
    ) -> AuditRecord:
        key = f"{execution_id}:{action.lower()}"
        with self._lock:
            self._approvals[key] = {
                "status": "rejected",
                "actor": actor,
                "timestamp": time.time(),
                "action": action,
            }
        return self._audit_record(
            actor=actor,
            source=source,
            correlation_id=correlation_id,
            execution_id=execution_id,
            action=f"reject:{action}",
            policy_decision="rejected",
            outcome="ok",
        )

    def authorize_and_record(
        self,
        *,
        action: str,
        actor: str,
        source: str,
        execution_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        external_ids: Optional[Dict[str, str]] = None,
        control_event_id: Optional[str] = None,
        **policy_kwargs: Any,
    ) -> PolicyDecision:
        # Shared-state idempotency across workers/restarts (#93)
        if control_event_id:
            from ..storage.shared_state import NS_CONTROL_EVENTS, get_shared_state

            store = get_shared_state()
            claimed = store.compare_and_set(
                NS_CONTROL_EVENTS,
                control_event_id,
                None,
                {
                    "claimed_at": time.time(),
                    "action": action,
                    "actor": actor,
                    "source": source,
                },
                ttl_seconds=7 * 24 * 3600,
            )
            if not claimed:
                with self._lock:
                    self._seen_control.add(control_event_id)
                return PolicyDecision(
                    False, "duplicate control event", "idempotency", False
                )
            with self._lock:
                self._seen_control.add(control_event_id)

        decision = self.evaluate(action=action, execution_id=execution_id, **policy_kwargs)
        self._audit_record(
            actor=actor,
            source=source,
            correlation_id=correlation_id,
            execution_id=execution_id,
            action=action,
            policy_decision="allow" if decision.allowed else "deny",
            outcome="authorized" if decision.allowed else "denied",
            external_ids=external_ids or {},
            metadata={
                "reason": decision.reason,
                "requires_approval": decision.requires_approval,
            },
        )
        return decision

    def _audit_record(
        self,
        *,
        actor: str,
        source: str,
        action: str,
        policy_decision: str,
        outcome: str,
        correlation_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        external_ids: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditRecord:
        rec = AuditRecord(
            audit_id=f"aud-{uuid.uuid4().hex[:16]}",
            actor=actor,
            source=source,
            timestamp=time.time(),
            correlation_id=correlation_id,
            execution_id=execution_id,
            external_ids=dict(external_ids or {}),
            policy_decision=policy_decision,
            action=action,
            outcome=outcome,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._audit.append(rec)
        logger.info("audit %s", rec.as_dict())
        return rec

    def list_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._audit)[-limit:]
        return [r.as_dict() for r in items]


_engine: Optional[PolicyEngine] = None
_engine_lock = threading.Lock()


def get_policy_engine() -> PolicyEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = PolicyEngine()
        return _engine
