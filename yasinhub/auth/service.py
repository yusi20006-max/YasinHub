"""Token authentication service for HTTP/PWA/Control surfaces."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from typing import Dict, Mapping, Optional, Tuple

from .models import AuthContext, AuthError, AuthMode, Role, YasinPrincipal

logger = logging.getLogger(__name__)

# In-memory token table for tests; production uses env only.
_test_tokens: Optional[Dict[str, YasinPrincipal]] = None
_test_mode: Optional[AuthMode] = None

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-.=+/]{8,512}$")


def reset_auth_for_tests(
    *,
    mode: Optional[AuthMode] = None,
    tokens: Optional[Dict[str, YasinPrincipal]] = None,
) -> None:
    global _test_tokens, _test_mode
    _test_mode = mode
    _test_tokens = dict(tokens) if tokens is not None else None


def get_auth_mode() -> AuthMode:
    if _test_mode is not None:
        return _test_mode
    raw = (os.environ.get("YASIN_AUTH_MODE") or "").strip().lower()
    if raw in ("production", "prod"):
        return AuthMode.PRODUCTION
    if raw in ("test", "testing"):
        return AuthMode.TEST
    if raw in ("development", "dev", "local"):
        return AuthMode.DEVELOPMENT
    # Explicit production tokens without mode still force production enforcement.
    if (os.environ.get("YASIN_AUTH_TOKENS") or "").strip():
        return AuthMode.PRODUCTION
    return AuthMode.DEVELOPMENT


def _parse_role(value: str) -> Optional[Role]:
    v = (value or "").strip().upper()
    for role in Role:
        if role.value == v:
            return role
    return None


def load_token_principals() -> Dict[str, YasinPrincipal]:
    """Load bearer-token \u2192 principal map.

    Format (comma-separated):
      YASIN_AUTH_TOKENS=tok_abc:admin:alice,tok_def:operator:bob

    Each entry: token:role[:yasin_user_id]
    Tokens are never logged.
    """
    if _test_tokens is not None:
        return dict(_test_tokens)

    raw = (os.environ.get("YASIN_AUTH_TOKENS") or "").strip()
    mapping: Dict[str, YasinPrincipal] = {}
    if not raw:
        return mapping
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        bits = [b.strip() for b in part.split(":")]
        if len(bits) < 2:
            continue
        token, role_s = bits[0], bits[1]
        role = _parse_role(role_s)
        if not token or role is None:
            continue
        if not _TOKEN_RE.match(token):
            continue
        user_id = bits[2] if len(bits) >= 3 and bits[2] else f"user-{_token_fingerprint(token)}"
        mapping[token] = YasinPrincipal(
            yasin_user_id=user_id,
            role=role,
            source="http",
            auth_method="bearer_token",
        )
    return mapping


def _token_fingerprint(token: str) -> str:
    """Non-reversible short id for logs (never the token itself)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


def _extract_bearer(headers: Mapping) -> Optional[str]:
    if headers is None:
        return None
    auth = None
    if hasattr(headers, "get"):
        auth = headers.get("Authorization") or headers.get("authorization")
    if not auth:
        return None
    auth = str(auth).strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def resolve_bearer_token(token: Optional[str]) -> Optional[YasinPrincipal]:
    if not token:
        return None
    principals = load_token_principals()
    for configured, principal in principals.items():
        if hmac.compare_digest(configured, token):
            return principal
    return None


def authenticate_http(
    headers: Mapping,
    *,
    body_actor: Optional[str] = None,
    require_auth: Optional[bool] = None,
) -> AuthContext:
    """Authenticate an HTTP request.

    Production: Bearer token required; soft actors rejected.
    Development/Test: token accepted when present; otherwise soft actor allowed
    only when require_auth is False (explicit non-production path).
    """
    mode = get_auth_mode()
    enforce = require_auth if require_auth is not None else (mode == AuthMode.PRODUCTION)

    token = _extract_bearer(headers)
    if token:
        principal = resolve_bearer_token(token)
        if principal is None:
            logger.warning(
                "auth_failed reason=invalid_token mode=%s fp=%s",
                mode.value,
                _token_fingerprint(token),
            )
            raise AuthError("invalid_token", "authentication required", status=401)
        return AuthContext(principal=principal, mode=mode, authenticated=True)

    if enforce:
        logger.warning("auth_failed reason=missing_token mode=%s", mode.value)
        raise AuthError("missing_token", "authentication required", status=401)

    actor = (body_actor or "").strip() or "dev-user"
    soft_role = Role.VIEWER
    if mode == AuthMode.TEST:
        soft_role = Role.OPERATOR
    principal = YasinPrincipal(
        yasin_user_id=actor,
        role=soft_role,
        source="http",
        auth_method="soft_dev",
    )
    return AuthContext(principal=principal, mode=mode, authenticated=False)
