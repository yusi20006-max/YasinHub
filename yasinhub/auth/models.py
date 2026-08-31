"""Shared identity models for HTTP authentication."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Role(str, Enum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    DEVELOPER = "DEVELOPER"
    ADMIN = "ADMIN"


class AuthMode(str, Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"


class AuthError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 401) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class YasinPrincipal:
    """Authenticated principal mapped into the existing role model."""

    yasin_user_id: str
    role: Role
    source: str = "http"
    auth_method: str = "token"
    display_name: Optional[str] = None


@dataclass(frozen=True)
class AuthContext:
    principal: YasinPrincipal
    mode: AuthMode
    authenticated: bool

    @property
    def actor(self) -> str:
        return self.principal.yasin_user_id

    @property
    def role(self) -> Role:
        return self.principal.role
