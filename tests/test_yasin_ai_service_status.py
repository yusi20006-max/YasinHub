from pathlib import Path
from types import SimpleNamespace

from yasinhub.registry import DEFAULT_PROJECTS, ProjectEntry
from yasinhub.report import build_report
from yasinhub.service_manager import start_service


def test_yasin_ai_registry_uses_long_running_canonical_command():
    project = next(p for p in DEFAULT_PROJECTS if p.name == "yasin-ai")

    assert project.path == str(Path.home() / "yasineco" / "Yasin-AI")
    assert project.process_pattern == "yasinai.cli.main serve"
    assert project.start_command == "yasin serve"


def test_build_report_reconciles_stale_yasin_ai_failure(monkeypatch, tmp_path):
    project = ProjectEntry(
        name="yasin-ai",
        path=str(tmp_path),
        process_pattern="yasinai.cli.main serve",
        start_command="yasin serve",
    )

    monkeypatch.setattr(
        "yasinhub.report.check_process",
        lambda pattern: SimpleNamespace(pattern=pattern, running=True, pids=["4242"]),
    )
    monkeypatch.setattr("yasinhub.report.read_pid", lambda name: None)
    monkeypatch.setattr("yasinhub.report.save_pid", lambda name, pid: None)
    monkeypatch.setattr("yasinhub.report.is_pid_alive", lambda pid: False)
    monkeypatch.setattr("yasinhub.report.remove_pid", lambda name: None)

    from yasinhub.status_store import write_status

    write_status("yasin-ai", success=False, message="old path failure", status_dir=tmp_path)

    reports = build_report([project], status_dir=tmp_path)
    report = reports[0]

    assert report.process_running is True
    assert report.health_state == "RUNNING"
    assert report.last_success is True
    assert report.last_message == "observed running"


def test_start_service_records_running_status(monkeypatch, tmp_path):
    project = ProjectEntry(
        name="yasin-ai",
        path=str(tmp_path),
        process_pattern=None,
        start_command="yasin serve",
    )

    class FakeProcess:
        pid = 9876

        @staticmethod
        def poll():
            return None

    monkeypatch.setattr("yasinhub.service_manager.read_pid", lambda name: None)
    monkeypatch.setattr("yasinhub.service_manager.subprocess.Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr("yasinhub.service_manager.save_pid", lambda name, pid: None)
    monkeypatch.setattr("yasinhub.service_manager.time.sleep", lambda _: None)
    monkeypatch.setattr("yasinhub.service_manager._service_env", lambda project: {})
    monkeypatch.setattr("yasinhub.config_manager.get_status_dir", lambda: tmp_path)

    assert start_service(project, logs_dir=tmp_path) is True

    import json

    record = json.loads((tmp_path / "yasin-ai.json").read_text(encoding="utf-8"))
    assert record["success"] is True
    assert record["message"] == "observed running"
