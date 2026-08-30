"""
Slack integration boundary for YasinHub.

Slack is an operational interface only. YasinHub remains the Control Plane
and source of truth. Requests never bypass YasinHub to reach Yasin-Agent.
"""

from .config import SlackConfig, load_slack_config, is_slack_enabled
from .verification import verify_slack_request, SlackVerificationError
from .client import SlackClient, SlackClientError, NullSlackClient
from .events import (
    SlackInboundEvent,
    normalize_slack_event,
    SlackEventType,
)
from .adapter import SlackAdapter, get_slack_adapter, set_slack_adapter

__all__ = [
    "SlackConfig",
    "load_slack_config",
    "is_slack_enabled",
    "verify_slack_request",
    "SlackVerificationError",
    "SlackClient",
    "SlackClientError",
    "NullSlackClient",
    "SlackInboundEvent",
    "normalize_slack_event",
    "SlackEventType",
    "SlackAdapter",
    "get_slack_adapter",
    "set_slack_adapter",
]
