"""monday.com specific models. Isolated from core execution models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MondayItemRef:
    """Stable external reference to a monday item/board."""

    board_id: str
    item_id: str
    pulse_id: Optional[str] = None  # legacy alias

    def as_dict(self) -> Dict[str, str]:
        d = {"board_id": self.board_id, "item_id": self.item_id}
        if self.pulse_id:
            d["pulse_id"] = self.pulse_id
        return d


@dataclass
class MondayNormalizedEvent:
    """Internal Yasin event envelope produced by the monday adapter.

    Never contains raw monday secrets or full payload blobs beyond
    what is required for correlation and audit.
    """

    event_id: str
    event_type: str  # e.g. task.ready, task.updated, item.created
    source: str = "monday"
    board_id: str = ""
    item_id: str = ""
    correlation_id: Optional[str] = None
    timestamp: float = 0.0
    status: Optional[str] = None
    name: Optional[str] = None
    column_values: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_event_type: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "board_id": self.board_id,
            "item_id": self.item_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "status": self.status,
            "name": self.name,
            "column_values": dict(self.column_values),
            "metadata": dict(self.metadata),
            "raw_event_type": self.raw_event_type,
        }

    def external_ref(self) -> MondayItemRef:
        return MondayItemRef(board_id=self.board_id, item_id=self.item_id)
