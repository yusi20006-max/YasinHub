"""
tests/test_service_management_ops.py
تست‌های جامع برای مدیریت چرخه‌ی حیات سرویس‌ها و ردیابی پروسس‌ها در YasinHub.
شامل بررسی وضعیت‌های RUNNING و STOPPED، ایجاد و حذف PID، رفتارهای ری‌استارت و مدیریت بازیابی از کرش (crashed process detection).
"""

import os
import time
import signal
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from yasinhub.registry import ProjectEntry
from yasinhub.pid_store import save_pid, read_pid, remove_pid, is_pid_alive
from yasinhub.service_manager import start_service, stop_service, restart_service
from yasinhub.report import build_report, ProjectReport


@pytest.fixture
def patch_pid_dir(tmp_path, monkeypatch):
    """جایگزین کردن مسیر دایرکتوری ذخیره PID با مسیر موقت برای ایزوله‌سازی تست‌ها"""
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: pid_dir)
    return pid_dir


def test_service_start_stop_running_stopped_status(patch_pid_dir, tmp_path):
    """بررسی شروع، توقف، ایجاد/حذف فایل PID و تغییر وضعیت واقعی به RUNNING و STOPPED"""
    project = ProjectEntry(
        name="test_dummy_srv",
        start_command="python3 -c \"import time; time.sleep(15)\"",
        description="تست سرویس ساختگی"
    )
    logs_dir = tmp_path / "logs"

    # ۱. استارت اولیه و بررسی وضعیت RUNNING
    success = start_service(project, logs_dir=logs_dir)
    assert success is True

    # بررسی ثبت درست PID
    saved_pid = read_pid(project.name)
    assert saved_pid is not None
    assert saved_pid > 0
    assert is_pid_alive(saved_pid) is True

    # بررسی گزارش وضعیت
    reports = build_report(projects=[project])
    assert len(reports) == 1
    assert reports[0].process_running is True
    assert reports[0].health_state == "RUNNING"

    # ۲. توقف سرویس و بررسی وضعیت STOPPED
    stop_success = stop_service(project)
    assert stop_success is True

    # بررسی حذف درست PID
    assert read_pid(project.name) is None
    assert is_pid_alive(saved_pid) is False

    # بررسی تغییر وضعیت گزارش به غیرفعال
    reports_after = build_report(projects=[project])
    assert reports_after[0].process_running in (False, None)
    assert reports_after[0].health_state != "RUNNING"


def test_service_restart_behavior(patch_pid_dir, tmp_path):
    """تست رفتار ری‌استارت: متوقف کردن فرآیند قبلی و شروع مجدد با PID متفاوت و جدید"""
    project = ProjectEntry(
        name="test_restart_srv",
        start_command="python3 -c \"import time; time.sleep(15)\"",
        description="تست ری‌استارت"
    )
    logs_dir = tmp_path / "logs"

    # استارت اول
    assert start_service(project, logs_dir=logs_dir) is True
    pid1 = read_pid(project.name)
    assert pid1 is not None

    # ری‌استارت سرویس
    assert restart_service(project, logs_dir=logs_dir) is True
    pid2 = read_pid(project.name)
    assert pid2 is not None
    assert pid1 != pid2  # باید شناسه پروسس تغییر کرده باشد

    # بررسی زنده بودن پروسس جدید و متوقف بودن پروسس قدیمی
    assert is_pid_alive(pid1) is False
    assert is_pid_alive(pid2) is True

    # پاک‌سازی
    stop_service(project)


