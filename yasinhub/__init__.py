"""
yasinhub
یک CLI ساده‌ی وضعیت برای پروژه‌های اکوسیستم Yasin — نه یک داشبورد
سنگین؛ فقط پاسخ سریع به «چی روشنه، آخرین اجرا کِی و چطور بوده».
"""

from .process_checker import ProcessStatus, check_process
from .registry import ProjectEntry, default_registry
from .report import ProjectReport, build_report
from .status_store import StatusRecord, read_all_statuses, read_status, write_status

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
]

__version__ = "0.1.0"
