"""Canonical ecosystem-root migration regressions.

YASIN_ECOSYSTEM_ROOT is ~/YasinEco. No active runtime code may construct
paths from the legacy ~/yasineco tree; persisted legacy config must migrate
to the canonical root via ConfigManager (never by hand-editing Termux files,
never by touching the legacy directory itself).

Legacy ~/yasineco strings below appear ONLY as migration input fixtures.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from yasinhub import registry
from yasinhub.config_manager import ConfigManager
from yasinhub.registry import DEFAULT_PROJECTS, YASIN_ECOSYSTEM_ROOT


def test_default_agent_path_is_canonical_root():
    agent = next(p for p in DEFAULT_PROJECTS if p.name == "yasin-agent")
    assert agent.path == str(YASIN_ECOSYSTEM_ROOT / "Yasin-agent")


def test_default_agent_start_command_is_canonical():
    agent = next(p for p in DEFAULT_PROJECTS if p.name == "yasin-agent")
    assert str(YASIN_ECOSYSTEM_ROOT) in (agent.start_command or "")
    assert "/yasineco/" not in (agent.start_command or "")
    assert "Yasin-agent" in (agent.start_command or "")
    assert agent.start_command.endswith("-m agent_platform.server")


def test_no_default_project_start_uses_legacy_root():
    for project in DEFAULT_PROJECTS:
        for field in (project.path, project.start_command, project.stop_command):
            assert field is None or "/yasineco/" not in field, project.name


def _write_legacy_config(tmp_path, projects):
    config_file = tmp_path / "legacy-migration.yaml"
    config_file.write_text(yaml.dump({"projects": projects}), encoding="utf-8")
    return config_file


def test_legacy_agent_config_cannot_keep_legacy_start(tmp_path, monkeypatch):
    """A persisted stale Agent command must not survive ConfigManager load."""
    from yasinhub import registry as registry_module

    canonical_root = tmp_path / "YasinEco"
    (canonical_root / "Yasin-agent").mkdir(parents=True)
    monkeypatch.setattr(registry_module, "YASIN_ECOSYSTEM_ROOT", canonical_root)

    legacy_home = str(Path.home() / "yasineco")
    config_file = _write_legacy_config(tmp_path, [{
        "name": "yasin-agent",
        "path": f"{legacy_home}/Yasin-agent",
        "process_pattern": "agent_platform.server",
        "start_command": f"{legacy_home}/Yasin-agent/.venv/bin/python -m agent_platform.server",
    }])
    project = ConfigManager(config_path=config_file).get_projects()[0]
    assert "/yasineco/" not in (project.start_command or "")
    assert project.path == str(canonical_root / "Yasin-agent")


def test_legacy_service_paths_canonicalized(tmp_path, monkeypatch):
    """Feed/relay/AI/press legacy paths resolve under the canonical root."""
    from yasinhub import registry as registry_module

    canonical_root = tmp_path / "YasinEco"
    expected = {
        "yasinfeed": "Yasinfeed",
        "yasinrelay": "YasinRelay",
        "yasin-ai": "Yasin-AI",
        "yasinpress": "YasinPress-Rewrite-",
    }
    for dirname in expected.values():
        (canonical_root / dirname).mkdir(parents=True)
    monkeypatch.setattr(registry_module, "YASIN_ECOSYSTEM_ROOT", canonical_root)

    legacy_home = str(Path.home() / "yasineco")
    config_file = _write_legacy_config(tmp_path, [
        {"name": name, "path": f"{legacy_home}/{dirname}"}
        for name, dirname in expected.items()
    ])
    projects = {p.name: p for p in ConfigManager(config_path=config_file).get_projects()}
    for name, dirname in expected.items():
        assert projects[name].path == str(canonical_root / dirname), name


def test_disabled_services_survive_migration(tmp_path):
    """Migration must not enable retired services or drop their flags."""
    config_file = _write_legacy_config(tmp_path, [
        {"name": "yasin-coder", "enabled": False},
        {"name": "eitaa_news_v2", "enabled": False},
        {"name": "backup_manager", "enabled": False},
        {"name": "yasinrelay", "enabled": True},
    ])
    projects = {p.name: p for p in ConfigManager(config_path=config_file).get_projects()}
    assert projects["yasin-coder"].enabled is False
    assert projects["eitaa_news_v2"].enabled is False
    assert projects["backup_manager"].enabled is False
    assert projects["yasinrelay"].enabled is True


def test_port_contract_intact_after_migration(tmp_path):
    """Migration keeps verified HTTP ports and portless workers."""
    config_file = _write_legacy_config(tmp_path, [
        {"name": "yasin-agent", "port": 8080},
        {"name": "yasinfeed", "port": 8101},
        {"name": "yasinpress", "port": 7003},
        {"name": "yasinrelay"},
        {"name": "yasin-ai"},
    ])
    projects = {p.name: p for p in ConfigManager(config_path=config_file).get_projects()}
    assert projects["yasin-agent"].port == 7002
    assert projects["yasinfeed"].port == 7004
    assert projects["yasinpress"].port is None
    assert projects["yasinrelay"].port is None
    assert projects["yasin-ai"].port is None


def test_live_default_registry_has_no_legacy_start():
    """End-to-end over the real ~/.yasinhub/config.yaml: no legacy leakage."""
    from yasinhub.registry import default_registry

    for project in default_registry():
        for field in (project.path, project.start_command, project.stop_command):
            assert field is None or "/yasineco/" not in field, project.name
