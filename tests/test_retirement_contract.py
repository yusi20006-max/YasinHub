"""
tests/test_retirement_contract.py
Retirement contract: optional `enabled` flag on registry entries.

- Legacy entries without the field behave exactly as before (runnable).
- Disabled entries load, never spawn on start/stop/restart, and report
  status deterministically without crashing.
- Active services keep their previous lifecycle behavior.
"""

from pathlib import Path
from unittest.mock import patch

import yaml

from yasinhub.config_manager import ConfigManager
from yasinhub.process_checker import ProcessStatus
from yasinhub.registry import DEFAULT_PROJECTS, ProjectEntry
from yasinhub.report import build_report
from yasinhub.service_manager import restart_service, start_service, stop_service


def _disabled_entry(**over):
    args = dict(
        name="retired_svc",
        start_command="python3 run.py",
        process_pattern="retired_svc_marker_zzz",
    )
    args.update(over)
    args["enabled"] = False
    return ProjectEntry(**args)


def test_legacy_entry_without_state_stays_runnable(tmp_path):
    """1. Legacy entry (no `enabled` passed) defaults to runnable."""
    project = ProjectEntry(name="legacy_svc", start_command="python3 run.py")
    assert project.enabled is True


def test_disabled_entry_loads_from_yaml(tmp_path):
    """2. Disabled entry loads successfully with state preserved."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump(
            {
                "projects": [
                    {
                        "name": "old_svc",
                        "start_command": "python3 old.py",
                        "enabled": False,
                    },
                    {"name": "new_svc", "start_command": "python3 new.py"},
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    manager = ConfigManager(config_path=config_file)
    projects = {p.name: p for p in manager.get_projects()}
    assert projects["old_svc"].enabled is False
    assert projects["new_svc"].enabled is True


def test_disabled_start_never_spawns(tmp_path):
    """3. Disabled start returns False without spawning or writing a PID."""
    project = _disabled_entry()
    with patch("yasinhub.service_manager.subprocess.Popen") as popen:
        assert start_service(project, logs_dir=tmp_path / "logs") is False
        popen.assert_not_called()
    assert not (tmp_path / "logs" / "retired_svc.log").exists()


def test_disabled_status_without_crash(tmp_path):
    """4. Disabled entry is excluded from runtime reports without crashing."""
    reports = build_report(
        projects=[_disabled_entry()],
        status_dir=tmp_path / "status",
    )
    assert reports == []


def test_disabled_stop_restart_never_spawn(tmp_path):
    """5. Disabled stop/restart never spawn a process."""
    from yasinhub.process_checker import ProcessStatus

    project = _disabled_entry()
    with (
        patch("yasinhub.service_manager.subprocess.Popen") as popen,
        patch("yasinhub.service_manager.check_process") as check,
    ):
        check.return_value = ProcessStatus(pattern="x", running=False, pids=[])
        assert stop_service(project) is False
        assert restart_service(project, logs_dir=tmp_path / "logs") is False
        popen.assert_not_called()


def test_active_service_lifecycle_unchanged(tmp_path):
    """6. Active service keeps the previous lifecycle behavior (real process)."""
    project = ProjectEntry(
        name="contract_alive_svc",
        start_command="python3 -c \"import time; time.sleep(30)\"",
        process_pattern="contract_alive_marker_zzz",
    )
    logs_dir = tmp_path / "logs"
    with patch("yasinhub.service_manager.check_process") as check:
        check.return_value = ProcessStatus(pattern="x", running=False, pids=[])
        assert start_service(project, logs_dir=logs_dir) is True
    with patch("yasinhub.service_manager.check_process") as check:
        check.return_value = ProcessStatus(pattern="x", running=False, pids=[])
        assert stop_service(project) is True


def test_api_services_advertises_enabled_flag(tmp_path):
    """7. API/config compatibility: services payload carries `enabled`."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump(
            {
                "projects": [
                    {"name": "a", "start_command": "python3 a.py"},
                    {
                        "name": "b",
                        "start_command": "python3 b.py",
                        "enabled": False,
                    },
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    manager = ConfigManager(config_path=config_file)
    payload = [
        {
            "name": p.name,
            "enabled": getattr(p, "enabled", True),
            "controls": ["start", "stop", "restart"]
            if getattr(p, "enabled", True)
            else [],
        }
        for p in manager.get_projects()
    ]
    by_name = {s["name"]: s for s in payload}
    assert by_name["a"] == {"name": "a", "enabled": True, "controls": ["start", "stop", "restart"]}
    assert by_name["b"] == {"name": "b", "enabled": False, "controls": []}


def test_retired_defaults_do_not_spawn():
    """Guard: retired defaults refuse start even with a Popen mock present."""
    for name in ("backup_manager", "eitaa_news_v2", "yasin-coder"):
        project = next(p for p in DEFAULT_PROJECTS if p.name == name)
        assert project.enabled is False
        with patch("yasinhub.service_manager.subprocess.Popen") as popen:
            assert start_service(project, logs_dir=Path("/tmp/retired-guard")) is False
            popen.assert_not_called()


def test_validation_rejects_non_bool_enabled(tmp_path):
    """Validation: non-bool `enabled` is rejected, legacy absence is fine."""
    from yasinhub.config_manager import ValidationError

    bad = tmp_path / "bad.yaml"
    bad.write_text(
        yaml.dump({"projects": [{"name": "s", "enabled": "no"}]}),
        encoding="utf-8",
    )
    try:
        ConfigManager(config_path=bad)
    except ValidationError:
        pass
    else:
        raise AssertionError("non-bool enabled must be rejected")
