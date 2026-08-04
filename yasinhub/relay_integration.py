from __future__ import annotations
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from yasin_relay.sdk import YasinRelayClient
    HAS_YASIN_RELAY = True
except ImportError:
    YasinRelayClient = None
    HAS_YASIN_RELAY = False


class RelayIntegration:
    def __init__(self, client: Optional[Any] = None) -> None:
        self.client = client
        self.connected = client is not None
        self.connection_error: Optional[str] = None

        if self.connected:
            return

        if not HAS_YASIN_RELAY:
            self.connection_error = "yasin_relay یافت نشد یا نصب نیست"
            return

        try:
            self.client = YasinRelayClient()
            self.connected = True
        except Exception as e:
            self.connected = False
            self.connection_error = str(e)

    def connect(self) -> bool:
        if not self.connected or not self.client:
            return False
        try:
            return bool(self.client.connect())
        except Exception as e:
            self.connection_error = str(e)
            # عمدا connected را False نمی‌کنیم تا get_status روی کلاینت تست شود
            return False

    def get_status(self) -> Dict[str, Any]:
        if not self.connected or not self.client:
            return {
                "status": "unknown",
                "connected": False,
                "error": self.connection_error or "yasin_relay یافت نشد یا نصب نیست",
            }

        try:
            data = self.client.get_status()
            if isinstance(data, dict):
                return data
            return {"status": "unknown", "connected": True}
        except Exception as e:
            self.connection_error = str(e)
            return {"status": "error", "connected": self.connected, "error": str(e)}

    def handle_event(self, event_type: str, payload: Dict[str, Any]) -> bool:
        if not self.connected or not self.client:
            return False
        try:
            return bool(self.client.handle_event(event_type, payload))
        except Exception as e:
            self.connection_error = str(e)
            return False
