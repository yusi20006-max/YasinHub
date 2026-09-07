"""
yasinhub
یک CLI ساده‌ی وضعیت برای پروژه‌های اکوسیستم Yasin — نه یک داشبورد
سنگین؛ فقط پاسخ سریع به «چی روشنه، آخرین اجرا کِی و چطور بوده».
"""

from .process_checker import ProcessStatus, check_process
from .registry import ProjectEntry, default_registry
from .report import ProjectReport, build_report
from .status_store import StatusRecord, read_all_statuses, read_status, write_status
from .core_integration import CoreIntegration
from .pwa_version import PWA_VERSION

__all__ = [
    "ProcessStatus",
    "check_process",
    "ProjectEntry",
    "default_registry",
    "ProjectReport",
    "build_report",
    "StatusRecord",
    "read_all_statuses",
    "read_status",
    "write_status",
    "CoreIntegration",
    "PWA_VERSION",
]

__version__ = PWA_VERSION
