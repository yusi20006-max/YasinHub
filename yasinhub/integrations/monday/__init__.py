"""monday.com integration adapter for YasinHub.

Keeps monday-specific types isolated. Emits normalized internal events only.
Does not dispatch Agents.
"""

from .config import MondayConfig, get_monday_config
from .adapter import MondayAdapter, get_monday_adapter
from .webhook import handle_monday_webhook, verify_monday_challenge
from .models import MondayNormalizedEvent, MondayItemRef

__all__ = [
    "MondayConfig",
    "get_monday_config",
    "MondayAdapter",
    "get_monday_adapter",
    "handle_monday_webhook",
    "verify_monday_challenge",
    "MondayNormalizedEvent",
    "MondayItemRef",
]
