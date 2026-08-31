"""Yasin-AI capability abstraction (#96/#99/#101/#110).

Configuration (env):
  YASIN_AI_PROVIDER = fake | null | openai | http | openai_compatible
  YASIN_AI_API_KEY  = secret (never logged)
  YASIN_AI_BASE_URL = HTTPS/HTTP OpenAI-compatible API root
  YASIN_AI_MODEL    = non-empty model name
  YASIN_AI_TIMEOUT  = seconds, 0 < timeout <= 120 (default 15)

Invalid or incomplete production configuration degrades to NullAIProvider.
Secrets are never included in logs or user-facing error messages.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from .ai_runtime import sanitize_ai_context
from .ai_runtime import ai_runtime_status as _status_impl

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_TIMEOUT = 15.0
_MAX_TIMEOUT = 120.0
_ALLOWED_PROVIDERS = {"fake", "test", "null", "none", "off", "disabled", "", "openai", "http", "openai_compatible"}


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


def _valid_base_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def _parse_timeout(value: str | None) -> float | None:
    if value is None or not value.strip():
        return _DEFAULT_TIMEOUT
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return None
    if not 0 < timeout <= _MAX_TIMEOUT:
        return None
    return timeout


class FakeAIProvider:
    def complete(self, *, system: str, user: str, context: Dict[str, Any]) -> AICompletion:
        if context and context.get("cancel_requested"):
            return AICompletion(
                text="AI request cancelled before provider call.",
                confidence=0.0,
                provider="fake",
                error="cancelled",
            )
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
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        timeout: float = _DEFAULT_TIMEOUT,
        name: str = "openai",
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key is required")
        if not _valid_base_url(base_url.strip()):
            raise ValueError("base_url must be an absolute HTTP(S) URL without credentials, query, or fragment")
        if not model.strip():
            raise ValueError("model is required")
        if not 0 < timeout <= _MAX_TIMEOUT:
            raise ValueError("timeout must be greater than 0 and at most 120 seconds")
        self._api_key = api_key
        self._base_url = base_url.strip().rstrip("/")
        self._model = model.strip()
        self._timeout = timeout
        self._name = name.strip() or "openai"

    def complete(self, *, system: str, user: str, context: Dict[str, Any]) -> AICompletion:
        if context and context.get("cancel_requested"):
            return AICompletion(
                text="AI request cancelled before provider call.",
                confidence=0.0,
                provider=self._name,
                error="cancelled",
            )
        safe_ctx_obj = sanitize_ai_context(context)
        safe_ctx = json.dumps(safe_ctx_obj, default=str)[:4000]
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
    if name not in _ALLOWED_PROVIDERS:
        logger.warning("ai_provider_invalid_config — using null")
        return NullAIProvider()
    if name in ("fake", "test"):
        return FakeAIProvider()
    if name in ("null", "none", "off", "disabled", ""):
        return NullAIProvider()

    api_key = (os.environ.get("YASIN_AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logger.info("ai_provider_selected=%s but credentials are unavailable — using null", name)
        return NullAIProvider()

    base_url = (
        os.environ.get("YASIN_AI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or _DEFAULT_BASE_URL
    ).strip()
    model = (os.environ.get("YASIN_AI_MODEL") or _DEFAULT_MODEL).strip()
    timeout = _parse_timeout(os.environ.get("YASIN_AI_TIMEOUT"))
    if not _valid_base_url(base_url) or not model or timeout is None:
        logger.warning("ai_provider_invalid_config provider=%s — using null", name)
        return NullAIProvider()

    return HttpAIProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        name=name if name != "openai_compatible" else "openai",
    )


_provider: Optional[AIProvider] = None


class _SafeAIProvider:
    """Wrap any provider with cancel + sanitize (#110)."""

    def __init__(self, inner: AIProvider) -> None:
        self._inner = inner

    def complete(self, *, system: str, user: str, context: Dict[str, Any]) -> AICompletion:
        if context and context.get("cancel_requested"):
            return AICompletion(
                text="AI request cancelled before provider call.",
                confidence=0.0,
                provider=getattr(self._inner, "_name", type(self._inner).__name__),
                error="cancelled",
            )
        safe = sanitize_ai_context(context)
        return self._inner.complete(system=system, user=user, context=safe)


def get_ai_provider() -> AIProvider:
    global _provider
    if _provider is None:
        if os.environ.get("YASIN_AI_PROVIDER"):
            raw = create_ai_provider_from_env()
        else:
            raw = FakeAIProvider()
        _provider = _SafeAIProvider(raw)
    return _provider


def ai_runtime_status() -> Dict[str, Any]:
    return _status_impl(
        lambda: get_ai_provider()._inner
        if isinstance(get_ai_provider(), _SafeAIProvider)
        else get_ai_provider()
    )


def set_ai_provider(provider: Optional[AIProvider]) -> None:
    global _provider
    if provider is None:
        _provider = None
    elif isinstance(provider, _SafeAIProvider):
        _provider = provider
    else:
        _provider = _SafeAIProvider(provider)


def reset_ai_provider_for_tests() -> None:
    global _provider
    _provider = None
