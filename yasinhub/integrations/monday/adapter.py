"""monday Adapter — ingests normalized events, provides health/sync surfaces.

Never dispatches Agents. Downstream stages (#65+) consume the normalized
events via the internal event bus / store.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .config import MondayConfig, get_monday_config
from .models import MondayNormalizedEvent

logger = logging.getLogger(__name__)


class MondayAdapter:
    """In-process monday integration boundary."""

    def __init__(self, config: Optional[MondayConfig] = None) -> None:
        self._config = config or get_monday_config()
        self._lock = threading.RLock()
        self._events: List[MondayNormalizedEvent] = []
        self._seen_ids: set = set()
        self._last_ingest_at: Optional[float] = None

    @property
    def config(self) -> MondayConfig:
        return self._config

    def ingest_normalized_event(self, event: MondayNormalizedEvent) -> bool:
        """Idempotent ingest of a normalized monday event.

        Returns True if newly accepted, False if duplicate.
        """
        with self._lock:
            if event.event_id in self._seen_ids:
                return False
            # also key by correlation + type for stronger idempotency
            dedup_key = f"{event.correlation_id}:{event.event_type}:{event.item_id}"
            if dedup_key in self._seen_ids:
                return False
            self._seen_ids.add(event.event_id)
            self._seen_ids.add(dedup_key)
            self._events.append(event)
            self._last_ingest_at = time.time()

        logger.info(
            "monday event ingested type=%s board=%s item=%s corr=%s",
            event.event_type,
            event.board_id,
            event.item_id,
            event.correlation_id,
        )
        return True

    def list_events(
        self,
        *,
        event_type: Optional[str] = None,
        board_id: Optional[str] = None,
        item_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[MondayNormalizedEvent]:
        with self._lock:
            items = list(self._events)
        if event_type:
            items = [e for e in items if e.event_type == event_type]
        if board_id:
            items = [e for e in items if e.board_id == board_id]
        if item_id:
            items = [e for e in items if e.item_id == item_id]
        return items[-limit:]

    def health(self) -> Dict[str, Any]:
        cfg = self._config
        return {
            "service": "monday-integration",
            "status": "ok" if cfg.enabled or cfg.has_credentials() else "disabled",
            "enabled": cfg.enabled,
            "has_credentials": cfg.has_credentials(),
            "has_signing_secret": cfg.has_signing_secret(),
            "events_ingested": len(self._events),
            "last_ingest_at": self._last_ingest_at,
            "config": cfg.as_safe_dict(),
        }

    def sync_status(self) -> Dict[str, Any]:
        """Manual reconciliation entry point (foundation for #67)."""
        return {
            "success": True,
            "message": "sync endpoint ready; full bidirectional sync in #67",
            "pending_events": len(self._events),
            "boards": list(self._config.default_board_ids),
        }

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._seen_ids.clear()
            self._last_ingest_at = None


_adapter: Optional[MondayAdapter] = None
_adapter_lock = threading.Lock()


def get_monday_adapter() -> MondayAdapter:
    global _adapter
    with _adapter_lock:
        if _adapter is None:
            _adapter = MondayAdapter()
        return _adapter


def set_monday_adapter(adapter: Optional[MondayAdapter]) -> None:
    global _adapter
    with _adapter_lock:
        _adapter = adapter
