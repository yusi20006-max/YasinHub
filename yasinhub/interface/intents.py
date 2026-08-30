"""Structured intent model for the Yasin Interface (#96)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class IntentKind(str, Enum):
    READ_STATUS = "READ_STATUS"
    READ_EXECUTION = "READ_EXECUTION"
    READ_GITHUB = "READ_GITHUB"
    READ_MONDAY = "READ_MONDAY"
    INVESTIGATE_FAILURE = "INVESTIGATE_FAILURE"
    SUMMARIZE = "SUMMARIZE"
    CONTROL_REQUEST = "CONTROL_REQUEST"
    CONFIRM_CONTROL = "CONFIRM_CONTROL"
    CANCEL_CONTROL = "CANCEL_CONTROL"
    UNKNOWN = "UNKNOWN"


CONTROL_OPS = frozenset(
    {"start", "cancel", "retry", "re-run", "approve", "reject", "pause", "resume"}
)


@dataclass
class Intent:
    kind: IntentKind
    raw_text: str = ""
    execution_id: Optional[str] = None
    github_pr: Optional[int] = None
    github_issue: Optional[int] = None
    github_repo: Optional[str] = None
    monday_item_id: Optional[str] = None
    control_operation: Optional[str] = None
    confirmation_token: Optional[str] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    entities: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "raw_text": self.raw_text,
            "execution_id": self.execution_id,
            "github_pr": self.github_pr,
            "github_issue": self.github_issue,
            "github_repo": self.github_repo,
            "monday_item_id": self.monday_item_id,
            "control_operation": self.control_operation,
            "confirmation_token": self.confirmation_token,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
            "entities": list(self.entities),
        }

    @property
    def is_control(self) -> bool:
        return self.kind in (
            IntentKind.CONTROL_REQUEST,
            IntentKind.CONFIRM_CONTROL,
            IntentKind.CANCEL_CONTROL,
        )

    @property
    def is_read(self) -> bool:
        return self.kind in (
            IntentKind.READ_STATUS,
            IntentKind.READ_EXECUTION,
            IntentKind.READ_GITHUB,
            IntentKind.READ_MONDAY,
            IntentKind.INVESTIGATE_FAILURE,
            IntentKind.SUMMARIZE,
        )
