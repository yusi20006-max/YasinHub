"""Yasin-AI capability abstraction (#96/#99). Provider-agnostic.

Configuration (env):
  YASIN_AI_PROVIDER = fake | null | openai | http
  YASIN_AI_API_KEY  = secret (never logged)
  YASIN_AI_BASE_URL = e.g. https://api.openai.com/v1
  YASIN_AI_MODEL    = model name
  YASIN_AI_TIMEOUT  = seconds (default 15)

Missing credentials → NullAIProvider (system stays healthy).
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class AICompletion:
    text: str
    confidence: float = 0.5
    provider: str = "none"
    error: Optional[str] = None


class AIProvider(Protocol):
    def complete(self, *, system: str, user: str, context: Dict[str, Any]) -> AICompletion:
        ...


def _redact_secrets(text: str) -> str:
    if not text:
        return text
    patterns = [
        r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+",
        r"sk-[A-Za-z0-9]{10,}",
        r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",
    ]
    out = text
    for p in patterns:
        out = re.sub(p, "[REDACTED]", out)
    return out


class FakeAIProvider:
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


class HttpAIProvider:
    """OpenAI-compatible chat completions via stdlib urllib."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: float = 15.0,
        name: str = "openai",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._name = name

    def complete(self, *, system: str, user: str, context: Dict[str, Any]) -> AICompletion:
        ctx_summary = {
            k: v
            for k, v in context.items()
            if k
            in (
                "execution_id",
                "sources",
                "execution",
                "github",
                "monday",
                "reconciliation",
                "recent_executions",
            )
        }
        safe_ctx = json.dumps(ctx_summary, default=str)[:4000]
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"Context (JSON):\n{safe_ctx}\n\nRequest:\n{user[:2000]}",
                },
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }
        url = f"{self._base_url}/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            text = ""
            if choices:
                text = (choices[0].get("message") or {}).get("content") or ""
            text = _redact_secrets(text.strip())
            if not text:
                return AICompletion(
                    text="AI returned an empty response.",
                    confidence=0.2,
                    provider=self._name,
                    error="empty_response",
                )
            return AICompletion(text=text, confidence=0.65, provider=self._name)
        except urllib.error.HTTPError as exc:
            logger.warning("ai_http_error status=%s provider=%s", exc.code, self._name)
            return AICompletion(
                text="AI provider returned an error. YasinHub remains healthy.",
                confidence=0.0,
                provider=self._name,
                error=f"http_{exc.code}",
            )
        except urllib.error.URLError:
            logger.warning("ai_url_error provider=%s", self._name)
            return AICompletion(
                text="AI provider is unreachable. YasinHub remains healthy.",
                confidence=0.0,
                provider=self._name,
                error="unreachable",
            )
        except TimeoutError:
            logger.warning("ai_timeout provider=%s", self._name)
            return AICompletion(
                text="AI provider timed out. YasinHub remains healthy.",
                confidence=0.0,
                provider=self._name,
                error="timeout",
            )
        except Exception as exc:
            logger.warning("ai_provider_error provider=%s err=%s", self._name, type(exc).__name__)
            return AICompletion(
                text="AI capability encountered an error. YasinHub remains healthy.",
                confidence=0.0,
                provider=self._name,
                error=type(exc).__name__,
            )


def create_ai_provider_from_env() -> AIProvider:
    name = (os.environ.get("YASIN_AI_PROVIDER") or "null").strip().lower()
    if name in ("fake", "test"):
        return FakeAIProvider()
    if name in ("null", "none", "off", "disabled", ""):
        return NullAIProvider()

    api_key = (os.environ.get("YASIN_AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logger.info("ai_provider_selected=%s but no API key — using null", name)
        return NullAIProvider()

    base_url = (
        os.environ.get("YASIN_AI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).strip()
    model = (os.environ.get("YASIN_AI_MODEL") or "gpt-4o-mini").strip()
    try:
        timeout = float(os.environ.get("YASIN_AI_TIMEOUT") or "15")
    except ValueError:
        timeout = 15.0

    if name in ("openai", "http", "openai_compatible"):
        return HttpAIProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            name=name if name != "openai_compatible" else "openai",
        )

    logger.info("ai_provider_unknown name=%s — using openai-compatible HTTP", name)
    return HttpAIProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        name=name,
    )


_provider: Optional[AIProvider] = None


def get_ai_provider() -> AIProvider:
    global _provider
    if _provider is None:
        if os.environ.get("YASIN_AI_PROVIDER"):
            _provider = create_ai_provider_from_env()
        else:
            _provider = FakeAIProvider()
    return _provider


def set_ai_provider(provider: Optional[AIProvider]) -> None:
    global _provider
    _provider = provider


def reset_ai_provider_for_tests() -> None:
    global _provider
    _provider = None
