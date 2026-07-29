"""
registry.py
فهرست پروژه‌هایی که YasinHub وضعیت‌شان را نشان می‌دهد: نام، الگوی
پروسس (برای process_checker)، و توضیح کوتاه.

این فهرست از یک فایل کانفیگ (YAML) بارگذاری می‌شود؛ با پس‌روی به لیست
پیش‌فرض در صورت نبود فایل پیکربندی.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    import yaml
except ImportError:
    yaml = None

# مسیر پیش‌فرض فایل پیکربندی مرکزی
DEFAULT_CONFIG_DIR = Path(os.environ.get("YASINHUB_CONFIG_DIR", str(Path.home() / ".yasinhub")))
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"


@dataclass
class ProjectEntry:
    name: str
    process_pattern: Optional[str] = None
    description: str = ""
    start_command: Optional[str] = None
    stop_command: Optional[str] = None


DEFAULT_PROJECTS: List[ProjectEntry] = [
    ProjectEntry(
        name="eitaa_news_v2",
        process_pattern="eitaa_news_v2.py",
        description="بات خبری RSS -> @yusinews",
        start_command="python3 eitaa_news_v2.py"
    ),
    ProjectEntry(
        name="yasinrelay",
        process_pattern="yasinrelay.cli",
        description="تلگرام -> AI -> ایتا",
        start_command="python3 -m yasinrelay.cli"
    ),
    ProjectEntry(
        name="yasin-agent",
        process_pattern=None,
        description="اجرای وظایف چندمرحله‌ای (بدون پروسس دائمی)",
        start_command="python3 -m yasin_agent.cli"
    ),
    ProjectEntry(
        name="yasin-ai",
        process_pattern="yasin_ai.cli",
        description="موتور اصلی هوش مصنوعی یاسین",
        start_command="python3 -m yasin_ai.cli"
    ),
    ProjectEntry(
        name="yasin-coder",
        process_pattern="yasin_coder.cli",
        description="دستیار کدنویسی یاسین",
        start_command="python3 -m yasin_coder.cli"
    ),
    ProjectEntry(
        name="yasinpress",
        process_pattern="yasinpress.cli",
        description="سیستم مدیریت و انتشار محتوای یاسین",
        start_command="python3 -m yasinpress.cli"
    ),
    ProjectEntry(
        name="backup_manager",
        process_pattern="backup_manager.py",
        description="مدیریت پشتیبان‌گیری خودکار اکوسیستم",
        start_command="python3 backup_manager.py"
    ),
]


def default_registry() -> List[ProjectEntry]:
    """
    لود کردن فهرست پروژه‌ها از فایل پیکربندی YAML مرکزی.
    در صورت عدم وجود یا هرگونه خطا، به لیست پیش‌فرض پس‌روی (fallback) می‌کند.
    """
    return load_config()


def load_config(config_path: Optional[Path] = None) -> List[ProjectEntry]:
    path = config_path or DEFAULT_CONFIG_PATH

    # اگر پکیج yaml نصب نبود یا خطایی رخ داد، از پیش‌فرض استفاده شود
    if yaml is None:
        return list(DEFAULT_PROJECTS)

    if not path.exists():
        try:
            # ایجاد دایرکتوری و ذخیره پیکربندی پیش‌فرض
            path.parent.mkdir(parents=True, exist_ok=True)
            default_yaml_content = {
                "projects": [
                    {
                        "name": p.name,
                        "process_pattern": p.process_pattern,
                        "description": p.description,
                        "start_command": p.start_command,
                        "stop_command": p.stop_command,
                    }
                    for p in DEFAULT_PROJECTS
                ]
            }
            path.write_text(
                yaml.dump(default_yaml_content, allow_unicode=True, sort_keys=False),
                encoding="utf-8"
            )
        except Exception:
            # در صورت عدم امکان نوشتن، فقط ادامه بده و لیست پیش‌فرض رو برگردون
            return list(DEFAULT_PROJECTS)

    try:
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        if not data or "projects" not in data:
            return list(DEFAULT_PROJECTS)

        projects_list = []
        for item in data["projects"]:
            projects_list.append(
                ProjectEntry(
                    name=item["name"],
                    process_pattern=item.get("process_pattern"),
                    description=item.get("description", ""),
                    start_command=item.get("start_command"),
                    stop_command=item.get("stop_command"),
                )
            )
        return projects_list
    except Exception:
        return list(DEFAULT_PROJECTS)
