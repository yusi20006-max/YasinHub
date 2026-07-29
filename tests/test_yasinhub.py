"""
tests/test_yasinhub.py
پوشش تست برای: status_store (خواندن/نوشتن)، process_checker (mock شده)،
report (ترکیب دو منبع)، و خروجی CLI.
"""

from unittest.mock import patch, MagicMock
import os
import signal
from pathlib import Path
import pytest

from yasinhub.cli import format_report, main as cli_main
from yasinhub.process_checker import ProcessStatus, check_process
from yasinhub.registry import ProjectEntry, load_config, default_registry
from yasinhub.report import build_report
from yasinhub.status_store import read_all_statuses, read_status, write_status
from yasinhub.service_manager import start_service, stop_service, restart_service


# ---------------------------------------------------------------------------
# status_store
# ---------------------------------------------------------------------------

def test_write_and_read_status(tmp_path):
    write_status("demo_project", success=True, message="همه‌چیز اوکی", status_dir=tmp_path)
    record = read_status("demo_project", status_dir=tmp_path)

    assert record is not None
    assert record.success is True
    assert record.message == "همه‌چیز اوکی"
    assert record.last_run is not None


def test_read_status_missing_returns_none(tmp_path):
    assert read_status("nonexistent", status_dir=tmp_path) is None


def test_read_all_statuses(tmp_path):
    write_status("a", success=True, status_dir=tmp_path)
    write_status("b", success=False, message="خطا", status_dir=tmp_path)

    all_statuses = read_all_statuses(status_dir=tmp_path)
    assert set(all_statuses.keys()) == {"a", "b"}
    assert all_statuses["b"].success is False


def test_read_status_handles_corrupt_json(tmp_path):
    bad_file = tmp_path / "broken.json"
    bad_file.write_text("{not valid json", encoding="utf-8")

    record = read_status("broken", status_dir=tmp_path)
    assert record is not None
    assert "نامعتبر" in record.message


# ---------------------------------------------------------------------------
# process_checker
# ---------------------------------------------------------------------------

@patch("yasinhub.process_checker.subprocess.run")
def test_check_process_running(mock_run):
    mock_run.return_value.stdout = "1234\n5678\n"
    status = check_process("some_pattern")
    assert status.running is True
    assert status.pids == ["1234", "5678"]


@patch("yasinhub.process_checker.subprocess.run")
def test_check_process_not_running(mock_run):
    mock_run.return_value.stdout = ""
    status = check_process("some_pattern")
    assert status.running is False
    assert status.pids == []


@patch("yasinhub.process_checker.subprocess.run", side_effect=FileNotFoundError)
def test_check_process_missing_pgrep_returns_not_running(mock_run):
    status = check_process("some_pattern")
    assert status.running is False


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

@patch("yasinhub.report.check_process")
def test_build_report_combines_process_and_status(mock_check, tmp_path):
    mock_check.return_value = ProcessStatus(pattern="p", running=True, pids=["1"])
    write_status("proj_a", success=True, message="ok", status_dir=tmp_path)

    projects = [ProjectEntry(name="proj_a", process_pattern="proj_a.py", description="پروژه‌ی تستی")]
    reports = build_report(projects=projects, status_dir=tmp_path)

    assert len(reports) == 1
    r = reports[0]
    assert r.process_running is True
    assert r.last_success is True
    assert r.last_message == "ok"


def test_build_report_project_without_process_pattern(tmp_path):
    projects = [ProjectEntry(name="no_proc", process_pattern=None, description="بدون پروسس دائمی")]
    reports = build_report(projects=projects, status_dir=tmp_path)

    assert reports[0].process_running is None
    assert reports[0].last_run is None


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def test_format_report_includes_name_and_message():
    from yasinhub.report import ProjectReport

    reports = [
        ProjectReport(
            name="demo",
            description="",
            process_running=True,
            last_run="2026-07-26T10:00:00+00:00",
            last_success=True,
            last_message="۱۰ پست منتشر شد",
        )
    ]
    output = format_report(reports)
    assert "demo" in output
    assert "در حال اجرا" in output
    assert "۱۰ پست منتشر شد" in output


# ---------------------------------------------------------------------------
# v0.2 Central Configuration & Service Management Tests
# ---------------------------------------------------------------------------

def test_config_generation_and_loading(tmp_path):
    config_file = tmp_path / "config.yaml"
    # باید فایل کانفیگ پیش‌فرض رو ایجاد کنه
    projects = load_config(config_file)
    assert len(projects) > 0
    assert config_file.exists()

    # ویرایش یک پروژه برای بررسی لود شدن کانفیگ سفارشی
    import yaml
    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["projects"][0]["description"] = "توضیح تستی سفارشی"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    reloaded_projects = load_config(config_file)
    assert reloaded_projects[0].description == "توضیح تستی سفارشی"


@patch("yasinhub.service_manager.subprocess.Popen")
@patch("yasinhub.service_manager.check_process")
def test_start_service_success(mock_check, mock_popen, tmp_path):
    # فرض کنیم پروسس الان در حال اجرا نیست
    mock_check.return_value = ProcessStatus(pattern="test_pattern", running=False, pids=[])

    # ساختن شیء پروسس ساختگی که متوقف نشده (poll برمی‌گرداند None)
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc

    project = ProjectEntry(name="test_srv", start_command="python3 run.py", process_pattern="test_pattern")
    logs_dir = tmp_path / "logs"

    success = start_service(project, logs_dir=logs_dir)
    assert success is True
    assert (logs_dir / "test_srv.log").exists()


@patch("yasinhub.service_manager.subprocess.run")
def test_stop_service_custom_command(mock_run):
    project = ProjectEntry(name="test_srv", stop_command="python3 stop.py")
    success = stop_service(project)
    assert success is True
    mock_run.assert_called_once_with("python3 stop.py", shell=True, timeout=10)


@patch("yasinhub.service_manager.os.kill")
@patch("yasinhub.service_manager.check_process")
def test_stop_service_by_pid(mock_check, mock_kill):
    mock_check.return_value = ProcessStatus(pattern="test_pattern", running=True, pids=["4567"])

    project = ProjectEntry(name="test_srv", process_pattern="test_pattern")
    success = stop_service(project)
    assert success is True
    mock_kill.assert_called_with(4567, signal.SIGTERM)


@patch("yasinhub.cli.build_report")
def test_cli_status_subcommand(mock_build_report, capsys):
    from yasinhub.report import ProjectReport
    mock_build_report.return_value = [
        ProjectReport(
            name="test_srv",
            description="دسکریپشن",
            process_running=True,
            last_run="2026-07-26",
            last_success=True,
            last_message="اوکی",
        )
    ]
    code = cli_main(["status"])
    assert code == 0
    captured = capsys.readouterr()
    assert "test_srv" in captured.out


@patch("yasinhub.service_manager.start_service")
@patch("yasinhub.service_manager.stop_service")
@patch("yasinhub.service_manager.restart_service")
def test_cli_management_subcommands(mock_restart, mock_stop, mock_start, capsys):
    mock_start.return_value = True
    mock_stop.return_value = True
    mock_restart.return_value = True

    # تست استارت همه سرویس‌ها
    code = cli_main(["start"])
    assert code == 0
    captured = capsys.readouterr()
    assert "با موفقیت انجام شد" in captured.out

    # تست استارت یک سرویس خاص غیرموجود
    code = cli_main(["start", "non_existent_service"])
    assert code == 1
    captured = capsys.readouterr()
    assert "یافت نشد" in captured.out
