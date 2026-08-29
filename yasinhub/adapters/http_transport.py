"""
HTTP transport for Agent \u2194 Hub integration (#59).

Hub acts as an authenticated HTTP client against a remote Agent runtime.
Credentials come from environment only \u2014 never embedded in source or frontend.
Transport is replaceable; Observer routes stay transport-agnostic.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode, urljoin

logger = logging.getLogger(__name__)


class TransportError(Exception):
    """Base transport failure."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        retryable: bool = False,
        body: Any = None,
    ):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.body = body


class AuthenticationError(TransportError):
    """Service authentication failed (401/403)."""

    def __init__(self, message: str = "authentication failed", *, status: int = 401):
        super().__init__(message, status=status, retryable=False)


class TransportUnavailable(TransportError):
    """Remote runtime unreachable or unhealthy."""

    def __init__(self, message: str = "agent runtime unavailable"):
        super().__init__(message, status=None, retryable=True)


@dataclass
class HttpTransportConfig:
    """Configuration loaded from environment / explicit args."""

    base_url: str
    service_token: str
    timeout_seconds: float = 10.0
    connect_retries: int = 2
    retry_backoff_seconds: float = 0.25
    user_agent: str = "YasinHub-AgentTransport/1.0"
    health_path: str = "/v1/health"
    stale_after_seconds: float = 30.0

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> Optional["HttpTransportConfig"]:
        e = env if env is not None else os.environ
        base = (e.get("YASINHUB_AGENT_BASE_URL") or "").strip().rstrip("/")
        token = (e.get("YASINHUB_AGENT_SERVICE_TOKEN") or "").strip()
        if not base or not token:
            return None
        timeout = float(e.get("YASINHUB_AGENT_TIMEOUT", "10") or "10")
        retries = int(e.get("YASINHUB_AGENT_RETRIES", "2") or "2")
        return cls(base_url=base, service_token=token, timeout_seconds=timeout, connect_retries=retries)


@dataclass
class ConnectionHealth:
    healthy: bool = False
    last_ok_at: Optional[float] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    last_status: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "last_ok_at": self.last_ok_at,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "last_status": self.last_status,
            "stale": self.is_stale(),
        }

    def is_stale(self, threshold: float = 30.0) -> bool:
        if self.last_ok_at is None:
            return True
        return (time.time() - self.last_ok_at) > threshold


