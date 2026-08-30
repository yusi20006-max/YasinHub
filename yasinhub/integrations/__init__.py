"""External system integrations for YasinHub (monday.com, GitHub, etc.).

Adapters normalize external payloads into Yasin internal events and never
couple external systems directly to the Agent runtime.
"""

from .monday import (
    MondayAdapter,
    MondayConfig,
    get_monday_adapter,
    handle_monday_webhook,
)

__all__ = [
    "MondayAdapter",
    "MondayConfig",
    "get_monday_adapter",
    "handle_monday_webhook",
]
