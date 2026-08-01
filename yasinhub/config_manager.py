"""
config_manager.py
لایه مدیریت پیکربندی مرکزی YasinHub.
پشتیبانی از لود کردن کانفیگ از فایل، بازنویسی با متغیرهای محیطی، اعتبار سنجی و دسترسی زمان اجرا.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

# پیش‌فرض‌ها
DEFAULT_CONFIG_DIR = Path(os.environ.get("YASINHUB_CONFIG_DIR", str(Path.home() / ".yasinhub")))
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"


class ValidationError(ValueError):
    """خطای اعتبارسنجی پیکربندی"""
    pass


# ساختار کل پروژه برای سازگاری عقب‌رو
@dataclass
class ProjectConfig:
    name: str
    process_pattern: Optional[str] = None
    description: str = ""
    start_command: Optional[str] = None
    stop_command: Optional[str] = None


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """لود کردن پیکربندی از فایل YAML و بازنویسی با متغیرهای محیطی"""
        config_data: Dict[str, Any] = {"projects": []}

        # لود از فایل در صورت وجود
        if yaml is not None and self.config_path.exists():
            try:
                content = self.config_path.read_text(encoding="utf-8")
                loaded = yaml.safe_load(content)
                if isinstance(loaded, dict):
                    config_data.update(loaded)
            except Exception as e:
                # در صورت خراب بودن فایل، لاگ یا خطا داده شود، اما متوقف نشود
                print(f"هشدار: خطا در خواندن فایل پیکربندی: {e}", file=sys.stderr)

        # اعمال مقادیر پیش‌فرض اگر پروژه‌ای تعریف نشده باشد
        if not config_data.get("projects"):
            from .registry import DEFAULT_PROJECTS
            config_data["projects"] = [
                {
                    "name": p.name,
                    "process_pattern": p.process_pattern,
                    "description": p.description,
                    "start_command": p.start_command,
                    "stop_command": p.stop_command,
                }
                for p in DEFAULT_PROJECTS
            ]

        # مدیریت متغیرهای محیطی با بالاترین اولویت
        # YASIN_STATUS_DIR یا YASINHUB_STATUS_DIR
        status_dir_env = os.environ.get("YASIN_STATUS_DIR") or os.environ.get("YASINHUB_STATUS_DIR")
        if status_dir_env:
            config_data["status_dir"] = status_dir_env

        logs_dir_env = os.environ.get("YASINHUB_LOGS_DIR")
        if logs_dir_env:
            config_data["logs_dir"] = logs_dir_env

        # مقداردهی پیش‌فرض‌ها در صورت عدم وجود
        if "status_dir" not in config_data:
            config_data["status_dir"] = str(Path.home() / ".yasin_status")
        if "logs_dir" not in config_data:
            config_data["logs_dir"] = str(Path.home() / ".yasinhub" / "logs")

        # اعتبارسنجی
        self.validate_config(config_data)

        self._config = config_data
        return self._config

    def validate_config(self, data: Dict[str, Any]) -> None:
        """اعتبارسنجی مقادیر، ساختار و نوع داده‌های پیکربندی"""
        if not isinstance(data, dict):
            raise ValidationError("پیکربندی باید یک دیکشنری معتبر باشد.")

        # بررسی فیلدهای ریشه
        if "status_dir" in data and not isinstance(data["status_dir"], str):
            raise ValidationError("فیلد status_dir باید رشته باشد.")
        if "logs_dir" in data and not isinstance(data["logs_dir"], str):
            raise ValidationError("فیلد logs_dir باید رشته باشد.")

        if "projects" in data:
            if not isinstance(data["projects"], list):
                raise ValidationError("فیلد projects باید لیستی از پروژه‌ها باشد.")

            seen_names = set()
            for idx, proj in enumerate(data["projects"]):
                if not isinstance(proj, dict):
                    raise ValidationError(f"پروژه با ایندکس {idx} باید یک دیکشنری باشد.")

                name = proj.get("name")
                if not name or not isinstance(name, str):
                    raise ValidationError(f"پروژه با ایندکس {idx} فاقد نام معتبر (رشته غیر خالی) است.")

                if name in seen_names:
                    raise ValidationError(f"نام پروژه '{name}' تکراری است.")
                seen_names.add(name)

                # اعتبارسنجی نوع فیلدهای اختیاری پروژه
                for field in ("process_pattern", "description", "start_command", "stop_command"):
                    val = proj.get(field)
                    if val is not None and not isinstance(val, str):
                        raise ValidationError(f"فیلد {field} در پروژه '{name}' باید رشته باشد.")

    def reload_config(self) -> Dict[str, Any]:
        """بازخوانی مجدد پیکربندی در زمان اجرا"""
        return self.load_config()

    def get_config(self) -> Dict[str, Any]:
        """دریافت کل پیکربندی زمان اجرا"""
        return self._config

    def get_status_dir(self) -> Path:
        """دریافت دایرکتوری وضعیت‌ها"""
        # بسط دادن ~ در مسیر در صورت وجود
        path_str = self._config.get("status_dir") or str(Path.home() / ".yasin_status")
        return Path(os.path.expanduser(path_str))

    def get_logs_dir(self) -> Path:
        """دریافت دایرکتوری لاگ‌ها"""
        path_str = self._config.get("logs_dir") or str(Path.home() / ".yasinhub" / "logs")
        return Path(os.path.expanduser(path_str))

    def get_projects(self) -> List[ProjectConfig]:
        """دریافت پروژه‌ها به صورت کلاس دیتا"""
        from .registry import ProjectEntry
        projects_list = []
        for item in self._config.get("projects", []):
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


# یک نمونه واحد جهانی (Singleton) از مدیر پیکربندی برای کل برنامه
_manager = ConfigManager()


def get_config() -> Dict[str, Any]:
    return _manager.get_config()


def get_projects() -> List[Any]:
    return _manager.get_projects()


def get_status_dir() -> Path:
    return _manager.get_status_dir()


def get_logs_dir() -> Path:
    return _manager.get_logs_dir()


def reload_config() -> Dict[str, Any]:
    return _manager.reload_config()


def validate_config(data: Dict[str, Any]) -> None:
    _manager.validate_config(data)
