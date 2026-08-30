"""Yasin-Core memory adapter boundary (#96). Does not duplicate Core memory."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class MemoryAdapter(Protocol):
    def recall(self, *, intent, session=None) -> Optional[Dict[str, Any]]:
        ...


class NullMemoryAdapter:
    def recall(self, *, intent, session=None) -> Optional[Dict[str, Any]]:
        return None


class FakeMemoryAdapter:
    def __init__(self, items: Optional[List[Dict[str, Any]]] = None) -> None:
        self._items = items or []

    def recall(self, *, intent, session=None) -> Optional[Dict[str, Any]]:
        eid = getattr(intent, "execution_id", None)
        hits = [i for i in self._items if not eid or i.get("execution_id") == eid]
        if not hits:
            return None
        return {"hits": hits[:5], "source": "fake_memory"}


class CoreMemoryAdapter:
    def __init__(self, core=None) -> None:
        self._core = core

    def recall(self, *, intent, session=None) -> Optional[Dict[str, Any]]:
        if self._core is None:
            try:
                from ..core_integration import CoreIntegration

                self._core = CoreIntegration()
            except Exception:
                return None
        if not getattr(self._core, "connected", False):
            return None
        try:
            client = getattr(self._core, "client", None)
            if client is None:
                return None
            if hasattr(client, "memory_search"):
                q = getattr(intent, "raw_text", "")[:200]
                result = client.memory_search(q)
                return {"hits": result, "source": "yasin_core"}
        except Exception:
            logger.debug("core_memory_recall_failed", exc_info=True)
        return None


_memory: Optional[MemoryAdapter] = None


def get_memory_adapter() -> MemoryAdapter:
    global _memory
    if _memory is None:
        _memory = NullMemoryAdapter()
    return _memory


def set_memory_adapter(adapter: Optional[MemoryAdapter]) -> None:
    global _memory
    _memory = adapter
