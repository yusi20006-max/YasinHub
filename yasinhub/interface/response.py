"""Structured interface response model (#96/#99)."""

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
            parts.append("Reply `@Yasin confirm <token>` or use the buttons below.")
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

    def to_slack_blocks(self) -> list:
        """Block Kit payload; value is token only — not authorization."""
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": self.answer or " "},
            }
        ]
        if self.confirmation_required and self.confirmation_token:
            summary = self.confirmation_summary or "pending control action"
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Confirmation required:* {summary}\nToken: `{self.confirmation_token}`",
                    },
                }
            )
            blocks.append(
                {
                    "type": "actions",
                    "block_id": f"yasin_confirm_{self.confirmation_token}",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Confirm"},
                            "style": "primary",
                            "action_id": "yasin_confirm",
                            "value": self.confirmation_token,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Cancel"},
                            "style": "danger",
                            "action_id": "yasin_cancel",
                            "value": self.confirmation_token,
                        },
                    ],
                }
            )
        elif self.suggested_next_actions:
            actions = "\n".join(f"• {a}" for a in self.suggested_next_actions[:5])
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Suggested next actions:*\n{actions}"},
                }
            )
        return blocks
