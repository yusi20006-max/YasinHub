"""
events_engine.py
موتور رویدادهای YasinHub: پارس کردن رویدادها از فایل‌های لاگ، استخراج زمان و سطح شدت، فیلتر کردن و پاک‌سازی فضای ذخیره‌سازی رویدادها.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config_manager import get_logs_dir

# الگوهای شناسایی رویدادها در خطوط لاگ
EVENT_TYPES = [
    "ContentReceived",
    "AIProcessingCompleted",
    "PublishingCompleted",
    "DuplicateDetected",
    "ProcessingStarted",
    "ERROR"
]

# نگاشت نوع رویداد به سطح شدت (Severity Level)
SEVERITY_MAP = {
    "ERROR": "ERROR",
    "DuplicateDetected": "WARNING",
    "PublishingCompleted": "SUCCESS",
    "AIProcessingCompleted": "INFO",
    "ContentReceived": "INFO",
    "ProcessingStarted": "INFO"
}

# عبارات منظم برای استخراج تاریخ و زمان
TIMESTAMP_REGEXES = [
    re.compile(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?)'),
    re.compile(r'(\d{4}/\d{2}/\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)'),
]


def extract_timestamp(line: str) -> Optional[str]:
    """استخراج تاریخ و زمان از خط لاگ با استفاده از عبارات منظم"""
    for rx in TIMESTAMP_REGEXES:
        m = rx.search(line)
        if m:
            return m.group(1)
    return None


def get_file_mtime(filepath: Path) -> str:
    """دریافت زمان آخرین ویرایش فایل به عنوان جایگزین"""
    try:
        mtime = filepath.stat().st_mtime
        return datetime.fromtimestamp(mtime, timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def parse_events_from_logs(max_lines_per_file: int = 200) -> List[Dict[str, Any]]:
    """خواندن و پارس کردن رویدادها از لاگ‌های تمام سرویس‌ها در مسیر ~/.yasinhub/logs/"""
    events = []
    log_dir = get_logs_dir()

    if not log_dir.exists():
        return []

    for log_file in log_dir.glob("*.log"):
        service = log_file.stem
        file_mtime = get_file_mtime(log_file)

        try:
            # خواندن خطوط پایانی فایل لاگ
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()[-max_lines_per_file:]

            # معکوس کردن خطوط برای دریافت جدیدترین‌ها در ابتدا
            for line in reversed(lines):
                # یافتن منطبق‌ترین نوع رویداد در خط
                matched_type = None
                for name in EVENT_TYPES:
                    if name in line:
                        matched_type = name
                        break

                if matched_type:
                    ts = extract_timestamp(line) or file_mtime
                    severity = SEVERITY_MAP.get(matched_type, "INFO")

                    # پاک‌سازی پیام: حذف کردن زمان و برچسب‌های تکراری از متن اصلی در صورت امکان
                    clean_msg = line.strip()

                    events.append({
                        "service": service,
                        "type": matched_type,
                        "severity": severity,
                        "timestamp": ts,
                        "message": clean_msg
                    })
        except Exception:
            pass

    # مرتب‌سازی کل رویدادها بر اساس زمان به صورت نزولی (جدیدترین در ابتدا)
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events


def filter_events(
    events: List[Dict[str, Any]],
    service: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    level: Optional[str] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """فیلتر کردن رویدادها بر اساس پارامترهای ارسالی"""
    filtered = []

    # همگام‌سازی severity و level
    target_severity = severity or level

    for e in events:
        if service and e["service"].lower() != service.lower():
            continue
        if event_type and e["type"].lower() != event_type.lower():
            continue
        if target_severity and e["severity"].lower() != target_severity.lower():
            continue

        filtered.append(e)

    if limit is not None:
        try:
            lim = int(limit)
            return filtered[:lim]
        except ValueError:
            pass

    return filtered


def cleanup_events() -> bool:
    """پاک‌سازی فضای ذخیره‌سازی رویدادها با خالی کردن (Truncate) فایل‌های لاگ"""
    log_dir = get_logs_dir()
    if not log_dir.exists():
        return True

    success = True
    for log_file in log_dir.glob("*.log"):
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.truncate(0)
        except Exception:
            success = False

    return success