class HttpTransportClient:
    """Authenticated HTTP client for service-to-service Agent access."""

    def __init__(self, config: HttpTransportConfig, *, opener: Any = None) -> None:
        self.config = config
        self._opener = opener
        self._health = ConnectionHealth()
        self._lock = threading.RLock()
        self._idempotency_cache: Dict[Tuple[str, str, str], Tuple[int, Any]] = {}
        self._seen_event_ids: set = set()

    @property
    def health(self) -> ConnectionHealth:
        return self._health

    def is_stale(self) -> bool:
        return self._health.is_stale(self.config.stale_after_seconds)

    def _headers(
        self,
        *,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        content_type: bool = False,
    ) -> Dict[str, str]:
        h = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.service_token}",
            "User-Agent": self.config.user_agent,
        }
        if request_id:
            h["X-Request-Id"] = request_id
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        if content_type:
            h["Content-Type"] = "application/json"
        return h

    def _url(self, path: str, query: Optional[Dict[str, Any]] = None) -> str:
        base = self.config.base_url.rstrip("/") + "/"
        full = urljoin(base, path.lstrip("/"))
        if query:
            q = {k: v for k, v in query.items() if v is not None and v != ""}
            if q:
                full = full + ("&" if "?" in full else "?") + urlencode(q)
        return full

    def _record_success(self, status: int) -> None:
        with self._lock:
            self._health.healthy = True
            self._health.last_ok_at = time.time()
            self._health.last_error = None
            self._health.consecutive_failures = 0
            self._health.last_status = status

    def _record_failure(self, err: str, status: Optional[int] = None) -> None:
        with self._lock:
            self._health.healthy = False
            self._health.last_error = err
            self._health.consecutive_failures += 1
            self._health.last_status = status

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[int, Any]:
        method = method.upper()
        if method in ("POST", "PUT", "PATCH") and idempotency_key:
            cache_key = (method, path, idempotency_key)
            with self._lock:
                if cache_key in self._idempotency_cache:
                    return self._idempotency_cache[cache_key]

        url = self._url(path, query)
        data = None
        headers = self._headers(
            request_id=request_id,
            idempotency_key=idempotency_key,
            content_type=body is not None,
        )
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        last_err: Optional[Exception] = None
        attempts = max(1, self.config.connect_retries + 1)
        for attempt in range(attempts):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                if self._opener is not None:
                    resp = self._opener.open(req, timeout=self.config.timeout_seconds)
                else:
                    resp = urllib.request.urlopen(req, timeout=self.config.timeout_seconds)
                with resp:
                    status = getattr(resp, "status", None) or resp.getcode()
                    raw = resp.read().decode("utf-8") if resp.readable() else ""
                parsed: Any = None
                if raw:
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError:
                        parsed = {"raw": raw}
                self._record_success(int(status))
                result = (int(status), parsed)
                if method in ("POST", "PUT", "PATCH") and idempotency_key:
                    with self._lock:
                        self._idempotency_cache[(method, path, idempotency_key)] = result
                return result
            except urllib.error.HTTPError as e:
                status = e.code
                try:
                    err_body = e.read().decode("utf-8")
                    err_json = json.loads(err_body) if err_body else {}
                except Exception:
                    err_json = {}
                msg = (
                    (err_json.get("detail") or err_json.get("error") or err_json.get("message"))
                    if isinstance(err_json, dict)
                    else None
                ) or str(e)
                if status in (401, 403):
                    self._record_failure(str(msg), status)
                    raise AuthenticationError(str(msg), status=status) from e
                if status >= 500:
                    last_err = TransportError(str(msg), status=status, retryable=True, body=err_json)
                    self._record_failure(str(msg), status)
                    if attempt + 1 < attempts:
                        time.sleep(self.config.retry_backoff_seconds * (attempt + 1))
                        continue
                    raise last_err from e
                self._record_failure(str(msg), status)
                raise TransportError(str(msg), status=status, retryable=False, body=err_json) from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = TransportUnavailable(str(e.reason if hasattr(e, "reason") else e))
                self._record_failure(str(last_err))
                if attempt + 1 < attempts:
                    time.sleep(self.config.retry_backoff_seconds * (attempt + 1))
                    continue
                raise last_err from e

        raise last_err or TransportUnavailable("request failed")

    def get_json(self, path: str, *, query: Optional[Dict[str, Any]] = None, request_id: Optional[str] = None) -> Any:
        status, data = self.request("GET", path, query=query, request_id=request_id)
        if status >= 400:
            raise TransportError(f"GET {path} failed", status=status)
        return data

    def post_json(
        self,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        *,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[int, Any]:
        return self.request(
            "POST",
            path,
            body=body or {},
            request_id=request_id,
            idempotency_key=idempotency_key,
        )

    def check_health(self) -> ConnectionHealth:
        try:
            self.get_json(self.config.health_path)
        except Exception as e:
            self._record_failure(str(e))
        return self.health

    def remember_event_id(self, event_id: str) -> bool:
        """Return True if this event_id is new (should be processed)."""
        if not event_id:
            return True
        with self._lock:
            if event_id in self._seen_event_ids:
                return False
            self._seen_event_ids.add(event_id)
            if len(self._seen_event_ids) > 10000:
                self._seen_event_ids = set(list(self._seen_event_ids)[5000:])
            return True


__all__ = [
    "HttpTransportConfig",
    "HttpTransportClient",
    "ConnectionHealth",
    "TransportError",
    "AuthenticationError",
    "TransportUnavailable",
]
