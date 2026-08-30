"""Structured interface response model (#96)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class InterfaceResponse:
    answer: str
    evidence: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    execution_refs: List[str] = field(default_factory=list)
    confidence: float = 0.5
    uncertainty: Optional[str] = None
    suggested_next_actions: List[str] = field(default_factory=list)
    confirmation_required: bool = False
    confirmation_token: Optional[str] = None
    confirmation_summary: Optional[str] = None
    intent_kind: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "evidence": list(self.evidence),
            "references": list(self.references),
            "execution_refs": list(self.execution_refs),
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "suggested_next_actions": list(self.suggested_next_actions),
            "confirmation_required": self.confirmation_required,
            "confirmation_token": self.confirmation_token,
            "confirmation_summary": self.confirmation_summary,
            "intent_kind": self.intent_kind,
            "success": self.success,
            "error": self.error,
            "metadata": dict(self.metadata),
        }

    def to_slack_text(self) -> str:
        parts = [self.answer]
        if self.confirmation_required and self.confirmation_summary:
            parts.append("")
            parts.append(f"*Confirmation required:* {self.confirmation_summary}")
            parts.append("Reply `@Yasin confirm <token>` or `@Yasin cancel control`.")
            if self.confirmation_token:
                parts.append(f"Token: `{self.confirmation_token}`")
        if self.suggested_next_actions:
            parts.append("")
            parts.append("*Suggested next actions:*")
            for a in self.suggested_next_actions[:5]:
                parts.append(f"• {a}")
        if self.uncertainty:
            parts.append(f"\n_Uncertainty: {self.uncertainty}_")
        return "\n".join(parts)