def test_crashed_process_detection_and_cleanup(patch_pid_dir, tmp_path):
    """تست شناسایی کرش پروسس: اگر فایل PID وجود داشته باشد ولی پروسس مرده باشد، فایل حذف شده و وضعیت اصلاح شود"""
    project = ProjectEntry(
        name="test_crash_srv",
        start_command="python3 -c \"import time; time.sleep(15)\"",
        description="تست کرش"
    )

    # ذخیره یک PID نامعتبر و غیرزنده به طور دستی (مشابه سناریوی کرش)
    stale_pid = 999999
    save_pid(project.name, stale_pid)

    # بررسی وضعیت گزارش: باید متوجه شود پروسس مرده است و فایل PID قدیمی را پاک کند
    reports = build_report(projects=[project])
    assert len(reports) == 1
    assert reports[0].process_running is False
    assert read_pid(project.name) is None  # فایل PID قدیمی و خراب باید اتوماتیک حذف شده باشد

    # سناریوی ۲: تست استارت سرویس هنگامی که فایل PID خراب از قبل وجود داشته باشد
    # ذخیره مجدد PID نامعتبر
    save_pid(project.name, stale_pid)

    logs_dir = tmp_path / "logs"
    # استارت سرویس باید به طور اتوماتیک فایل خراب را حذف کرده و سرویس جدید را راه بیندازد
    assert start_service(project, logs_dir=logs_dir) is True

    new_pid = read_pid(project.name)
    assert new_pid is not None
    assert new_pid != stale_pid
    assert is_pid_alive(new_pid) is True

    # پاک‌سازی
    stop_service(project)


@patch("yasinhub.api.server.default_registry")
@patch("yasinhub.api.server.start_service")
@patch("yasinhub.api.server.stop_service")
@patch("yasinhub.api.server.restart_service")
def test_api_server_service_control_actions(
    mock_restart, mock_stop, mock_start, mock_registry
):
    """بررسی کامل هندلر کنترل API برای سناریوهای GET و POST با مقادیر مختلف"""
    from yasinhub.api.server import YasinHubHandler
    import json
    from io import BytesIO

    # شبیه‌سازی درخواست‌ها و پاسخ‌ها در لایه سرور
    class MockServerRequest:
        def makefile(self, *args, **kwargs):
            return BytesIO(b"")
        def sendall(self, data):
            pass

    class DummyAPIHandler(YasinHubHandler):
        def __init__(self):
            self.request = MockServerRequest()
            self.client_address = ("127.0.0.1", 12345)
            self.server = MagicMock()
            self.wfile = BytesIO()
            self.response_code = None
            self.response_headers = {}

        def setup(self): pass
        def handle(self): pass
        def finish(self): pass
        def send_response(self, code, message=None):
            self.response_code = code
        def send_header(self, keyword, value):
            self.response_headers[keyword] = value
        def end_headers(self): pass

    project = ProjectEntry(name="eitaa_news_v2", start_command="python3 eitaa_news_v2.py")
    mock_registry.return_value = [project]

    # ۱. تست استارت از طریق POST
    mock_start.return_value = True
    handler = DummyAPIHandler()
    handler.path = "/api/control/eitaa_news_v2/start"
    handler.do_POST()

    assert handler.response_code == 200
    res1 = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert res1["service"] == "eitaa_news_v2"
    assert res1["action"] == "start"
    assert res1["success"] is True
    mock_start.assert_called_once_with(project)

    # ۲. تست استاپ از طریق GET
    mock_stop.return_value = True
    handler_get = DummyAPIHandler()
    handler_get.path = "/api/control/eitaa_news_v2/stop"
    handler_get.do_GET()

    assert handler_get.response_code == 200
    res2 = json.loads(handler_get.wfile.getvalue().decode("utf-8"))
    assert res2["action"] == "stop"
    assert res2["success"] is True
    mock_stop.assert_called_once_with(project)

    # ۳. تست ری‌استارت و بررسی شرایط عدم موفقیت
    mock_restart.return_value = False
    handler_restart = DummyAPIHandler()
    handler_restart.path = "/api/control/eitaa_news_v2/restart"
    handler_restart.do_POST()

    assert handler_restart.response_code == 200
    res3 = json.loads(handler_restart.wfile.getvalue().decode("utf-8"))
    assert res3["action"] == "restart"
    assert res3["success"] is False
    mock_restart.assert_called_once_with(project)

    # ۴. تست سرویس غیرموجود
    handler_unknown = DummyAPIHandler()
    handler_unknown.path = "/api/control/non_existent_service/start"
    handler_unknown.do_POST()

    assert handler_unknown.response_code == 200
    res4 = json.loads(handler_unknown.wfile.getvalue().decode("utf-8"))
    assert res4["success"] is False
    assert "not found" in res4["error"]
