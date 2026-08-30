"""
Environment-driven Slack configuration.

Secrets are never logged or returned in plain form by public helpers.
Slack remains fully optional; missing configuration disables the integration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class SlackConfig:
    """Immutable Slack integration settings loaded from the environment."""

    enabled: bool = False
    bot_token: str = ""
    signing_secret: str = ""
    app_token: str = ""  # optional socket-mode / advanced
    default_channel: str = "#yasin"
    alerts_channel: str = "#yasin-alerts"
    agent_channel: str = "#yasin-agent"
    feature_commands: bool = True
    feature_notifications: bool = True
    feature_interactive: bool = True
    request_timestamp_max_age_seconds: int = 60 * 5  # 5 minutes replay window
    extra: Dict[str, str] = field(default_factory=dict)

    def has_credentials(self) -> bool:
        return bool(self.bot_token and self.signing_secret)

    def safe_dict(self) -> Dict[str, object]:
        """Return a redacted view suitable for logging/diagnostics."""
        return {
            "enabled": self.enabled,
            "has_bot_token": bool(self.bot_token),
            "has_signing_secret": bool(self.signing_secret),
            "has_app_token": bool(self.app_token),
            "default_channel": self.default_channel,
            "alerts_channel": self.alerts_channel,
            "agent_channel": self.agent_channel,
            "feature_commands": self.feature_commands,
            "feature_notifications": self.feature_notifications,
            "feature_interactive": self.feature_interactive,
            "request_timestamp_max_age_seconds": self.request_timestamp_max_age_seconds,
        }


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_slack_config() -> SlackConfig:
    """
    Load Slack configuration from environment variables.

    Supported variables:
      YASIN_SLACK_ENABLED
      YASIN_SLACK_BOT_TOKEN
      YASIN_SLACK_SIGNING_SECRET
      YASIN_SLACK_APP_TOKEN
      YASIN_SLACK_DEFAULT_CHANNEL
      YASIN_SLACK_ALERTS_CHANNEL
      YASIN_SLACK_AGENT_CHANNEL
      YASIN_SLACK_FEATURE_COMMANDS
      YASIN_SLACK_FEATURE_NOTIFICATIONS
      YASIN_SLACK_FEATURE_INTERACTIVE
      YASIN_SLACK_TIMESTAMP_MAX_AGE
    """
    enabled_flag = _env_bool("YASIN_SLACK_ENABLED", False)
    bot_token = (os.environ.get("YASIN_SLACK_BOT_TOKEN") or "").strip()
    signing_secret = (os.environ.get("YASIN_SLACK_SIGNING_SECRET") or "").strip()

    # Auto-enable when credentials are present unless explicitly disabled
    if not enabled_flag and bot_token and signing_secret:
        enabled_flag = True
    if enabled_flag and not (bot_token and signing_secret):
        # Explicit enable without credentials → treat as disabled
        enabled_flag = False

    try:
        max_age = int(os.environ.get("YASIN_SLACK_TIMESTAMP_MAX_AGE", "300"))
    except ValueError:
        max_age = 300

    return SlackConfig(
        enabled=enabled_flag,
        bot_token=bot_token,
        signing_secret=signing_secret,
        app_token=(os.environ.get("YASIN_SLACK_APP_TOKEN") or "").strip(),
        default_channel=(os.environ.get("YASIN_SLACK_DEFAULT_CHANNEL") or "#yasin").strip(),
        alerts_channel=(os.environ.get("YASIN_SLACK_ALERTS_CHANNEL") or "#yasin-alerts").strip(),
        agent_channel=(os.environ.get("YASIN_SLACK_AGENT_CHANNEL") or "#yasin-agent").strip(),
        feature_commands=_env_bool("YASIN_SLACK_FEATURE_COMMANDS", True),
        feature_notifications=_env_bool("YASIN_SLACK_FEATURE_NOTIFICATIONS", True),
        feature_interactive=_env_bool("YASIN_SLACK_FEATURE_INTERACTIVE", True),
        request_timestamp_max_age_seconds=max(30, max_age),
    )


def is_slack_enabled(config: Optional[SlackConfig] = None) -> bool:
    cfg = config if config is not None else load_slack_config()
    return bool(cfg.enabled and cfg.has_credentials())
