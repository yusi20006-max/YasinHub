"""Production authentication boundary for YasinHub HTTP surfaces.

Authentication establishes identity only. Authorization remains with Policy.
Slack continues to use HMAC + Slack identity mapping; this module covers
HTTP/PWA/Control API paths.
"""

from .models import AuthContext, AuthError, AuthMode, Role, YasinPrincipal
from .service import (
    authenticate_http,
    get_auth_mode,
    load_token_principals,
    reset_auth_for_tests,
    resolve_bearer_token,
)

__all__ = [
    "AuthContext",
    "AuthError",
    "AuthMode",
    "Role",
    "YasinPrincipal",
    "authenticate_http",
    "get_auth_mode",
    "load_token_principals",
    "reset_auth_for_tests",
    "resolve_bearer_token",
]
