"""
status_store.py
قرارداد ساده‌ی فایل وضعیت: هر پروژه (eitaa_news_v2, YasinRelay, ...) بعد
از هر اجرا یک فایل JSON در یک پوشه‌ی مشترک می‌نویسد:

    ~/.yasin_status/<project_name>.json

با ساختار:
    {
      "last_run": "2026-07-26T10:00:00+00:00",
      "success": true,
      "message": "۱۲ پست منتشر شد"
    }

نوشتن این فایل با تابع `write_status` انجام می‌شود (که هر پروژه در
انتهای اجرای خودش صدا می‌زند)؛ خواندنش با `read_all_statuses` که
YasinHub استفاده می‌کند.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# متغیر پیش‌فرض خام، اما در توابع از config_manager استفاده می‌شود تا داینامیک باشد
DEFAULT_STATUS_DIR = Path(os.environ.get("YASIN_STATUS_DIR", str(Path.home() / ".yasin_status")))


@dataclass
class StatusRecord:
    project: str
    last_run: Optional[str] = None
    success: Optional[bool] = None
    message: str = ""

    health: Dict = None
    metrics: Dict = None
    db_stats: Dict = None

    @classmethod
    def from_dict(cls, project: str, data: Dict) -> "StatusRecord":
        return cls(
            project=project,
            last_run=data.get("last_run"),
            success=data.get("success"),
            message=data.get("message", ""),
            health=data.get("health", {}),
            metrics=data.get("metrics", {})
                or data.get("health", {}).get("metrics", {}),
            db_stats=data.get("db_stats", {})
                or data.get("health", {}).get("db_stats", {}),
        )


def write_status(
    project: str,
    success: bool,
    message: str = "",
    status_dir: Optional[Path] = None,
) -> Path:
    """پروژه‌ها این تابع را در انتهای اجرای خودشان صدا می‌زنند."""
    if status_dir is None:
        from .config_manager import get_status_dir
        s_dir = get_status_dir()
    else:
        s_dir = status_dir

    s_dir.mkdir(parents=True, exist_ok=True)
    path = s_dir / f"{project}.json"
    payload = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "message": message,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_status(project: str, status_dir: Optional[Path] = None) -> Optional[StatusRecord]:
    if status_dir is None:
        from .config_manager import get_status_dir
        s_dir = get_status_dir()
    else:
        s_dir = status_dir

    path = s_dir / f"{project}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return StatusRecord(project=project, message="فایل وضعیت خراب/نامعتبر است")
    return StatusRecord.from_dict(project, data)


def read_all_statuses(status_dir: Optional[Path] = None) -> Dict[str, StatusRecord]:
    if status_dir is None:
        from .config_manager import get_status_dir
        s_dir = get_status_dir()
    else:
        s_dir = status_dir

    if not s_dir.exists():
        return {}
    results: Dict[str, StatusRecord] = {}
    for path in sorted(s_dir.glob("*.json")):
        project = path.stem
        record = read_status(project, status_dir=s_dir)
        if record is not None:
            results[project] = record
    return results
