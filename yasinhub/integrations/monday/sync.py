"""Bidirectional monday <-> YasinHub state synchronization.

YasinHub remains authoritative for execution state.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional, Set

from .client import MondayClient, MondayClientError
from .config import MondayConfig, get_monday_config
from ...observer.execution_store import get_default_store

logger = logging.getLogger(__name__)

# Hub status -> monday status label
STATUS_MAP = {
    "queued": "Queued",
    "running": "Running",
    "paused": "Review",
    "succeeded": "Done",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


class MondaySyncService:
    def __init__(self, config: Optional[MondayConfig] = None) -> None:
        self._config = config or get_monday_config()
        self._client = MondayClient(self._config)
        self._lock = threading.RLock()
        self._push_origins: Set[str] = set()  # prevent sync loops

    def mark_hub_origin(self, item_id: str) -> None:
        with self._lock:
            self._push_origins.add(str(item_id))

    def is_hub_origin(self, item_id: str) -> bool:
        with self._lock:
            return str(item_id) in self._push_origins

    def clear_hub_origin(self, item_id: str) -> None:
        with self._lock:
            self._push_origins.discard(str(item_id))

    def map_status(self, hub_status: str) -> str:
        return STATUS_MAP.get(hub_status, hub_status)

    def push_execution_to_monday(self, execution_id: str) -> Dict[str, Any]:
        store = get_default_store()
        snap = store.get_execution(execution_id)
        if not snap:
            return {"success": False, "error": "unknown execution"}

        meta = snap.metadata or {}
        board_id = meta.get("board_id")
        item_id = meta.get("item_id")
        if not board_id or not item_id:
            return {"success": False, "error": "no monday external refs"}

        if self.is_hub_origin(str(item_id)):
            # still allow push; origin flag is for inbound filtering
            pass

        self.mark_hub_origin(str(item_id))
        updates = {}
        cfg = self._config

        if not self._client.available:
            return {
                "success": True,
                "dry_run": True,
                "message": "monday client not configured; state recorded locally",
                "mapped_status": self.map_status(snap.status),
                "execution_id": execution_id,
                "item_id": item_id,
            }

        try:
            if cfg.status_column_id:
                label = self.map_status(snap.status)
                self._client.change_column_value(
                    str(board_id), str(item_id), cfg.status_column_id, {"label": label}
                )
                updates["status"] = label
            if cfg.execution_id_column_id:
                self._client.change_column_value(
                    str(board_id), str(item_id), cfg.execution_id_column_id, execution_id
                )
                updates["execution_id"] = execution_id
            if cfg.agent_column_id and snap.agent_id:
                self._client.change_column_value(
                    str(board_id), str(item_id), cfg.agent_column_id, snap.agent_id
                )
            if cfg.result_column_id and snap.result is not None:
                self._client.change_column_value(
                    str(board_id), str(item_id), cfg.result_column_id, str(snap.result)[:500]
                )
        except MondayClientError as e:
            logger.warning("monday sync push failed: %s", e)
            return {"success": False, "error": str(e)}

        return {"success": True, "updates": updates, "item_id": item_id}

    def reconcile(self) -> Dict[str, Any]:
        """Repair missed webhook updates by pushing all known executions."""
        store = get_default_store()
        results = []
        for snap in store.list_executions():
            if (snap.metadata or {}).get("source") == "monday":
                results.append(self.push_execution_to_monday(snap.execution_id))
        return {"success": True, "reconciled": len(results), "results": results}


_sync: Optional[MondaySyncService] = None
_sync_lock = threading.Lock()


def get_sync_service() -> MondaySyncService:
    global _sync
    with _sync_lock:
        if _sync is None:
            _sync = MondaySyncService()
        return _sync
