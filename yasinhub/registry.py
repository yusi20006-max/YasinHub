"""
registry.py
فهرست پروژه‌هایی که YasinHub وضعیت‌شان را نشان می‌دهد: نام، الگوی
پروسس (برای process_checker)، و توضیح کوتاه.

این فهرست را می‌توان بعداً از یک فایل کانفیگ (YAML/JSON) بارگذاری کرد؛
فعلاً به‌صورت یک لیست ساده در کد است تا شروع کار راحت باشد.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ProjectEntry:
    name: str
    process_pattern: Optional[str] = None
    description: str = ""


DEFAULT_PROJECTS: List[ProjectEntry] = [
    ProjectEntry(name="eitaa_news_v2", process_pattern="eitaa_news_v2.py", description="بات خبری RSS -> @yusinews"),
    ProjectEntry(name="yasinrelay", process_pattern="yasinrelay.cli", description="تلگرام -> AI -> ایتا"),
    ProjectEntry(name="yasin-agent", process_pattern=None, description="اجرای وظایف چندمرحله‌ای (بدون پروسس دائمی)"),
]


def default_registry() -> List[ProjectEntry]:
    return list(DEFAULT_PROJECTS)
