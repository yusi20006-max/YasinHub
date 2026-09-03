"""Regression: Control Plane stop must not leave stale SUCCESS / observed running."""

from types import SimpleNamespace
from unittest.mock import patch

from yasinhub.registry import ProjectEntry
from yasinhub.report import build_report, calculate_health_state
from yasinhub.service_manager import stop_service
from yasinhub.status_store import write_status, read_status


def test_calculate_health_dead_process_not_success():
    assert calculate_health_state(False, "2026-09-03T10:00:00+00:00", True) == "IDLE"
    assert calculate_health_state(False, "2026-09-03T10:00:00+00:00", False) == "FAILED"
    assert calculate_health_state(True, "2026-09-03T10:00:00+00:00", True) == "RUNNING"
    assert calculate_health_state(None, "2026-09-03T10:00:00+00:00", True) == "SUCCESS"


def test_build_report_after_stop_is_idle_not_success(tmp_path):
    project = ProjectEntry(
        name="yasin-ai",
        path=str(tmp_path),
        process_pattern="yasinai.cli.main serve",
        start_command="yasin serve",
    )
    write_status(
        "yasin-ai",
        success=True,
        message="observed running",
        status_dir=tmp_path,
    )

    with patch("yasinhub.report.read_pid", return_value=None), patch(
        "yasinhub.report.check_process",
        return_value=SimpleNamespace(pattern="x", running=False, pids=[]),
    ), patch("yasinhub.report.is_pid_alive", return_value=False), patch(
        "yasinhub.report.remove_pid"
    ), patch("yasinhub.report.save_pid"):
        reports = build_report([project], status_dir=tmp_path)

    r = reports[0]
    assert r.process_running is False
    assert r.health_state == "IDLE"
    assert r.health_state != "SUCCESS"
    assert r.health_state != "RUNNING"
    # persisted observation may still exist; runtime state must not be SUCCESS
    assert r.last_message in ("observed running", "stopped")


def test_stop_service_marks_stopped_status(tmp_path, monkeypatch):
    project = ProjectEntry(
        name="yasin-ai",
        path=str(tmp_path),
        process_pattern=None,
        start_command="yasin serve",
    )
    write_status(
        "yasin-ai",
        success=True,
        message="observed running",
        status_dir=tmp_path,
    )
    monkeypatch.setattr("yasinhub.service_manager.read_pid", lambda name: 4242)
    monkeypatch.setattr("yasinhub.service_manager.stop_pid_safely", lambda pid, timeout=3.0: True)
    monkeypatch.setattr("yasinhub.service_manager.remove_pid", lambda name: None)
    monkeypatch.setattr("yasinhub.config_manager.get_status_dir", lambda: tmp_path)

    assert stop_service(project) is True
    persisted = read_status("yasin-ai", status_dir=tmp_path)
    assert persisted is not None
    assert persisted.message == "stopped"
    assert persisted.success is True


def test_running_to_stop_to_start_status_cycle(tmp_path, monkeypatch):
    """running → stop → idle; stop → start → running."""
    project = ProjectEntry(
        name="yasin-ai",
        path=str(tmp_path),
        process_pattern="yasinai.cli.main serve",
        start_command="yasin serve",
    )
    status_dir = tmp_path

    # Simulate previously running observation
    write_status("yasin-ai", success=True, message="observed running", status_dir=status_dir)

    with patch("yasinhub.report.read_pid", return_value=None), patch(
        "yasinhub.report.check_process",
        return_value=SimpleNamespace(pattern="x", running=False, pids=[]),
    ):
        stopped_reports = build_report([project], status_dir=status_dir)
    assert stopped_reports[0].health_state == "IDLE"

    # Live process again
    with patch("yasinhub.report.read_pid", return_value=None), patch(
        "yasinhub.report.check_process",
        return_value=SimpleNamespace(pattern="x", running=True, pids=["9999"]),
    ), patch("yasinhub.report.save_pid"), patch("yasinhub.report.is_pid_alive", return_value=True):
        running_reports = build_report([project], status_dir=status_dir)
    assert running_reports[0].health_state == "RUNNING"


def test_repeated_stop_keeps_idle(tmp_path, monkeypatch):
    project = ProjectEntry(
        name="yasin-ai",
        start_command="yasin serve",
        process_pattern="yasinai.cli.main serve",
    )
    monkeypatch.setattr("yasinhub.service_manager.read_pid", lambda name: None)
    monkeypatch.setattr(
        "yasinhub.service_manager.check_process",
        lambda pattern: SimpleNamespace(running=False, pids=[]),
    )
    monkeypatch.setattr("yasinhub.config_manager.get_status_dir", lambda: tmp_path)
    write_status("yasin-ai", success=True, message="stopped", status_dir=tmp_path)

    assert stop_service(project) is False  # nothing to stop
    with patch("yasinhub.report.read_pid", return_value=None), patch(
        "yasinhub.report.check_process",
        return_value=SimpleNamespace(pattern="x", running=False, pids=[]),
    ):
        reports = build_report([project], status_dir=tmp_path)
    assert reports[0].health_state == "IDLE"
