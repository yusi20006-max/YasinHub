"""Normalize raw monday webhook payloads into internal events."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from .config import MondayConfig, get_monday_config
from .models import MondayNormalizedEvent


def _extract_column_values(raw: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not isinstance(raw, (list, dict)):
        return out
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict):
                out[str(k)] = v.get("text") or v.get("value") or v
            else:
                out[str(k)] = v
        return out
    for col in raw:
        if not isinstance(col, dict):
            continue
        cid = str(col.get("id") or col.get("column_id") or "")
        if not cid:
            continue
        text = col.get("text")
        value = col.get("value")
        out[cid] = text if text is not None else value
    return out


def _detect_event_type(payload: Dict[str, Any], status: Optional[str], cfg: MondayConfig) -> str:
    """Map monday event + status to internal event type."""
    raw_type = (
        payload.get("type")
        or payload.get("event", {}).get("type")
        if isinstance(payload.get("event"), dict)
        else None
        or payload.get("eventType")
        or ""
    )
    raw_type = str(raw_type).lower()

    if status and any(s.lower() == str(status).lower() for s in cfg.status_ready_values):
        return "task.ready"

    if "create" in raw_type or raw_type in ("create_pulse", "create_item"):
        return "item.created"
    if "update" in raw_type or "change" in raw_type or "column" in raw_type:
        return "task.updated"
    if "delete" in raw_type:
        return "item.deleted"
    if status:
        return "task.status_changed"
    return "monday.event"


def normalize_monday_payload(
    payload: Dict[str, Any],
    *,
    config: Optional[MondayConfig] = None,
) -> List[MondayNormalizedEvent]:
    """Convert a raw monday webhook body into zero or more normalized events."""
    cfg = config or get_monday_config()
    events: List[MondayNormalizedEvent] = []

    # monday often wraps under "event"
    event_obj = payload.get("event") if isinstance(payload.get("event"), dict) else payload

    board_id = str(
        event_obj.get("boardId")
        or event_obj.get("board_id")
        or payload.get("boardId")
        or payload.get("board_id")
        or ""
    )
    item_id = str(
        event_obj.get("pulseId")
        or event_obj.get("itemId")
        or event_obj.get("item_id")
        or event_obj.get("pulse_id")
        or payload.get("pulseId")
        or payload.get("itemId")
        or ""
    )
    if not item_id and not board_id:
        # might be a batch or different shape
        if "pulseId" not in str(payload) and "itemId" not in str(payload):
            raise ValueError("missing board_id / item_id")

    name = event_obj.get("pulseName") or event_obj.get("itemName") or event_obj.get("name")
    column_values = _extract_column_values(
        event_obj.get("columnValues")
        or event_obj.get("column_values")
        or event_obj.get("column_values_json")
        or {}
    )

    # Status from column or dedicated field
    status = None
    if cfg.status_column_id and cfg.status_column_id in column_values:
        status = str(column_values[cfg.status_column_id])
    else:
        status = (
            event_obj.get("status")
            or event_obj.get("columnValue")
            or column_values.get("status")
        )
        if isinstance(status, dict):
            status = status.get("label") or status.get("text") or str(status)

    event_type = _detect_event_type(payload, status, cfg)
    correlation_id = None
    if cfg.correlation_column_id and cfg.correlation_column_id in column_values:
        correlation_id = str(column_values[cfg.correlation_column_id])
    if not correlation_id:
        correlation_id = f"mon-{board_id}-{item_id}" if board_id and item_id else f"mon-{uuid.uuid4().hex[:12]}"

    evt = MondayNormalizedEvent(
        event_id=f"mon-evt-{uuid.uuid4().hex[:16]}",
        event_type=event_type,
        source="monday",
        board_id=board_id,
        item_id=item_id,
        correlation_id=correlation_id,
        timestamp=time.time(),
        status=str(status) if status is not None else None,
        name=str(name) if name is not None else None,
        column_values=column_values,
        metadata={
            "user_id": event_obj.get("userId") or event_obj.get("user_id"),
            "trigger_time": event_obj.get("triggerTime") or event_obj.get("trigger_time"),
        },
        raw_event_type=str(
            payload.get("type")
            or (payload.get("event") or {}).get("type")
            if isinstance(payload.get("event"), dict)
            else payload.get("type")
            or ""
        ),
    )
    events.append(evt)
    return events
