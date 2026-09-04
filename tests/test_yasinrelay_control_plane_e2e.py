"""Phase 2: real YasinHub ↔ YasinRelay control-plane lifecycle regressions."""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

from yasinhub.pid_store import read_pid, is_pid_alive, remove_pid, save_pid
from yasinhub.registry import ProjectEntry, default_registry
from yasinhub.report import build_report
from yasinhub.service_manager import (
    start_service,
    stop_service,
    restart_service,
    verify_process_identity,
    _command_argv,
)

STANDIN_CODE = "import time; time.sleep(20)  # yasinrelay_e2e_standin_marker"
RECONCILE_CODE = "import time; time.sleep(20)  # yasinrelay_e2e_reconcile_marker"


def _yasinrelay_entry() -> ProjectEntry:
    return next(p for p in default_registry() if p.name == "yasinrelay")


def test_yasinrelay_registry_canonical_start_contract():
    p = _yasinrelay_entry()
    assert p.start_command == (
        ".venv/bin/yasinrelay-termux run --schedule --non-interactive"
    )
    assert p.process_pattern == "yasinrelay.cli"
    assert "YasinRelay" in (p.path or "")
    argv = _command_argv(p.start_command)
    assert argv[0] == ".venv/bin/yasinrelay-termux"
    assert "--schedule" in argv
    assert "--non-interactive" in argv


def test_start_command_argv_has_no_shell_metachar_injection():
    argv = _command_argv(
        ".venv/bin/yasinrelay-termux run --schedule --non-interactive"
    )
    assert len(argv) == 4


def test_real_start_stop_restart_pid_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: tmp_path / "pids")
    (tmp_path / "pids").mkdir(parents=True, exist_ok=True)
    logs = tmp_path / "logs"
    project = ProjectEntry(
        name="yasinrelay-e2e-standin",
        path=str(tmp_path),
        process_pattern="yasinrelay_e2e_standin_marker",
        start_command=f'python3 -c "{STANDIN_CODE}"',
    )
    assert start_service(project, logs_dir=logs) is True
    pid1 = read_pid(project.name)
    assert pid1 is not None and is_pid_alive(pid1)
    assert (
        verify_process_identity(pid1, project.process_pattern, project.start_command)
        is True
    )
    assert stop_service(project) is True
    assert read_pid(project.name) is None
    assert is_pid_alive(pid1) is False
    assert start_service(project, logs_dir=logs) is True
    pid2 = read_pid(project.name)
    assert pid2 is not None and pid2 != pid1 and is_pid_alive(pid2)
    assert restart_service(project, logs_dir=logs) is True
    pid3 = read_pid(project.name)
    assert pid3 is not None and pid3 != pid2 and is_pid_alive(pid3)
    assert is_pid_alive(pid2) is False
    stop_service(project)


def test_startup_failure_when_process_exits_immediately(tmp_path, monkeypatch):
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: tmp_path / "pids")
    (tmp_path / "pids").mkdir(parents=True, exist_ok=True)
    project = ProjectEntry(
        name="yasinrelay-fail-fast",
        path=str(tmp_path),
        start_command='python3 -c "raise SystemExit(1)"',
    )
    assert start_service(project, logs_dir=tmp_path / "logs") is False
    assert read_pid(project.name) is None


def test_out_of_band_crash_clears_running_state(tmp_path, monkeypatch):
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: tmp_path / "pids")
    (tmp_path / "pids").mkdir(parents=True, exist_ok=True)
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    project = ProjectEntry(
        name="yasinrelay-crash",
        path=str(tmp_path),
        process_pattern="yasinrelay_e2e_standin_marker",
        start_command=f'python3 -c "{STANDIN_CODE}"',
    )
    assert start_service(project, logs_dir=tmp_path / "logs") is True
    pid = read_pid(project.name)
    assert pid and is_pid_alive(pid)
    os.kill(pid, 9)
    time.sleep(0.3)
    assert is_pid_alive(pid) is False
    reports = build_report([project], status_dir=status_dir)
    assert reports[0].process_running is False
    assert reports[0].health_state != "RUNNING"


def test_stop_does_not_kill_foreign_pid(tmp_path, monkeypatch):
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: tmp_path / "pids")
    (tmp_path / "pids").mkdir(parents=True, exist_ok=True)
    project = ProjectEntry(
        name="yasinrelay-foreign",
        process_pattern="this-pattern-will-never-match-zzzz",
        start_command="python3 -c 'pass'",
    )
    self_pid = os.getpid()
    save_pid(project.name, self_pid)
    stop_service(project)
    assert is_pid_alive(self_pid) is True
    assert read_pid(project.name) is None


def test_hub_restart_reconciles_existing_process(tmp_path, monkeypatch):
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: tmp_path / "pids")
    (tmp_path / "pids").mkdir(parents=True, exist_ok=True)
    project = ProjectEntry(
        name="yasinrelay-reconcile",
        path=str(tmp_path),
        process_pattern="yasinrelay_e2e_reconcile_marker",
        start_command=f'python3 -c "{RECONCILE_CODE}"',
    )
    assert start_service(project, logs_dir=tmp_path / "logs") is True
    pid = read_pid(project.name)
    assert pid and is_pid_alive(pid)
    remove_pid(project.name)
    assert read_pid(project.name) is None
    reports = build_report([project], status_dir=tmp_path / "status")
    assert reports[0].process_running is True
    assert reports[0].health_state == "RUNNING"
    assert read_pid(project.name) == pid
    stop_service(project)


def test_yasinrelay_start_uses_project_path_as_cwd(monkeypatch, tmp_path):
    project = _yasinrelay_entry()
    captured = {}

    class FakeProc:
        pid = 424242

        def poll(self):
            return None

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["cwd"] = kwargs.get("cwd")
        captured["shell"] = kwargs.get("shell")
        return FakeProc()

    monkeypatch.setattr("yasinhub.service_manager.subprocess.Popen", fake_popen)
    monkeypatch.setattr("yasinhub.service_manager.read_pid", lambda name: None)
    monkeypatch.setattr(
        "yasinhub.service_manager.check_process",
        lambda pattern: SimpleNamespace(running=False, pids=[]),
    )
    monkeypatch.setattr("yasinhub.service_manager.save_pid", lambda name, pid: None)
    monkeypatch.setattr(
        "yasinhub.service_manager._wait_for_stable_start",
        lambda proc, grace=None, interval=None: None,
    )
    monkeypatch.setattr("yasinhub.service_manager._mark_running", lambda name: None)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    assert start_service(project, logs_dir=tmp_path) is True
    assert captured["shell"] is False
    assert captured["argv"][0] == ".venv/bin/yasinrelay-termux"
    assert "--non-interactive" in captured["argv"]
    assert captured["cwd"] == project.path
