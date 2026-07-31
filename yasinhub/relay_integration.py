"""
relay_integration.py
لایه یکپارچه‌سازی YasinHub با Yasin-Relay از طریق SDK عمومی.
"""

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
    """
    لایه تعامل و مدیریت ارتباط YasinHub با Yasin-Relay.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        self.client: Optional[Any] = None
        self.connected: bool = False
        self.connection_error: Optional[str] = None

        if client is not None:
            self.client = client
            self.connected = True
        elif HAS_YASIN_RELAY:
            try:
                self.client = YasinRelayClient()
                self.connected = True
            except Exception as e:
                self.client = None
                self.connected = False
                self.connection_error = f"خطا در مقداردهی اولیه کلاینت رله: {str(e)}"
        else:
            self.connection_error = "کتابخانه yasin_relay یافت نشد یا نصب نیست"

    def connect(self) -> bool:
        """
        برقراری ارتباط با سرویس رله.
        """
        if not self.connected or self.client is None:
            logger.warning("کلاینت متصل نیست؛ امکان برقراری ارتباط وجود ندارد.")
            return False
        try:
            return self.client.connect()
        except Exception as e:
            logger.error(f"خطا در برقراری ارتباط با سرویس رله: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        دریافت وضعیت و مانیتورینگ سرویس رله.
        """
        if not self.connected or self.client is None:
            return {"status": "unknown", "error": self.connection_error}
        try:
            return self.client.get_status()
        except Exception as e:
            logger.error(f"خطا در دریافت وضعیت سرویس رله: {e}")
            return {"status": "error", "error": str(e)}

    def handle_event(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """
        مدیریت و پردازش رویدادهای رله.
        """
        if not self.connected or self.client is None:
            logger.warning("کلاینت متصل نیست؛ امکان پردازش رویداد وجود ندارد.")
            return False
        try:
            return self.client.handle_event(event_type, payload)
        except Exception as e:
            logger.error(f"خطا در پردازش رویداد {event_type}: {e}")
            return False
