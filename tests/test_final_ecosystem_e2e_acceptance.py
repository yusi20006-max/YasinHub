"""Final software-side ecosystem E2E acceptance checks for Issue #174.

These checks deliberately stop at the software boundary. They prove the Hub's
real-process lifecycle and the PWA's authoritative-state contract, while the
physical Android/Termux and credentialed publish boundary remains operator-only.
"""

from __future__ import annotations

import os
from pathlib import Path

from yasinhub.pid_store import get_pid_dir, is_pid_alive, read_pid
from yasinhub.registry import ProjectEntry, default_registry
from yasinhub.service_manager import restart_service, start_service, stop_service


STANDIN = "import time; time.sleep(15)  # final_ecosystem_e2e_marker"


def test_final_e2e_registry_and_architecture_contract():
    """The canonical Relay launcher remains the only Hub start contract."""
    relay = next(p for p in default_registry() if p.name == "yasinrelay")
    assert relay.start_command == ".venv/bin/yasinrelay-termux run --schedule --non-interactive"
    assert relay.process_pattern == "yasinrelay.cli"

    repo_root = Path(__file__).resolve().parents[1]
    app_text = (repo_root / "yasinhub" / "service_manager.py").read_text(encoding="utf-8")
    assert "shell=False" in app_text
    assert "verify_process_identity" in app_text


def test_final_e2e_real_process_lifecycle(tmp_path, monkeypatch):
    """Prove START → STOP → START → RESTART using real child processes."""
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir()
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: pid_dir)

    project = ProjectEntry(
        name="final-ecosystem-e2e",
        path=str(tmp_path),
        process_pattern="final_ecosystem_e2e_marker",
        start_command=f'python3 -c "{STANDIN}"',
    )
    logs = tmp_path / "logs"

    assert start_service(project, logs_dir=logs) is True
    pid1 = read_pid(project.name)
    assert pid1 is not None and is_pid_alive(pid1)

    assert stop_service(project) is True
    assert read_pid(project.name) is None
    assert not is_pid_alive(pid1)

    assert start_service(project, logs_dir=logs) is True
    pid2 = read_pid(project.name)
    assert pid2 is not None and pid2 != pid1 and is_pid_alive(pid2)

    assert restart_service(project, logs_dir=logs) is True
    pid3 = read_pid(project.name)
    assert pid3 is not None and pid3 != pid2 and is_pid_alive(pid3)
    assert not is_pid_alive(pid2)

    assert stop_service(project) is True
    assert read_pid(project.name) is None
    assert not is_pid_alive(pid3)


def test_final_e2e_pwa_uses_authoritative_backend_state():
    """Guard the PWA contract against optimistic lifecycle state regressions."""
    repo_root = Path(__file__).resolve().parents[1]
    views = (repo_root / "dashboard" / "js" / "views.js").read_text(encoding="utf-8")
    controls = (repo_root / "dashboard" / "service-controls.js").read_text(encoding="utf-8")

    assert 'project.pid!=null&&project.pid!==""' in views
    assert "data.success===true" in controls
    assert "data-lifecycle-pending" in controls
    assert "formatAuthoritativeResult" in controls
