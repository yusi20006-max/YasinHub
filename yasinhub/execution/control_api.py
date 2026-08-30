"""Unified YasinHub Control API — channel-neutral command boundary.

All external surfaces (monday, PWA, CLI, Slack, Telegram) must route
control operations through this API. Never call Yasin-Agent directly.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..adapters.agent_runtime import IntegrationContext, get_runtime_adapter
from ..observer.execution_store import InvalidTransitionError, get_default_store
from .correlation import get_correlation_store
from .policies import get_policy_engine

logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = ("status", "start", "cancel", "retry", "re-run", "approve", "reject")


@dataclass
class ControlRequest:
    action: str
    actor: str
    source: str
    execution_id: Optional[str] = None
    correlation_id: Optional[str] = None
    control_event_id: Optional[str] = None
    target_action: Optional[str] = None  # for approve/reject of privileged ops
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ControlRequest":
        return cls(
            action=str(data.get("action") or "").lower().strip(),
            actor=str(data.get("actor") or "anonymous"),
            source=str(data.get("source") or "unknown"),
            execution_id=data.get("execution_id"),
            correlation_id=data.get("correlation_id"),
            control_event_id=data.get("control_event_id") or data.get("idempotency_key"),
            target_action=data.get("target_action"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ControlResponse:
    success: bool
    action: str
    status_code: int = 200
    execution: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    policy: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "action": self.action,
            "request_id": self.request_id,
        }
        if self.execution is not None:
            d["execution"] = self.execution
        if self.error is not None:
            d["error"] = self.error
        if self.policy is not None:
            d["policy"] = self.policy
        if self.correlation_id is not None:
            d["correlation_id"] = self.correlation_id
        return d


class ControlAPI:
    """Central control command dispatcher."""

    def handle(self, request: ControlRequest) -> ControlResponse:
        request_id = request.control_event_id or f"ctrl-{uuid.uuid4().hex[:12]}"

        if request.action not in SUPPORTED_ACTIONS:
            return ControlResponse(
                success=False,
                action=request.action,
                status_code=400,
                error=f"unsupported action: {request.action}",
                request_id=request_id,
            )

        # Resolve execution via id or correlation
        execution_id = request.execution_id
        corr_id = request.correlation_id
        if not execution_id and corr_id:
            rec = get_correlation_store().get_by_correlation(corr_id)
            if rec:
                execution_id = rec.execution_id

        if request.action == "status":
            return self._status(execution_id, corr_id, request_id)

        if not execution_id and request.action not in ("approve", "reject"):
            return ControlResponse(
                success=False,
                action=request.action,
                status_code=400,
                error="execution_id or correlation_id required",
                request_id=request_id,
            )

        # Policy gate
        policy = get_policy_engine()
        target = request.target_action or request.action
        decision = policy.authorize_and_record(
            action=target,
            actor=request.actor,
            source=request.source,
            execution_id=execution_id,
            correlation_id=corr_id,
            control_event_id=request.control_event_id,
            external_ids={
                k: str(v)
                for k, v in (request.metadata or {}).items()
                if k in ("item_id", "board_id", "pr", "repo")
            },
        )

        if not decision.allowed:
            return ControlResponse(
                success=False,
                action=request.action,
                status_code=403,
                error=decision.reason,
                policy={
                    "allowed": False,
                    "reason": decision.reason,
                    "requires_approval": decision.requires_approval,
                },
                request_id=request_id,
                correlation_id=corr_id,
            )

        if request.action == "approve":
            policy.approve(
                execution_id or "",
                request.target_action or "production_merge",
                actor=request.actor,
                source=request.source,
                correlation_id=corr_id,
            )
            return ControlResponse(
                success=True,
                action="approve",
                request_id=request_id,
                correlation_id=corr_id,
                policy={"allowed": True, "status": "approved"},
            )

        if request.action == "reject":
            policy.reject(
                execution_id or "",
                request.target_action or "production_merge",
                actor=request.actor,
                source=request.source,
                correlation_id=corr_id,
            )
            return ControlResponse(
                success=True,
                action="reject",
                request_id=request_id,
                correlation_id=corr_id,
                policy={"allowed": True, "status": "rejected"},
            )

        return self._mutate(request.action, execution_id, request, request_id, corr_id)

    def _status(
        self,
        execution_id: Optional[str],
        corr_id: Optional[str],
        request_id: str,
    ) -> ControlResponse:
        store = get_default_store()
        if execution_id:
            snap = store.get_execution(execution_id)
            if not snap:
                return ControlResponse(
                    success=False,
                    action="status",
                    status_code=404,
                    error="unknown execution",
                    request_id=request_id,
                )
            corr = get_correlation_store().get_by_execution(execution_id)
            return ControlResponse(
                success=True,
                action="status",
                execution=snap.as_dict(),
                correlation_id=corr.correlation_id if corr else corr_id,
                request_id=request_id,
            )
        if corr_id:
            rec = get_correlation_store().get_by_correlation(corr_id)
            if not rec:
                return ControlResponse(
                    success=False,
                    action="status",
                    status_code=404,
                    error="unknown correlation",
                    request_id=request_id,
                )
            snap = store.get_execution(rec.execution_id)
            return ControlResponse(
                success=True,
                action="status",
                execution=snap.as_dict() if snap else None,
                correlation_id=corr_id,
                request_id=request_id,
            )
        # list recent
        items = [e.as_dict() for e in store.list_executions()][-20:]
        return ControlResponse(
            success=True,
            action="status",
            execution={"count": len(items), "executions": items},
            request_id=request_id,
        )

    def _mutate(
        self,
        action: str,
        execution_id: Optional[str],
        request: ControlRequest,
        request_id: str,
        corr_id: Optional[str],
    ) -> ControlResponse:
        store = get_default_store()
        adapter = get_runtime_adapter()
        ctx = IntegrationContext(
            request_id=request_id,
            actor=request.actor,
            source=request.source,
        )

        if not execution_id:
            return ControlResponse(
                success=False,
                action=action,
                status_code=400,
                error="execution_id required",
                request_id=request_id,
            )

        try:
            if action == "start":
                snap = store.get_execution(execution_id)
                if snap is None:
                    return ControlResponse(
                        success=False,
                        action=action,
                        status_code=404,
                        error="unknown execution",
                        request_id=request_id,
                    )
                updated = store.start(execution_id, actor=request.actor)
                return ControlResponse(
                    success=True,
                    action=action,
                    execution=updated.as_dict(),
                    request_id=request_id,
                    correlation_id=corr_id,
                )
            if action == "cancel":
                result = adapter.cancel(execution_id, context=ctx)
                return ControlResponse(
                    success=True,
                    action=action,
                    execution=result if isinstance(result, dict) else result,
                    request_id=request_id,
                    correlation_id=corr_id,
                )
            if action in ("retry", "re-run"):
                snap = store.get_execution(execution_id)
                if snap is None:
                    return ControlResponse(
                        success=False,
                        action=action,
                        status_code=404,
                        error="unknown execution",
                        request_id=request_id,
                    )
                # create a new execution linked by correlation
                meta = dict(snap.metadata or {})
                new_id = f"exec-retry-{uuid.uuid4().hex[:12]}"
                new_snap = store.create_execution(
                    task_id=snap.task_id,
                    session_id=f"sess-retry-{uuid.uuid4().hex[:8]}",
                    agent_id=snap.agent_id,
                    metadata={**meta, "retried_from": execution_id},
                    execution_id=new_id,
                )
                if corr_id or meta.get("correlation_id"):
                    try:
                        get_correlation_store().register(
                            execution_id=new_id,
                            correlation_id=str(corr_id or meta.get("correlation_id")),
                            monday_item_id=meta.get("item_id"),
                            monday_board_id=meta.get("board_id"),
                            github_repo=meta.get("repository"),
                        )
                    except Exception:
                        logger.exception("correlation on retry failed")
                return ControlResponse(
                    success=True,
                    action=action,
                    execution=new_snap.as_dict(),
                    request_id=request_id,
                    correlation_id=corr_id or meta.get("correlation_id"),
                )
        except KeyError:
            return ControlResponse(
                success=False,
                action=action,
                status_code=404,
                error="unknown execution",
                request_id=request_id,
            )
        except InvalidTransitionError as e:
            return ControlResponse(
                success=False,
                action=action,
                status_code=409,
                error=str(e),
                request_id=request_id,
            )
        except Exception as e:
            logger.exception("control action %s failed", action)
            return ControlResponse(
                success=False,
                action=action,
                status_code=500,
                error=str(e)[:200],
                request_id=request_id,
            )

        return ControlResponse(
            success=False,
            action=action,
            status_code=400,
            error="unhandled action",
            request_id=request_id,
        )


_api: Optional[ControlAPI] = None


def get_control_api() -> ControlAPI:
    global _api
    if _api is None:
        _api = ControlAPI()
    return _api
