"""
tests/test_yasinhub.py
پوشش تست برای: status_store (خواندن/نوشتن)، process_checker (mock شده)،
report (ترکیب دو منبع)، و خروجی CLI.
"""

from unittest.mock import patch

from yasinhub.cli import format_report
from yasinhub.process_checker import ProcessStatus, check_process
from yasinhub.registry import ProjectEntry
from yasinhub.report import build_report
from yasinhub.status_store import read_all_statuses, read_status, write_status


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
