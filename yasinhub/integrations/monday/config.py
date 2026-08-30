"""monday.com configuration. Credentials are never stored in board items."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MondayConfig:
    """Runtime configuration for the monday integration.

    Secrets come exclusively from environment / secure config store.
    """

    enabled: bool = False
    api_token: Optional[str] = None
    signing_secret: Optional[str] = None
    webhook_path: str = "/v1/integrations/monday/webhook"
    health_path: str = "/v1/integrations/monday/health"
    sync_path: str = "/v1/integrations/monday/sync"
    default_board_ids: List[str] = field(default_factory=list)
    # Configurable column mapping (board-agnostic)
    status_column_id: Optional[str] = None
    execution_id_column_id: Optional[str] = None
    github_issue_column_id: Optional[str] = None
    pr_column_id: Optional[str] = None
    ci_column_id: Optional[str] = None
    agent_column_id: Optional[str] = None
    result_column_id: Optional[str] = None
    correlation_column_id: Optional[str] = None
    # Status value mapping (monday label -> internal)
    status_ready_values: List[str] = field(default_factory=lambda: ["Ready", "ready", "READY"])
    status_map: Dict[str, str] = field(default_factory=dict)

    def has_credentials(self) -> bool:
        return bool(self.api_token)

    def has_signing_secret(self) -> bool:
        return bool(self.signing_secret)

    def as_safe_dict(self) -> Dict[str, Any]:
        """Public view — never includes secrets."""
        return {
            "enabled": self.enabled,
            "webhook_path": self.webhook_path,
            "health_path": self.health_path,
            "sync_path": self.sync_path,
            "default_board_ids": list(self.default_board_ids),
            "status_column_id": self.status_column_id,
            "has_api_token": bool(self.api_token),
            "has_signing_secret": bool(self.signing_secret),
        }


def _env_list(key: str) -> List[str]:
    raw = os.environ.get(key, "")
    if not raw.strip():
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def get_monday_config() -> MondayConfig:
    """Load monday config from environment (highest priority for secrets)."""
    enabled = os.environ.get("YASINHUB_MONDAY_ENABLED", "").lower() in ("1", "true", "yes")
    token = os.environ.get("YASINHUB_MONDAY_API_TOKEN") or os.environ.get("MONDAY_API_TOKEN")
    secret = os.environ.get("YASINHUB_MONDAY_SIGNING_SECRET") or os.environ.get("MONDAY_SIGNING_SECRET")
    boards = _env_list("YASINHUB_MONDAY_BOARD_IDS")

    cfg = MondayConfig(
        enabled=enabled or bool(token),
        api_token=token,
        signing_secret=secret,
        default_board_ids=boards,
        status_column_id=os.environ.get("YASINHUB_MONDAY_STATUS_COLUMN"),
        execution_id_column_id=os.environ.get("YASINHUB_MONDAY_EXECUTION_ID_COLUMN"),
        github_issue_column_id=os.environ.get("YASINHUB_MONDAY_GITHUB_ISSUE_COLUMN"),
        pr_column_id=os.environ.get("YASINHUB_MONDAY_PR_COLUMN"),
        ci_column_id=os.environ.get("YASINHUB_MONDAY_CI_COLUMN"),
        agent_column_id=os.environ.get("YASINHUB_MONDAY_AGENT_COLUMN"),
        result_column_id=os.environ.get("YASINHUB_MONDAY_RESULT_COLUMN"),
        correlation_column_id=os.environ.get("YASINHUB_MONDAY_CORRELATION_COLUMN"),
    )
    return cfg
