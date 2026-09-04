"""Regression tests for Issue #163: Control Plane START/STOP/RESTART verification.

Covers the production bug where Hub reported START success (HTTP success:true +
PID file) for a service whose process exits shortly after Popen() — e.g. YasinRelay
failing config validation after ~1s of imports, beyond the old 0.3s single poll.

All lifecycle tests use REAL processes (no Popen mocking) so the verified behavior
is the actual production behavior.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from yasinhub.pid_store import is_pid_alive, read_pid, save_pid
from yasinhub.registry import ProjectEntry
from yasinhub.report import build_report
from yasinhub.service_manager import (
    restart_service,
    start_service,
    stop_service,
    verify_process_identity,
)
from yasinhub.status_store import read_status


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Isolate PID + status dirs from the real ~/.yasinhub / ~/.yasin_status."""
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir(parents=True, exist_ok=True)
    status_dir = tmp_path / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: pid_dir)
    monkeypatch.setattr("yasinhub.config_manager.get_status_dir", lambda: status_dir)
    return tmp_path


def _sleepy_project(name: str, seconds: int = 15) -> ProjectEntry:
    return ProjectEntry(
        name=name,
        start_command=f"python3 -c \"import time; time.sleep({seconds})\"",
        description="test service",
    )


def test_start_fails_when_process_exits_during_verification(isolated_state, tmp_path):
    """Core regression: Popen + PID, then child exits 1.2s later (relay-like).

    Expected: start_service() is False, PID file removed, FAILED status recorded
    with exit-code evidence — never a success report for a dead process.
    """
    project = ProjectEntry(
        name="early-exit-srv",
        start_command=(
            "python3 -c \"import time,sys; time.sleep(1.2); "
            "print('FATAL: no channels'); sys.exit(1)\""
        ),
        description="exits during startup verification",
    )
    assert start_service(project, logs_dir=tmp_path / "logs") is False
    assert read_pid(project.name) is None
    record = read_status(project.name, status_dir=tmp_path / "status")
    assert record is not None
    assert record.success is False
    assert "1" in (record.message or "")


def test_start_reports_running_only_for_stable_process(isolated_state, tmp_path):
    project = _sleepy_project("stable-srv")
    assert start_service(project, logs_dir=tmp_path / "logs") is True
    pid = read_pid(project.name)
    assert pid is not None and is_pid_alive(pid) is True
    reports = build_report(projects=[project], status_dir=tmp_path / "status")
    assert reports[0].health_state == "RUNNING"
    assert stop_service(project) is True


def test_stop_removes_pid_and_verifies_process_gone(isolated_state, tmp_path):
    project = _sleepy_project("stop-verify-srv")
    assert start_service(project, logs_dir=tmp_path / "logs") is True
    pid = read_pid(project.name)
    assert stop_service(project) is True
    assert read_pid(project.name) is None
    assert is_pid_alive(pid) is False
    reports = build_report(projects=[project], status_dir=tmp_path / "status")
    assert reports[0].health_state != "RUNNING"


def test_stop_kills_spawned_child_even_when_pattern_differs(isolated_state, tmp_path):
    """Hub-spawned children are owned via argv[0] even if the discovery pattern
    targets externally supervised processes and does not match the command."""
    project = ProjectEntry(
        name="pattern-mismatch-srv",
        start_command="python3 -c \"import time; time.sleep(15)\"",
        process_pattern="some-external-supervisor-marker-zzz",
        description="test service",
    )
    assert start_service(project, logs_dir=tmp_path / "logs") is True
    pid = read_pid(project.name)
    assert stop_service(project) is True
    assert read_pid(project.name) is None
    assert is_pid_alive(pid) is False


def test_restart_verifies_old_dead_new_alive_pid_differs(isolated_state, tmp_path):
    project = _sleepy_project("restart-verify-srv")
    assert start_service(project, logs_dir=tmp_path / "logs") is True
    old_pid = read_pid(project.name)
    assert restart_service(project, logs_dir=tmp_path / "logs") is True
    new_pid = read_pid(project.name)
    assert new_pid is not None and new_pid != old_pid
    assert is_pid_alive(old_pid) is False
    assert is_pid_alive(new_pid) is True
    assert stop_service(project) is True


def test_stop_never_kills_hub_own_pid(isolated_state):
    project = _sleepy_project("self-pid-srv")
    save_pid(project.name, os.getpid())
    assert stop_service(project) is False
    assert read_pid(project.name) is None
    assert is_pid_alive(os.getpid()) is True


@pytest.mark.skipif(
    not Path("/proc/self/cmdline").exists(), reason="requires /proc cmdline"
)
def test_verify_process_identity_unit():
    assert verify_process_identity(os.getpid(), "pytest") is True
    assert verify_process_identity(os.getpid(), "definitely-not-this-pattern-zzz") is False
    assert verify_process_identity(999999, "pytest") is None
    assert verify_process_identity(os.getpid(), None) is None
    # Hub-spawned child whose discovery pattern does not match its command:
    # argv[0] of the configured start command still proves ownership. Derive
    # argv[0] from our own cmdline so the test is runner-agnostic
    # (`python3 -m pytest` vs the `pytest` console script).
    own_argv0 = (
        Path(f"/proc/{os.getpid()}/cmdline").read_bytes().split(b"\0")[0].decode()
    )
    assert (
        verify_process_identity(
            os.getpid(),
            "definitely-not-this-pattern-zzz",
            start_command=f"{own_argv0} -m something",
        )
        is True
    )
    assert (
        verify_process_identity(
            os.getpid(),
            "definitely-not-this-pattern-zzz",
            start_command="definitely-not-this-binary-zzz --run",
        )
        is False
    )
