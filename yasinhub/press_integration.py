"""
press_integration.py
لایه یکپارچه‌سازی YasinHub با YasinPress و YasinPress-Rewrite از طریق SDK عمومی.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from yasin_press.sdk import YasinPressClient
    HAS_YASIN_PRESS = True
except ImportError:
    YasinPressClient = None
    HAS_YASIN_PRESS = False


class PressIntegration:
    """
    لایه تعامل و مدیریت ارتباط YasinHub با YasinPress و YasinPress-Rewrite.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        self.client: Optional[Any] = None
        self.connected: bool = False
        self.connection_error: Optional[str] = None

        if client is not None:
            self.client = client
            self.connected = True
        elif HAS_YASIN_PRESS:
            try:
                self.client = YasinPressClient()
                self.connected = True
            except Exception as e:
                self.client = None
                self.connected = False
                self.connection_error = f"خطا در مقداردهی اولیه کلاینت پرس: {str(e)}"
        else:
            self.connection_error = "کتابخانه yasin_press یافت نشد یا نصب نیست"

    def get_status(self) -> Dict[str, Any]:
        """
        دریافت وضعیت و مانیتورینگ سرویس پرس.
        """
        if not self.connected or self.client is None:
            return {"status": "unknown", "error": self.connection_error}
        try:
            return self.client.get_status()
        except Exception as e:
            logger.error(f"خطا در دریافت وضعیت سرویس پرس: {e}")
            return {"status": "error", "error": str(e)}

    def check_health(self) -> Dict[str, Any]:
        """
        بررسی سلامت سرویس پرس.
        """
        if not self.connected or self.client is None:
            return {"status": "unhealthy", "error": self.connection_error}
        try:
            return self.client.check_health()
        except Exception as e:
            logger.error(f"خطا در بررسی سلامت سرویس پرس: {e}")
            return {"status": "unhealthy", "error": str(e)}

    def get_rewrites(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        دریافت لیست مقالات پردازش‌شده یا بازنویسی‌شده توسط YasinPress-Rewrite.
        """
        if not self.connected or self.client is None:
            logger.warning("کلاینت متصل نیست؛ امکان دریافت مقالات بازنویسی وجود ندارد.")
            return []
        try:
            if hasattr(self.client, "get_rewrites"):
                return self.client.get_rewrites(limit=limit)
            # رفتار پیش‌فرض یا فال‌بک در صورت عدم وجود متد در SDK قدیمی یا شبیه‌سازی
            return []
        except Exception as e:
            logger.error(f"خطا در دریافت مقالات بازنویسی: {e}")
            return []
