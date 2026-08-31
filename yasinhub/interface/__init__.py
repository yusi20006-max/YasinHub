"""Yasin Interface — Phase 4 natural-language control surface (#96/#99)."""

from .adapters import (
    BaseChannelAdapter,
    ChannelMessage,
    CLIChannelAdapter,
    PWAChannelAdapter,
    SlackChannelAdapter,
    get_channel_adapter,
)
from .engine import YasinInterface, get_yasin_interface
from .intents import Intent, IntentKind
from .response import InterfaceResponse
from .session import Session, SessionStore, get_session_store

__all__ = [
    "YasinInterface",
    "get_yasin_interface",
    "Intent",
    "IntentKind",
    "InterfaceResponse",
    "Session",
    "SessionStore",
    "get_session_store",
    "ChannelMessage",
    "BaseChannelAdapter",
    "SlackChannelAdapter",
    "CLIChannelAdapter",
    "PWAChannelAdapter",
    "get_channel_adapter",
]
