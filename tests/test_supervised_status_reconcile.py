"""Regression tests for #153: live process must not be shown as FAILED from stale store."""

from __future__ import annotations

from unittest.mock import patch

from yasinhub.cli import format_report
from yasinhub.process_checker import ProcessStatus
from yasinhub.registry import ProjectEntry
from yasinhub.report import build_report
from yasinhub.service_manager import start_service
from yasinhub.status_store import write_status, read_status


def _agent_project() -> ProjectEntry:
    return ProjectEntry(
        name="yasin-agent",
        path="~/yasineco/Yasin-agent",
        process_pattern="agent_platform.server",
        description="Yasin-Agent HTTP runtime (production: supervised by runit/termux-services)",
        start_command=".venv/bin/python -m agent_platform.server",
    )


@patch("yasinhub.report.check_process")
@patch("yasinhub.report.read_pid", return_value=None)
def test_stale_failed_record_plus_live_process(_pid, mock_check, tmp_path):
    write_status("yasin-agent", success=False, message="خطا در راه‌اندازی قدیمی", status_dir=tmp_path)
    mock_check.return_value = ProcessStatus(
        pattern="agent_platform.server", running=True, pids=["26086"]
    )

    reports = build_report(projects=[_agent_project()], status_dir=tmp_path)
    assert len(reports) == 1
    r = reports[0]
    assert r.process_running is True
    assert r.health_state == "RUNNING"
    assert r.last_success is True
    assert "observed running" in r.last_message
    assert "خطا در راه‌اندازی قدیمی" not in (r.last_message or "")

    output = format_report(reports)
    assert "در حال اجرا" in output
    assert "خطا" not in output.split("وضعیت:")[1].split("\n")[0]


@patch("yasinhub.report.check_process")
@patch("yasinhub.report.read_pid", return_value=None)
def test_stale_failed_record_plus_runit_owned_agent(_pid, mock_check, tmp_path):
    write_status("yasin-agent", success=False, message="FAILED spawn", status_dir=tmp_path)
    mock_check.return_value = ProcessStatus(
        pattern="agent_platform.server", running=True, pids=["4242"]
    )
    reports = build_report(projects=[_agent_project()], status_dir=tmp_path)
    assert reports[0].health_state == "RUNNING"
    persisted = read_status("yasin-agent", status_dir=tmp_path)
    assert persisted is not None
    assert persisted.success is True


@patch("yasinhub.report.check_process")
@patch("yasinhub.report.read_pid", return_value=None)
def test_stopped_process_keeps_failed_record(_pid, mock_check, tmp_path):
    write_status("yasin-agent", success=False, message="spawn failed", status_dir=tmp_path)
    mock_check.return_value = ProcessStatus(
        pattern="agent_platform.server", running=False, pids=[]
    )
    reports = build_report(projects=[_agent_project()], status_dir=tmp_path)
    r = reports[0]
    assert r.process_running is False
    assert r.health_state == "FAILED"
    assert r.last_success is False
    assert r.last_message == "spawn failed"
    persisted = read_status("yasin-agent", status_dir=tmp_path)
    assert persisted is not None and persisted.success is False


def test_repeated_start_does_not_spawn_duplicate(tmp_path):
    project = _agent_project()
    with patch("yasinhub.service_manager.read_pid", return_value=None), patch(
        "yasinhub.service_manager.check_process"
    ) as check_process, patch("yasinhub.service_manager.subprocess.Popen") as popen, patch(
        "yasinhub.service_manager.save_pid"
    ):
        check_process.return_value.running = True
        check_process.return_value.pids = ["26086"]
        assert start_service(project, logs_dir=tmp_path / "logs") is True
        assert start_service(project, logs_dir=tmp_path / "logs") is True
        popen.assert_not_called()
