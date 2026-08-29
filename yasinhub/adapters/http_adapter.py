"""
HttpAgentRuntimeAdapter — authenticated HTTP implementation of AgentRuntimeAdapter (#59).

Hub is an HTTP client. Agent remains authoritative for lifecycle.
Local ObserverStore is used as a projection cache for list/get consistency
with existing Observer API routes.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from ..observer.execution_store import (
    ExecutionObserverStore,
    InvalidTransitionError,
    get_default_store,
)
from .agent_runtime import (
    AgentRuntimeAdapter,
    IntegrationContext,
    project_event_dict,
    project_execution_dict,
    project_fleet_dict,
)
from .http_transport import (
    AuthenticationError,
    HttpTransportClient,
    HttpTransportConfig,
    TransportError,
    TransportUnavailable,
)

logger = logging.getLogger(__name__)


class HttpAgentRuntimeAdapter(AgentRuntimeAdapter):
    """AgentRuntimeAdapter backed by remote Agent HTTP surface."""

    def __init__(
        self,
        client: HttpTransportClient,
        *,
        store: Optional[ExecutionObserverStore] = None,
        audit_sink: Any = None,
    ) -> None:
        self._client = client
        self._store = store if store is not None else get_default_store()
        self._audit_sink = audit_sink

    @property
    def client(self) -> HttpTransportClient:
        return self._client

    @property
    def health(self):
        return self._client.health

    def is_stale(self) -> bool:
        return self._client.is_stale()

    def _audit(self, action: str, context: IntegrationContext, **extra: Any) -> None:
        record = {
            **context.as_audit(),
            "action": action,
            **{k: v for k, v in extra.items() if k not in ("token", "password", "api_key", "secret")},
        }
        if self._audit_sink:
            try:
                self._audit_sink(record)
            except Exception:
                logger.exception("audit sink failed")
        logger.info("audit %s", record)

    def _map_status_error(self, status: int, data: Any, *, action: str) -> None:
        """Raise KeyError / InvalidTransitionError from HTTP status."""
        body = data if isinstance(data, dict) else {}
        detail = body.get("detail") or body.get("message") or body.get("error") or str(data)
        if status in (401, 403):
            raise AuthenticationError(str(detail), status=status)
        if status == 404:
            raise KeyError(str(detail) or f"{action}: not found")
        if status == 409:
            current = body.get("current") or body.get("current_status") or "unknown"
            target = body.get("target") or body.get("target_status") or "unknown"
            if isinstance(detail, str) and "->" in detail:
                parts = detail.split("->")
                current = parts[0].split()[-1].strip()
                target = parts[-1].strip()
            raise InvalidTransitionError(str(current), str(target))
        if status >= 500:
            raise TransportUnavailable(f"{action} failed: {detail}")
        raise TransportError(f"{action} failed: {detail}", status=status, retryable=False)

    def _control(
        self,
        action: str,
        path: str,
        context: IntegrationContext,
        *,
        resource_key: str,
    ) -> Dict[str, Any]:
        self._audit(action, context, path=path)
        body = {
            "request_id": context.request_id,
            "actor": context.actor,
            "source": context.source,
        }
        idem = f"{action}:{resource_key}:{context.request_id}"
        try:
            status, data = self._client.post_json(
                path,
                body,
                request_id=context.request_id,
                idempotency_key=idem,
            )
        except AuthenticationError:
            self._audit(action, context, result="auth_failed")
            raise
        except TransportUnavailable:
            self._audit(action, context, result="unavailable")
            raise
        except TransportError as e:
            status = getattr(e, "status", None)
            body_data = getattr(e, "body", None) or {}
            self._audit(action, context, result="transport_error", status=status)
            if status in (404, 409) and status is not None:
                self._map_status_error(int(status), body_data, action=action)
            raise

        if status >= 400:
            self._audit(action, context, result="error", status=status)
            self._map_status_error(status, data, action=action)

        if not isinstance(data, dict):
            data = {"result": data}

        if "execution_id" in data:
            try:
                self._store.upsert_execution(project_execution_dict(data))
            except Exception:
                logger.exception("projection of control response failed")
        elif "task_id" in data and ("workers" in data or "status" in data):
            try:
                self._store.upsert_fleet(project_fleet_dict(data))
            except Exception:
                logger.exception("projection of fleet control response failed")

        self._audit(action, context, result="ok")
        return data

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        try:
            data = self._client.get_json(
                f"/v1/executions/{execution_id}",
                request_id=str(uuid.uuid4()),
            )
        except TransportError as e:
            if e.status == 404:
                return None
            raise
        if not isinstance(data, dict):
            return None
        try:
            self._store.upsert_execution(project_execution_dict(data))
        except Exception:
            logger.exception("projection failed for get_execution")
        return data

    def list_executions(
        self,
        *,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if task_id:
            query["task_id"] = task_id
        if session_id:
            query["session_id"] = session_id
        if status:
            query["status"] = status
        data = self._client.get_json("/v1/executions", query=query or None)
        items = data if isinstance(data, list) else (data.get("items") or data.get("executions") or [])
        out: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                self._store.upsert_execution(project_execution_dict(item))
            except Exception:
                logger.exception("projection failed for list item")
            out.append(item)
        return out

    def list_events(
        self,
        *,
        execution_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if execution_id:
            query["execution_id"] = execution_id
        if task_id:
            query["task_id"] = task_id
        if session_id:
            query["session_id"] = session_id
        if worker_id:
            query["worker_id"] = worker_id
        if event_type:
            query["event_type"] = event_type
        if limit is not None:
            query["limit"] = limit
        path = f"/v1/executions/{execution_id}/events" if execution_id else "/v1/events"
        data = self._client.get_json(path, query=query or None)
        items = data if isinstance(data, list) else (data.get("items") or data.get("events") or [])
        out: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            eid = item.get("event_id") or item.get("id")
            if eid and not self._client.remember_event_id(str(eid)):
                continue
            try:
                self._store.emit_event(
                    event_type=str(item.get("event_type") or "unknown"),
                    execution_id=str(item.get("execution_id") or ""),
                    task_id=str(item.get("task_id") or ""),
                    session_id=str(item.get("session_id") or ""),
                    status=str(item.get("status") or ""),
                    metadata=dict(item.get("metadata") or {}),
                    agent_id=item.get("agent_id"),
                    workspace_id=item.get("workspace_id"),
                    worker_id=item.get("worker_id"),
                    parent_task_id=item.get("parent_task_id"),
                )
            except Exception:
                logger.exception("event projection failed")
            out.append(item)

        def _key(e: Dict[str, Any]):
            return (e.get("sequence") or 0, e.get("timestamp") or e.get("created_at") or "")

        out.sort(key=_key)
        if limit is not None and limit >= 0:
            out = out[:limit]
        return out

    def get_fleet(self, task_id: str) -> Optional[Dict[str, Any]]:
        try:
            data = self._client.get_json(f"/v1/fleets/{task_id}")
        except TransportError as e:
            if e.status == 404:
                return None
            raise
        if not isinstance(data, dict):
            return None
        try:
            self._store.upsert_fleet(project_fleet_dict(data))
        except Exception:
            logger.exception("fleet projection failed")
        return data

    def list_fleets(self) -> List[Dict[str, Any]]:
        data = self._client.get_json("/v1/fleets")
        items = data if isinstance(data, list) else (data.get("items") or data.get("fleets") or [])
        out: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                self._store.upsert_fleet(project_fleet_dict(item))
            except Exception:
                logger.exception("fleet list projection failed")
            out.append(item)
        return out

    def pause(self, execution_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        return self._control(
            "pause",
            f"/v1/executions/{execution_id}/pause",
            context,
            resource_key=execution_id,
        )

    def resume(self, execution_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        return self._control(
            "resume",
            f"/v1/executions/{execution_id}/resume",
            context,
            resource_key=execution_id,
        )

    def cancel(self, execution_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        return self._control(
            "cancel",
            f"/v1/executions/{execution_id}/cancel",
            context,
            resource_key=execution_id,
        )

    def cancel_fleet(self, task_id: str, *, context: IntegrationContext) -> Dict[str, Any]:
        return self._control(
            "fleet_cancel",
            f"/v1/fleets/{task_id}/cancel",
            context,
            resource_key=task_id,
        )


def build_adapter_from_env(
    env: Optional[Dict[str, str]] = None,
    *,
    store: Optional[ExecutionObserverStore] = None,
) -> Optional[HttpAgentRuntimeAdapter]:
    """Construct HttpAgentRuntimeAdapter when env has base URL + token; else None."""
    cfg = HttpTransportConfig.from_env(env)
    if cfg is None:
        return None
    client = HttpTransportClient(cfg)
    return HttpAgentRuntimeAdapter(client, store=store)


__all__ = [
    "HttpAgentRuntimeAdapter",
    "build_adapter_from_env",
]
