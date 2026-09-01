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

# قرارداد canonical اکوسیستم YASIN: تمام repositoryها زیر ~/yasineco هستند.
YASIN_ECOSYSTEM_ROOT = Path(os.environ.get("YASIN_ECOSYSTEM_ROOT", str(Path.home() / "yasineco"))).expanduser()

# مسیر پیش‌فرض فایل پیکربندی مرکزی
DEFAULT_CONFIG_DIR = Path(os.environ.get("YASINHUB_CONFIG_DIR", str(Path.home() / ".yasinhub")))
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"


@dataclass
class ProjectEntry:
    name: str
    path: Optional[str] = None
    process_pattern: Optional[str] = None
    description: str = ""
    start_command: Optional[str] = None
    stop_command: Optional[str] = None


DEFAULT_PROJECTS: List[ProjectEntry] = [
    ProjectEntry(
        name="yasinfeed",
        path=str(YASIN_ECOSYSTEM_ROOT / "Yasinfeed-main"),
        process_pattern="yasinfeed.py",
        description="سرویس فید خوان یاسین (YasinFeed)",
        start_command="python3 yasinfeed.py"
    ),
    ProjectEntry(
        name="eitaa_news_v2",
        process_pattern="eitaa_news_v2.py",
        description="بات خبری RSS -> @yusinews",
        start_command="python3 eitaa_news_v2.py"
    ),
    ProjectEntry(
        name="yasinrelay",
        path=str(YASIN_ECOSYSTEM_ROOT / "YasinRelay"),
        process_pattern="yasinrelay.cli",
        description="تلگرام -> AI -> ایتا",
        start_command="python3 -m yasinrelay.cli run"
    ),
    ProjectEntry(
        name="yasin-agent",
        path=str(YASIN_ECOSYSTEM_ROOT / "Yasin-agent"),
        process_pattern=None,
        description="اجرای وظایف چندمرحله‌ای (بدون پروسس دائمی)",
        start_command="python3 -m agent_platform.cli"
    ),
    ProjectEntry(
        name="yasin-ai",
        path=str(YASIN_ECOSYSTEM_ROOT / "Yasin-AI"),
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
    لود کردن فهرست پروژه‌ها از فایل پیکربندی YAML مرکزی از طریق لایه مدیریت پیکربندی.
    """
    from .config_manager import get_projects
    return get_projects()


def load_config(config_path: Optional[Path] = None) -> List[ProjectEntry]:
    """
    سازگاری با نسخه‌های قبلی: لود کردن پروژه‌ها از مسیر داده شده.
    در صورت عدم وجود فایل پیکربندی پیش‌فرض را ایجاد می‌کند.
    """
    path = config_path or DEFAULT_CONFIG_PATH

    if yaml is None:
        return list(DEFAULT_PROJECTS)

    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            default_yaml_content = {
                "projects": [
                    {
                        "name": p.name,
                        "path": p.path,
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
            return list(DEFAULT_PROJECTS)

    from .config_manager import ConfigManager
    manager = ConfigManager(config_path=path)
    return manager.get_projects()
