"""
agent_integration.py
لایه یکپارچه‌سازی YasinHub با Yasin-Agent از طریق SDK عمومی.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from yasin_agent.sdk import YasinAgentClient
    HAS_YASIN_AGENT = True
except ImportError:
    YasinAgentClient = None
    HAS_YASIN_AGENT = False


class AgentIntegration:
    """
    لایه تعامل و مدیریت ارتباط YasinHub با Yasin-Agent.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        self.client: Optional[Any] = None
        self.connected: bool = False
        self.connection_error: Optional[str] = None

        if client is not None:
            self.client = client
            self.connected = True
        elif HAS_YASIN_AGENT:
            try:
                self.client = YasinAgentClient()
                self.connected = True
            except Exception as e:
                self.client = None
                self.connected = False
                self.connection_error = f"خطا در مقداردهی اولیه کلاینت عامل: {str(e)}"
        else:
            self.connection_error = "کتابخانه yasin_agent یافت نشد یا نصب نیست"

    def register_agent(self, name: str, description: str = "") -> bool:
        """
        ثبت یک عامل جدید در سیستم.
        """
        if not self.connected or self.client is None:
            logger.warning("کلاینت متصل نیست؛ امکان ثبت عامل وجود ندارد.")
            return False
        try:
            return self.client.register_agent(name, description)
        except Exception as e:
            logger.error(f"خطا در ثبت عامل {name}: {e}")
            return False

    def get_agent_status(self, name: str) -> Dict[str, Any]:
        """
        دریافت وضعیت یک عامل مشخص.
        """
        if not self.connected or self.client is None:
            return {"name": name, "status": "unknown", "error": self.connection_error}
        try:
            return self.client.get_agent_status(name)
        except Exception as e:
            logger.error(f"خطا در دریافت وضعیت عامل {name}: {e}")
            return {"name": name, "status": "error", "error": str(e)}

    def start_agent(self, name: str) -> bool:
        """
        شروع اجرای یک عامل.
        """
        if not self.connected or self.client is None:
            return False
        try:
            return self.client.start_agent(name)
        except Exception as e:
            logger.error(f"خطا در شروع عامل {name}: {e}")
            return False

    def stop_agent(self, name: str) -> bool:
        """
        متوقف کردن اجرای یک عامل.
        """
        if not self.connected or self.client is None:
            return False
        try:
            return self.client.stop_agent(name)
        except Exception as e:
            logger.error(f"خطا در متوقف کردن عامل {name}: {e}")
            return False

    def restart_agent(self, name: str) -> bool:
        """
        راه‌اندازی مجدد یک عامل.
        """
        if not self.connected or self.client is None:
            return False
        try:
            if hasattr(self.client, "restart_agent"):
                return self.client.restart_agent(name)

            # در صورتی که تابع restart_agent تعریف نشده باشد، از ترکیب stop و start استفاده می‌کنیم
            stop_success = self.stop_agent(name)
            start_success = self.start_agent(name)
            return stop_success and start_success
        except Exception as e:
            logger.error(f"خطا در راه‌اندازی مجدد عامل {name}: {e}")
            return False

    def check_agent_health(self, name: str) -> Dict[str, Any]:
        """
        بررسی سلامت یک عامل مشخص.
        """
        if not self.connected or self.client is None:
            return {"name": name, "status": "unhealthy", "error": self.connection_error}
        try:
            return self.client.check_agent_health(name)
        except Exception as e:
            logger.error(f"خطا در بررسی سلامت عامل {name}: {e}")
            return {"name": name, "status": "unhealthy", "error": str(e)}
