"""
tests/test_config_manager.py
تست‌های لایه مدیریت پیکربندی مرکزی YasinHub.
"""

import os
import pytest
import yaml
from pathlib import Path
from yasinhub.config_manager import ConfigManager, ValidationError, reload_config, get_config, get_projects, get_status_dir, get_logs_dir


def test_config_loading_defaults(tmp_path):
    """تست لود شدن مقادیر پیش‌فرض در صورت عدم وجود فایل کانفیگ"""
    config_file = tmp_path / "nonexistent.yaml"
    manager = ConfigManager(config_path=config_file)

    # بررسی وجود پروژه‌ها در کانفیگ پیش‌فرض
    projects = manager.get_projects()
    assert len(projects) > 0
    assert any(p.name == "eitaa_news_v2" for p in projects)

    # بررسی دایرکتوری‌های پیش‌فرض
    assert manager.get_status_dir() == Path.home() / ".yasin_status"
    assert manager.get_logs_dir() == Path.home() / ".yasinhub" / "logs"


def test_env_variable_overrides(tmp_path, monkeypatch):
    """تست بازنویسی مقادیر با استفاده از متغیرهای محیطی"""
    config_file = tmp_path / "config.yaml"

    # تست با YASIN_STATUS_DIR
    monkeypatch.setenv("YASIN_STATUS_DIR", "/tmp/env_status_dir")
    monkeypatch.setenv("YASINHUB_LOGS_DIR", "/tmp/env_logs_dir")

    manager = ConfigManager(config_path=config_file)

    assert manager.get_status_dir() == Path("/tmp/env_status_dir")
    assert manager.get_logs_dir() == Path("/tmp/env_logs_dir")

    # تست با YASINHUB_STATUS_DIR
    monkeypatch.delenv("YASIN_STATUS_DIR")
    monkeypatch.setenv("YASINHUB_STATUS_DIR", "/tmp/env_status_dir_v2")

    manager_v2 = ConfigManager(config_path=config_file)
    assert manager_v2.get_status_dir() == Path("/tmp/env_status_dir_v2")


def test_config_validation():
    """تست اعتبارسنجی مقادیر و خطاهای ساختاری"""
    manager = ConfigManager()

    # غیر دیکشنری بودن ورودی ریشه
    with pytest.raises(ValidationError, match="پیکربندی باید یک دیکشنری معتبر باشد"):
        manager.validate_config("not a dict")

    # نامعتبر بودن نوع status_dir
    with pytest.raises(ValidationError, match="status_dir باید رشته باشد"):
        manager.validate_config({"status_dir": 123})

    # نامعتبر بودن نوع logs_dir
    with pytest.raises(ValidationError, match="logs_dir باید رشته باشد"):
        manager.validate_config({"logs_dir": 123})

    # نامعتبر بودن فیلد projects
    with pytest.raises(ValidationError, match="projects باید لیستی از پروژه‌ها باشد"):
        manager.validate_config({"projects": "not a list"})

    # نامعتبر بودن المان‌های درون لیست پروژه‌ها
    with pytest.raises(ValidationError, match="باید یک دیکشنری باشد"):
        manager.validate_config({"projects": ["not a dict"]})

    # فاقد نام بودن پروژه
    with pytest.raises(ValidationError, match="فاقد نام معتبر"):
        manager.validate_config({"projects": [{"description": "test"}]})

    # تکراری بودن نام پروژه‌ها
    with pytest.raises(ValidationError, match="تکراری است"):
        manager.validate_config({
            "projects": [
                {"name": "proj_a"},
                {"name": "proj_a"}
            ]
        })

    # نامعتبر بودن فیلدهای اختیاری پروژه
    with pytest.raises(ValidationError, match="باید رشته باشد"):
        manager.validate_config({
            "projects": [
                {"name": "proj_a", "process_pattern": 123}
            ]
        })


def test_runtime_config_reload(tmp_path):
    """تست بازخوانی مجدد پیکربندی در زمان اجرا"""
    config_file = tmp_path / "config.yaml"

    # ابتدا ایجاد فایل کانفیگ اولیه
    initial_data = {
        "status_dir": "/tmp/initial_status",
        "projects": [
            {"name": "test_reload_project", "description": "اولیه"}
        ]
    }
    config_file.write_text(yaml.dump(initial_data), encoding="utf-8")

    manager = ConfigManager(config_path=config_file)
    assert manager.get_status_dir() == Path("/tmp/initial_status")
    assert len(manager.get_projects()) == 1
    assert manager.get_projects()[0].description == "اولیه"

    # تغییر محتوای فایل
    updated_data = {
        "status_dir": "/tmp/updated_status",
        "projects": [
            {"name": "test_reload_project", "description": "ثانویه"},
            {"name": "new_project", "description": "جدید"}
        ]
    }
    config_file.write_text(yaml.dump(updated_data), encoding="utf-8")

    # بازخوانی
    manager.reload_config()
    assert manager.get_status_dir() == Path("/tmp/updated_status")
    projects = manager.get_projects()
    assert len(projects) == 2
    assert projects[0].description == "ثانویه"
    assert projects[1].name == "new_project"


def test_global_singleton_apis(tmp_path, monkeypatch):
    """تست توابع جهانی Singleton صادر شده"""
    # تغییر مسیر پیش‌فرض کانفیگ به یک فایل ساختگی
    config_file = tmp_path / "global_config.yaml"
    initial_data = {
        "status_dir": "/tmp/global_status",
        "logs_dir": "/tmp/global_logs",
        "projects": [
            {"name": "global_proj", "description": "توضیح"}
        ]
    }
    config_file.write_text(yaml.dump(initial_data), encoding="utf-8")

    # اعمال مسیر به عنوان آدرس پیش‌فرض در نمونه سراسری
    from yasinhub import config_manager
    monkeypatch.setattr(config_manager._manager, "config_path", config_file)
    config_manager.reload_config()

    assert get_status_dir() == Path("/tmp/global_status")
    assert get_logs_dir() == Path("/tmp/global_logs")
    assert len(get_projects()) == 1
    assert get_projects()[0].name == "global_proj"
    assert isinstance(get_config(), dict)
