"""Phase 3: device/Control Plane contract regressions (no secrets, no fake channels)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from yasinhub.registry import ProjectEntry, default_registry
from yasinhub.service_manager import _service_env, start_service
from yasinhub.services.doctor_service import DoctorService


def test_doctor_reports_termux_and_control_plane_sections():
    result = DoctorService().run()
    assert "termux" in result
    assert "control_plane" in result
    assert "python" in result
    assert result["control_plane"]["status"] == "ok"
    assert result["control_plane"]["yasinrelay"]["canonical"] is True
    assert (
        result["control_plane"]["yasinrelay"]["start_command"]
        == ".venv/bin/yasinrelay-termux run --schedule --non-interactive"
    )


def test_service_env_preserves_ld_preload(monkeypatch, tmp_path):
    """Hub must not strip Termux LD_PRELOAD when spawning managed services."""
    monkeypatch.setenv(
        "LD_PRELOAD", "/data/data/com.termux/files/usr/lib/libpython3.14.so"
    )
    project = ProjectEntry(
        name="yasinrelay",
        path=str(tmp_path),
        start_command=".venv/bin/yasinrelay-termux run --schedule --non-interactive",
    )
    env = _service_env(project)
    assert "LD_PRELOAD" in env
    assert env["LD_PRELOAD"].endswith("libpython3.14.so")
    assert str(tmp_path) in env.get("PYTHONPATH", "")


def test_service_env_does_not_invent_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("SOURCE_CHANNELS", raising=False)
    monkeypatch.delenv("EITAA_TOKEN", raising=False)
    project = ProjectEntry(name="yasinrelay", path=str(tmp_path))
    env = _service_env(project)
    assert "SOURCE_CHANNELS" not in env or env.get("SOURCE_CHANNELS") == os.environ.get(
        "SOURCE_CHANNELS"
    )
    assert env.get("EITAA_TOKEN") == os.environ.get("EITAA_TOKEN")


def test_registry_yasinrelay_canonical_on_main():
    relay = next(p for p in default_registry() if p.name == "yasinrelay")
    assert relay.start_command == (
        ".venv/bin/yasinrelay-termux run --schedule --non-interactive"
    )
    assert relay.process_pattern == "yasinrelay.cli"


def test_hub_start_propagates_env_including_ld_preload(monkeypatch, tmp_path):
    project = next(p for p in default_registry() if p.name == "yasinrelay")
    captured = {}

    class FakeProc:
        pid = 999001

        def poll(self):
            return None

    def fake_popen(argv, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        captured["shell"] = kwargs.get("shell")
        return FakeProc()

    monkeypatch.setenv("LD_PRELOAD", "libpython-test.so")
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
    assert captured["env"].get("LD_PRELOAD") == "libpython-test.so"


def test_phase3_device_on_device_flag_false_in_ci():
    """CI/sandbox is not Termux; doctor must not claim on_device without PREFIX."""
    termux = DoctorService().termux_check()
    if os.environ.get("PREFIX") != "/data/data/com.termux/files/usr":
        assert termux["on_device"] is False
