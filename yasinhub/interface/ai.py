"""Yasin-AI capability abstraction (#96). Provider-agnostic; tests use FakeAI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class AICompletion:
    text: str
    confidence: float = 0.5
    provider: str = "none"
    error: Optional[str] = None


class AIProvider(Protocol):
    def complete(self, *, system: str, user: str, context: Dict[str, Any]) -> AICompletion:
        ...


class FakeAIProvider:
    """Deterministic AI for tests — no network, no credentials."""

    def complete(self, *, system: str, user: str, context: Dict[str, Any]) -> AICompletion:
        eid = context.get("execution_id") or (context.get("execution") or {}).get("execution_id")
        status = (context.get("execution") or {}).get("status")
        error = (context.get("execution") or {}).get("error")
        if eid and status:
            parts = [f"Execution `{eid}` is currently *{status}*."]
            if error:
                parts.append(f"Recorded error: {error}")
            if context.get("reconciliation"):
                parts.append(f"Reconciliation findings: {len(context['reconciliation'])}.")
            return AICompletion(text=" ".join(parts), confidence=0.7, provider="fake")
        if context.get("github"):
            pr = context["github"].get("pr")
            return AICompletion(
                text=f"GitHub PR #{pr}: limited local correlation data available.",
                confidence=0.5,
                provider="fake",
            )
        if context.get("recent_executions"):
            n = len(context["recent_executions"])
            return AICompletion(
                text=f"There are {n} recent execution(s) visible to YasinHub.",
                confidence=0.6,
                provider="fake",
            )
        return AICompletion(
            text="I could not gather enough context to answer confidently.",
            confidence=0.3,
            provider="fake",
        )


class NullAIProvider:
    def complete(self, *, system: str, user: str, context: Dict[str, Any]) -> AICompletion:
        return AICompletion(
            text="AI capability unavailable.",
            confidence=0.0,
            provider="null",
            error="not_configured",
        )


_provider: Optional[AIProvider] = None


def get_ai_provider() -> AIProvider:
    global _provider
    if _provider is None:
        _provider = FakeAIProvider()
    return _provider


def set_ai_provider(provider: Optional[AIProvider]) -> None:
    global _provider
    _provider = provider
