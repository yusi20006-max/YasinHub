"""monday.com configuration. Credentials are never stored in board items."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class MondayConfigError(ValueError):
    """Raised when monday configuration is invalid for live mode."""


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
    status_column_id: Optional[str] = None
    execution_id_column_id: Optional[str] = None
    github_issue_column_id: Optional[str] = None
    pr_column_id: Optional[str] = None
    ci_column_id: Optional[str] = None
    agent_column_id: Optional[str] = None
    result_column_id: Optional[str] = None
    correlation_column_id: Optional[str] = None
    status_ready_values: List[str] = field(default_factory=lambda: ["Ready", "ready", "READY"])
    status_map: Dict[str, str] = field(default_factory=dict)
    max_retries: int = 3
    retry_backoff_seconds: float = 0.5
    request_timeout_seconds: float = 30.0
    live_writes_enabled: bool = False

    def has_credentials(self) -> bool:
        return bool(self.api_token)

    def has_signing_secret(self) -> bool:
        return bool(self.signing_secret)

    def is_live_ready(self) -> bool:
        return bool(
            self.enabled
            and self.api_token
            and self.live_writes_enabled
            and self.status_column_id
        )

    def validate(self) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        if self.enabled and not self.api_token:
            issues.append("enabled=true but API token is missing")
        if self.live_writes_enabled and not self.api_token:
            issues.append("live_writes_enabled=true but API token is missing")
        if self.live_writes_enabled and not self.status_column_id:
            issues.append("live_writes_enabled=true but status_column_id is not configured")
        if self.max_retries < 0 or self.max_retries > 10:
            issues.append("max_retries must be between 0 and 10")
        if self.request_timeout_seconds <= 0 or self.request_timeout_seconds > 120:
            issues.append("request_timeout_seconds must be in (0, 120]")
        if self.retry_backoff_seconds < 0:
            issues.append("retry_backoff_seconds must be >= 0")
        return (len(issues) == 0, issues)

    def require_valid_for_live(self) -> None:
        ok, issues = self.validate()
        if not ok and self.live_writes_enabled:
            raise MondayConfigError("; ".join(issues))

    def as_safe_dict(self) -> Dict[str, Any]:
        ok, issues = self.validate()
        return {
            "enabled": self.enabled,
            "live_writes_enabled": self.live_writes_enabled,
            "live_ready": self.is_live_ready(),
            "config_valid": ok,
            "config_issues": issues,
            "webhook_path": self.webhook_path,
            "health_path": self.health_path,
            "sync_path": self.sync_path,
            "default_board_ids": list(self.default_board_ids),
            "status_column_id": self.status_column_id,
            "execution_id_column_id": self.execution_id_column_id,
            "github_issue_column_id": self.github_issue_column_id,
            "pr_column_id": self.pr_column_id,
            "ci_column_id": self.ci_column_id,
            "agent_column_id": self.agent_column_id,
            "result_column_id": self.result_column_id,
            "correlation_column_id": self.correlation_column_id,
            "has_api_token": bool(self.api_token),
            "has_signing_secret": bool(self.signing_secret),
            "max_retries": self.max_retries,
            "request_timeout_seconds": self.request_timeout_seconds,
        }


def _env_list(key: str) -> List[str]:
    raw = os.environ.get(key, "")
    if not raw.strip():
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_monday_config() -> MondayConfig:
    enabled = _env_bool("YASINHUB_MONDAY_ENABLED")
    token = os.environ.get("YASINHUB_MONDAY_API_TOKEN") or os.environ.get("MONDAY_API_TOKEN")
    secret = os.environ.get("YASINHUB_MONDAY_SIGNING_SECRET") or os.environ.get("MONDAY_SIGNING_SECRET")
    boards = _env_list("YASINHUB_MONDAY_BOARD_IDS")
    live = _env_bool("YASINHUB_MONDAY_LIVE_WRITES")

    return MondayConfig(
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
        max_retries=_env_int("YASINHUB_MONDAY_MAX_RETRIES", 3),
        retry_backoff_seconds=_env_float("YASINHUB_MONDAY_RETRY_BACKOFF", 0.5),
        request_timeout_seconds=_env_float("YASINHUB_MONDAY_TIMEOUT", 30.0),
        live_writes_enabled=live,
    )
