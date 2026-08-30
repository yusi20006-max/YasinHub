"""
Slack identity mapping and role-based authorization.

Slack User ID → Yasin Identity → Role → permission check.
Never authorize based on display names.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Set


class SlackRole(str, Enum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    DEVELOPER = "DEVELOPER"
    ADMIN = "ADMIN"


COMMAND_PERMISSIONS: Dict[str, Set[SlackRole]] = {
    "status": {SlackRole.VIEWER, SlackRole.OPERATOR, SlackRole.DEVELOPER, SlackRole.ADMIN},
    "health": {SlackRole.VIEWER, SlackRole.OPERATOR, SlackRole.DEVELOPER, SlackRole.ADMIN},
    "executions": {SlackRole.VIEWER, SlackRole.OPERATOR, SlackRole.DEVELOPER, SlackRole.ADMIN},
    "execution": {SlackRole.VIEWER, SlackRole.OPERATOR, SlackRole.DEVELOPER, SlackRole.ADMIN},
    "help": {SlackRole.VIEWER, SlackRole.OPERATOR, SlackRole.DEVELOPER, SlackRole.ADMIN},
    "run": {SlackRole.OPERATOR, SlackRole.DEVELOPER, SlackRole.ADMIN},
    "cancel": {SlackRole.OPERATOR, SlackRole.DEVELOPER, SlackRole.ADMIN},
    "retry": {SlackRole.OPERATOR, SlackRole.DEVELOPER, SlackRole.ADMIN},
}


@dataclass(frozen=True)
class YasinIdentity:
    """Mapped Yasin identity for a Slack user."""

    yasin_user_id: str
    role: SlackRole
    slack_user_id: str
    display_name: Optional[str] = None  # informational only — never used for authz


class AuthorizationError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _parse_role(value: str) -> Optional[SlackRole]:
    v = (value or "").strip().upper()
    for role in SlackRole:
        if role.value == v:
            return role
    return None


def load_identity_map_from_env() -> Dict[str, YasinIdentity]:
    """
    Load Slack User ID → identity mapping from environment.

    Format (comma-separated entries):
      YASIN_SLACK_IDENTITY_MAP=U123:admin:alice,U456:operator:bob

    Each entry: slack_user_id:role[:optional_yasin_user_id]
    """
    raw = (os.environ.get("YASIN_SLACK_IDENTITY_MAP") or "").strip()
    mapping: Dict[str, YasinIdentity] = {}
    if not raw:
        return mapping
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        bits = [b.strip() for b in part.split(":")]
        if len(bits) < 2:
            continue
        slack_id = bits[0]
        role = _parse_role(bits[1])
        if not slack_id or role is None:
            continue
        yasin_id = bits[2] if len(bits) >= 3 and bits[2] else slack_id
        mapping[slack_id] = YasinIdentity(
            yasin_user_id=yasin_id,
            role=role,
            slack_user_id=slack_id,
        )
    return mapping


class IdentityStore:
    """In-process identity map; can be replaced/extended later."""

    def __init__(self, mapping: Optional[Dict[str, YasinIdentity]] = None) -> None:
        self._map = dict(mapping) if mapping is not None else load_identity_map_from_env()

    def resolve(self, slack_user_id: Optional[str]) -> Optional[YasinIdentity]:
        if not slack_user_id:
            return None
        return self._map.get(slack_user_id)

    def register(self, identity: YasinIdentity) -> None:
        self._map[identity.slack_user_id] = identity


def authorize_command(
    identity: Optional[YasinIdentity],
    command: str,
) -> YasinIdentity:
    """Ensure the identity may execute the given command. Raises AuthorizationError."""
    if identity is None:
        raise AuthorizationError("unmapped_slack_user")
    cmd = (command or "").lstrip("/").lower().strip()
    allowed = COMMAND_PERMISSIONS.get(cmd)
    if allowed is None:
        raise AuthorizationError("unknown_command")
    if identity.role not in allowed:
        raise AuthorizationError("forbidden")
    return identity
