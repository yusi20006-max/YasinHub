"""Yasin Interface — Phase 4 natural-language control surface (#96).

Channel-neutral conversational layer above the Control Plane.
Never bypasses policy, audit, or Control API.
"""

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
]
