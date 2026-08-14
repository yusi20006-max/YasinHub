from typing import Any, Dict, List, Optional
from yasinhub.press_integration import PressIntegration


class PressService:

    def __init__(self, press_integration: Optional[PressIntegration] = None):
        self.press = press_integration or PressIntegration()

    def health(self) -> Dict[str, Any]:
        """
        بررسی سلامت سرویس پرس.
        """
        status_info = self.press.check_health()
        return {
            "service": "YasinPress Service",
            "status": status_info.get("status", "unhealthy"),
            "error": status_info.get("error")
        }

    def get_status(self) -> Dict[str, Any]:
        """
        دریافت وضعیت کامل سرویس پرس.
        """
        return self.press.get_status()

    def get_rewrites(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        دریافت لیست بازنویسی‌های اخیر.
        """
        return self.press.get_rewrites(limit=limit)
