from yasinhub.config_manager import ConfigManager
from yasinhub.report import build_report
from yasinhub.registry import ProjectEntry


def test_disabled_services_are_excluded_from_runtime_reports(monkeypatch, tmp_path):
    projects = [
        ProjectEntry(name="active-service", process_pattern=None, enabled=True),
        ProjectEntry(name="yasin-coder", process_pattern="yasin_coder.cli", enabled=False),
        ProjectEntry(name="eitaa_news_v2", process_pattern="eitaa_news_v2.py", enabled=False),
        ProjectEntry(name="backup_manager", process_pattern="backup_manager.py", enabled=False),
    ]

    monkeypatch.setattr("yasinhub.report.read_pid", lambda _name: None)
    monkeypatch.setattr(
        "yasinhub.report.read_status",
        lambda _name, status_dir=None: None,
    )

    reports = build_report(projects=projects, status_dir=tmp_path)

    assert [report.name for report in reports] == ["active-service"]


def test_canonical_registry_state_overrides_stale_enabled_flag(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "projects:\n"
        "  - name: yasin-coder\n"
        "    enabled: true\n"
        "  - name: eitaa_news_v2\n"
        "    enabled: true\n"
        "  - name: backup_manager\n"
        "    enabled: true\n"
        "  - name: yasin-ai\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    manager = ConfigManager(config_path=config_path)
    projects = {project.name: project for project in manager.get_projects()}

    assert projects["yasin-coder"].enabled is False
    assert projects["eitaa_news_v2"].enabled is False
    assert projects["backup_manager"].enabled is False
    assert projects["yasin-ai"].enabled is True
