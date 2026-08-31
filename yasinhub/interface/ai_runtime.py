"""Production AI runtime helpers (#110).

Kept separate so providers and the interface engine share one sanitization path.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict

_SECRET_PATTERNS = [
    r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+",
    r"sk-[A-Za-z0-9]{10,}",
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",
]


def _redact(text: str) -> str:
    if not text:
        return text
    out = text
    for p in _SECRET_PATTERNS:
        out = re.sub(p, "[REDACTED]", out)
    return out


def sanitize_ai_context(context: Dict[str, Any] | None) -> Dict[str, Any]:
    if not context:
        return {}
    allowed_top = {
        "execution_id", "status", "task_id", "error", "sources", "github",
        "reconciliation", "recent_executions", "memory_hits", "session_id",
        "actor", "source", "channel", "intent_kind", "cancel_requested",
        "execution", "monday",
    }
    out: Dict[str, Any] = {}
    for key, value in context.items():
        if key not in allowed_top:
            continue
        if isinstance(value, str):
            out[key] = _redact(value)[: (500 if key == "error" else 2000)]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, list):
            out[key] = value[:20]
        elif isinstance(value, dict):
            slim = {}
            for sk, sv in list(value.items())[:20]:
                if isinstance(sv, str):
                    slim[str(sk)[:64]] = _redact(sv)[:500]
                elif isinstance(sv, (int, float, bool)) or sv is None:
                    slim[str(sk)[:64]] = sv
            out[key] = slim
    return out


def ai_runtime_status(get_provider) -> Dict[str, Any]:
    """get_provider is a callable to avoid circular imports."""
    provider = get_provider()
    name = type(provider).__name__
    configured = (os.environ.get("YASIN_AI_PROVIDER") or "").strip().lower()
    has_key = bool((os.environ.get("YASIN_AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip())
    status = "ready"
    if name == "NullAIProvider":
        status = "degraded"
    if name == "FakeAIProvider" and configured not in ("fake", "test", ""):
        status = "degraded"
    return {
        "provider_class": name,
        "configured_provider": configured or "default",
        "credentials_present": has_key,
        "status": status,
    }
