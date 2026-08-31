"""First-class channel adapter boundary (#99).

ChannelAdapter → Yasin Interface Engine

Adapters do not contain provider logic, policy, or Agent calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

from .engine import YasinInterface, get_yasin_interface
from .response import InterfaceResponse


@dataclass
class ChannelMessage:
    text: str
    channel: str
    source: str
    actor: Optional[str] = None
    yasin_user_id: Optional[str] = None
    slack_user_id: Optional[str] = None
    thread_id: Optional[str] = None
    channel_id: Optional[str] = None
    bot_user_id: Optional[str] = None
    require_mention: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(Protocol):
    def handle(self, message: ChannelMessage) -> InterfaceResponse:
        ...


class BaseChannelAdapter:
    channel_name: str = "unknown"

    def __init__(self, interface: Optional[YasinInterface] = None) -> None:
        self._interface = interface

    @property
    def interface(self) -> YasinInterface:
        return self._interface or get_yasin_interface()

    def handle(self, message: ChannelMessage) -> InterfaceResponse:
        return self.interface.handle(
            message.text,
            channel=message.channel or self.channel_name,
            source=message.source or self.channel_name,
            thread_id=message.thread_id,
            channel_id=message.channel_id,
            yasin_user_id=message.yasin_user_id or message.actor,
            slack_user_id=message.slack_user_id,
            actor=message.actor or message.yasin_user_id or message.slack_user_id or "anonymous",
            require_mention=message.require_mention,
            bot_user_id=message.bot_user_id,
        )


class SlackChannelAdapter(BaseChannelAdapter):
    channel_name = "slack"

    def handle(self, message: ChannelMessage) -> InterfaceResponse:
        message.require_mention = True
        message.channel = "slack"
        message.source = message.source or "slack"
        return super().handle(message)


class CLIChannelAdapter(BaseChannelAdapter):
    channel_name = "cli"

    def handle(self, message: ChannelMessage) -> InterfaceResponse:
        message.require_mention = False
        message.channel = "cli"
        message.source = message.source or "cli"
        return super().handle(message)


class PWAChannelAdapter(BaseChannelAdapter):
    channel_name = "pwa"

    def handle(self, message: ChannelMessage) -> InterfaceResponse:
        message.require_mention = False
        message.channel = "pwa"
        message.source = message.source or "pwa"
        return super().handle(message)


def get_channel_adapter(channel: str, interface: Optional[YasinInterface] = None) -> BaseChannelAdapter:
    ch = (channel or "").lower()
    if ch == "slack":
        return SlackChannelAdapter(interface)
    if ch == "cli":
        return CLIChannelAdapter(interface)
    if ch == "pwa":
        return PWAChannelAdapter(interface)
    return BaseChannelAdapter(interface)
