"""
core_integration.py
لایه یکپارچه‌سازی YasinHub با هسته مرکزی Yasin-Core از طریق SDK عمومی.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from yasin_core.sdk import YasinCoreClient
    from yasin_core.compatibility import is_compatible
    HAS_YASIN_CORE = True
except ImportError:
    YasinCoreClient = None
    is_compatible = None
    HAS_YASIN_CORE = False

# محدوده نسخه‌ی سازگار Core که این نسخه از Hub با آن تست و تأیید شده است.
# از موتور semver واقعی Core استفاده می‌کند (yasin_core.compatibility.is_compatible)
# به‌جای یک لیست ثابتِ major version که با هر ارتقای Core باید دستی به‌روزرسانی شود.
CORE_VERSION_COMPAT = ">=1.0.0"


def validate_sdk_compatibility(version: str) -> bool:
    """
    بررسی سازگاری نسخه SDK هسته با استفاده از موتور semver واقعی Core.
    """
    if not version:
        return False
    if is_compatible is not None:
        try:
            return is_compatible(CORE_VERSION_COMPAT, version)
        except Exception:
            return False
    # fallback محافظه‌کارانه اگر ماژول compatibility در دسترس نبود
    parts = version.split(".")
    if not parts:
        return False
    try:
        return int(parts[0]) >= 1
    except ValueError:
        return False


class CoreIntegration:
    """
    لایه تعامل و مدیریت ارتباط YasinHub با Yasin-Core.
    """

    def __init__(self, client: Optional[YasinCoreClient] = None) -> None:
        self.client: Optional[YasinCoreClient] = None
        self.connected: bool = False
        self.connection_error: Optional[str] = None

        if client is not None:
            self.client = client
            self.connected = True
        elif HAS_YASIN_CORE:
            try:
                self.client = YasinCoreClient()
                self.connected = True
            except Exception as e:
                self.client = None
                self.connected = False
                self.connection_error = f"خطا در مقداردهی اولیه کلاینت: {str(e)}"
        else:
            self.connection_error = "کتابخانه yasin_core یافت نشد یا نصب نیست"

    def check_health(self) -> Dict[str, Any]:
        """
        بررسی وضعیت سلامت و اتصال به هسته.
        """
        if not self.connected:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": self.connection_error,
                "version": None,
                "compatibility": False,
            }

        try:
            version = self.client.get_version()
            is_compatible = validate_sdk_compatibility(version)
            status = "healthy" if is_compatible else "unhealthy"

            return {
                "status": status,
                "connected": True,
                "error": None if is_compatible else f"نسخه SDK ناسازگار است: {version}",
                "version": version,
                "compatibility": is_compatible,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": f"خطا در ارتباط با کلاینت: {str(e)}",
                "version": None,
                "compatibility": False,
            }

    def get_runtime_info(self) -> Dict[str, Any]:
        """
        دریافت اطلاعات ران‌تایم هسته شامل عامل‌ها، ابزارها، پلاگین‌ها و سرویس‌دهنده‌ها.
        """
        if not self.connected or self.client is None:
            return {
                "agents": [],
                "tools": [],
                "plugins": [],
                "providers": [],
                "client_info": {},
            }

        try:
            return {
                "agents": self.client.list_agents(),
                "tools": self.client.list_tools(),
                "plugins": self.client.list_plugins(),
                "providers": self.client.list_providers(),
                "client_info": self.client.get_info(),
            }
        except Exception as e:
            logger.error(f"خطا در دریافت اطلاعات ران‌تایم: {e}")
            return {
                "agents": [],
                "tools": [],
                "plugins": [],
                "providers": [],
                "client_info": {},
                "error": str(e),
            }
