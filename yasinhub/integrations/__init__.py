"""External system integrations for YasinHub (monday.com, GitHub, etc.).

Adapters normalize external payloads into Yasin internal events and never
couple external systems directly to the Agent runtime.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .monday import MondayAdapter, MondayConfig

__all__ = [
    "MondayAdapter",
    "MondayConfig",
    "get_monday_adapter",
    "handle_monday_webhook",
]


def __getattr__(name: str):
    if name in ("MondayAdapter", "MondayConfig", "get_monday_adapter", "handle_monday_webhook"):
        from . import monday as _monday

        return getattr(_monday, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
