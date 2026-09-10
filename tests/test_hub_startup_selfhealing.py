"""Issue #180: YasinHub startup self-healing on dedicated port 7000.

Focused tests for yasinhub.startup — the official single-command launcher:

    preflight -> identify -> safely restart if YasinHub -> start -> verify

Safe by construction: ownership/lifecycle behavior uses controlled fixtures
and test doubles. No real user process is signaled or killed; the only live
sockets are isolated loopback servers on test-only ports (never 7000).
"""

from __future__ import annotations

import os
import socket
import subprocess

import pytest

from yasinhub import startup
from yasinhub.startup import (
    HubVerifyResult,
    PreflightResult,
    is_yasinhub_process,
    preflight_hub_port,
    resolve_hub_port,
    run_startup,
    sanitize_cmdline,
    stop_hub_gracefully,
    verify_hub_running,
)


def _free_test_port() -> int:
    for candidate in (7090, 7091, 7092, 7093, 7094, 7095, 7096, 7097, 7098, 7099):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return candidate
    raise RuntimeError("no free test port")


class _FakeProc:
    def __init__(self, pid: int):
        self.pid = pid
        self._code = None

    def poll(self):
        return self._code


def _ok_verify(pid: int) -> HubVerifyResult:
    return HubVerifyResult(
        running=True,
        pid=pid,
        identity=True,
        port_owned=True,
        listening=True,
        health_ok=True,
        reasons=["ok"],
    )


# ---------------------------------------------------------------------------
# 1-6: free port -> full restart path with verified new PID
# ---------------------------------------------------------------------------

def test_free_port_startup_proceeds_and_verifies(monkeypatch):
    port = _free_test_port()
    pre = PreflightResult(port=port, occupied=False, decision="free", detail="free")
    started = {}

    def fake_start():
        started["called"] = True
        return _FakeProc(pid=111111)

    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: pre,
        start_fn=fake_start,
        verify_fn=_ok_verify,
        verify_timeout=1.0,
    )
    assert result.success is True
    assert result.action == "started"
    assert result.pid == 111111
    assert result.port == port
    assert started.get("called") is True
    assert result.verify is not None and result.verify.running is True


def test_occupied_by_hub_graceful_stop_release_restart(monkeypatch):
    port = _free_test_port()
    old_pid, new_pid = 222221, 222222
    pre = PreflightResult(
        port=port, occupied=True, decision="yasinhub",
        proc_owner_pids=[old_pid], hub_pids=[old_pid], detail="hub owns",
    )
    calls: dict = {}

    def fake_stop(pid, timeout):
        calls.setdefault("stopped", []).append(pid)
        return True

    def fake_wait():
        calls["waited"] = True
        return True

    def fake_start():
        calls["started"] = True
        return _FakeProc(pid=new_pid)

    def fake_verify(pid):
        calls["verified"] = pid
        assert pid == new_pid and pid != old_pid
        return _ok_verify(pid)

    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: pre,
        stop_fn=fake_stop,
        wait_release_fn=fake_wait,
        start_fn=fake_start,
        verify_fn=fake_verify,
        verify_timeout=1.0,
    )
    assert result.success is True
    assert result.action == "restarted"
    assert calls["stopped"] == [old_pid]
    assert calls["waited"] is True
    assert calls["started"] is True
    assert calls["verified"] == new_pid
    assert result.pid == new_pid != old_pid


def test_new_pid_differs_and_listening_verified(monkeypatch):
    """New PID must differ; verification must cover listening + health."""
    port = _free_test_port()
    pre = PreflightResult(
        port=port, occupied=True, decision="yasinhub",
        proc_owner_pids=[333331], hub_pids=[333331], detail="hub owns",
    )
    seen: dict = {}

    def fake_verify(pid):
        seen["pid"] = pid
        return HubVerifyResult(
            running=True, pid=pid, identity=True, port_owned=True,
            listening=True, health_ok=True, reasons=["identity+port+health"],
        )

    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: pre,
        stop_fn=lambda pid, timeout: True,
        wait_release_fn=lambda: True,
        start_fn=lambda: _FakeProc(pid=333332),
        verify_fn=fake_verify,
        verify_timeout=1.0,
    )
    assert result.success is True
    assert seen["pid"] == 333332 != 333331
    assert result.verify is not None
    assert result.verify.listening is True
    assert result.verify.health_ok is True
    assert result.verify.identity is True


def test_pid_reuse_fails_closed(monkeypatch):
    port = _free_test_port()
    pre = PreflightResult(
        port=port, occupied=True, decision="yasinhub",
        proc_owner_pids=[444441], hub_pids=[444441], detail="hub owns",
    )
    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: pre,
        stop_fn=lambda pid, timeout: True,
        wait_release_fn=lambda: True,
        start_fn=lambda: _FakeProc(pid=444441),  # reuses old PID
        verify_fn=_ok_verify,
        verify_timeout=1.0,
    )
    assert result.success is False
    assert "reuse" in result.detail


# ---------------------------------------------------------------------------
# 7-8: unrelated owner -> FAIL CLOSED, never killed
# ---------------------------------------------------------------------------

def test_unrelated_owner_fails_closed_and_never_killed(monkeypatch):
    port = _free_test_port()
    foreign = 555551
    pre = PreflightResult(
        port=port, occupied=True, decision="foreign",
        proc_owner_pids=[foreign], foreign_pids=[foreign],
        detail="occupied by foreign",
    )
    killed: list = []
    started: list = []

    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: pre,
        stop_fn=lambda pid, timeout: killed.append(pid) or True,
        wait_release_fn=lambda: True,
        start_fn=lambda: started.append(1) or _FakeProc(pid=555552),
        verify_fn=_ok_verify,
        verify_timeout=1.0,
    )
    assert result.success is False
    assert result.action == "refused"
    assert killed == [], "unrelated process must never be killed"
    assert started == [], "must not start while a foreign owner holds the port"


def test_preflight_classifies_foreign_owner_by_identity(monkeypatch):
    port = _free_test_port()
    monkeypatch.setattr(startup, "port_owner_pids", lambda p: {777001})
    monkeypatch.setattr(startup, "is_port_occupied", lambda h, p: True)
    monkeypatch.setattr(startup, "is_yasinhub_process", lambda pid: False)
    pre = preflight_hub_port("127.0.0.1", port)
    assert pre.occupied is True
    assert pre.decision == "foreign"
    assert pre.foreign_pids == [777001]


# ---------------------------------------------------------------------------
# 9-10: stale/dead PID + incomplete metadata -> safe failure
# ---------------------------------------------------------------------------

def test_stale_dead_pid_is_safe(monkeypatch):
    dead_pid = 999991
    monkeypatch.setattr(startup, "is_pid_alive", lambda pid: False)
    assert stop_hub_gracefully(dead_pid, timeout=0.5) is True
    assert is_yasinhub_process(dead_pid) is None


def test_incomplete_metadata_fails_closed(monkeypatch):
    port = _free_test_port()
    monkeypatch.setattr(startup, "port_owner_pids", lambda p: {888001})
    monkeypatch.setattr(startup, "is_port_occupied", lambda h, p: True)
    monkeypatch.setattr(startup, "is_yasinhub_process", lambda pid: None)
    pre = preflight_hub_port("127.0.0.1", port)
    assert pre.decision == "indeterminate"
    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: pre,
        stop_fn=lambda pid, timeout: (_ for _ in ()).throw(AssertionError("must not kill")),
        start_fn=lambda: (_ for _ in ()).throw(AssertionError("must not start")),
        verify_timeout=1.0,
    )
    assert result.success is False
    assert result.action == "refused"


def test_indeterminable_ownership_without_hub_anchor_refuses(monkeypatch):
    port = _free_test_port()
    monkeypatch.setattr(startup, "port_owner_pids", lambda p: None)
    monkeypatch.setattr(startup, "is_port_occupied", lambda h, p: True)
    monkeypatch.setattr(startup, "hub_pid_candidates", lambda: [])
    monkeypatch.setattr(startup, "optional_external_owners", lambda p: set())
    pre = preflight_hub_port("127.0.0.1", port)
    assert pre.decision == "indeterminate"


# ---------------------------------------------------------------------------
# 11: previous Hub refuses to stop -> safe failure, no new start
# ---------------------------------------------------------------------------

def test_hub_refusing_to_stop_fails_safely(monkeypatch):
    port = _free_test_port()
    old_pid = 666661
    pre = PreflightResult(
        port=port, occupied=True, decision="yasinhub",
        proc_owner_pids=[old_pid], hub_pids=[old_pid], detail="hub owns",
    )
    started: list = []
    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: pre,
        stop_fn=lambda pid, timeout: False,  # refuses to stop
        wait_release_fn=lambda: (_ for _ in ()).throw(AssertionError("no wait expected")),
        start_fn=lambda: started.append(1) or _FakeProc(pid=666662),
        verify_fn=_ok_verify,
        verify_timeout=1.0,
    )
    assert result.success is False
    assert "did not stop" in result.detail
    assert started == []


def test_port_lingering_after_stop_fails_safely(monkeypatch):
    port = _free_test_port()
    old_pid = 666671
    pre = PreflightResult(
        port=port, occupied=True, decision="yasinhub",
        proc_owner_pids=[old_pid], hub_pids=[old_pid], detail="hub owns",
    )
    started: list = []
    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: pre,
        stop_fn=lambda pid, timeout: True,
        wait_release_fn=lambda: False,  # port still occupied
        start_fn=lambda: started.append(1) or _FakeProc(pid=666672),
        verify_fn=_ok_verify,
        verify_timeout=1.0,
    )
    assert result.success is False
    assert "still occupied" in result.detail
    assert started == []


def test_stop_uses_sigterm_not_sigkill(monkeypatch):
    """Normal path sends SIGTERM and never SIGKILL."""
    import signal as sigmod

    signals: list = []
    monkeypatch.setattr(startup, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(startup, "is_yasinhub_process", lambda pid: True)

    def fake_kill(pid, sig):
        signals.append(sig)
        raise ProcessLookupError()

    monkeypatch.setattr(startup.os, "kill", fake_kill)
    assert stop_hub_gracefully(123456, timeout=0.5) is True
    assert signals == [sigmod.SIGTERM]
    assert sigmod.SIGKILL not in signals


# ---------------------------------------------------------------------------
# 12: non-interactive launcher
# ---------------------------------------------------------------------------

def test_launcher_is_non_interactive(monkeypatch, capsys):
    port = _free_test_port()

    def no_input(*args, **kwargs):
        raise AssertionError("launcher must never prompt for input")

    monkeypatch.setattr("builtins.input", no_input)
    monkeypatch.setattr(startup, "run_startup", lambda **kw: startup.StartupResult(
        success=True, action="started", pid=101010, port=port, detail="ok",
    ))
    rc = startup.main(["--port", str(port)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ok" in out


def test_main_refuses_foreign_without_prompt(monkeypatch, capsys):
    port = _free_test_port()

    def no_input(*args, **kwargs):
        raise AssertionError("launcher must never prompt")

    monkeypatch.setattr("builtins.input", no_input)
    monkeypatch.setattr(
        startup, "run_startup",
        lambda **kw: startup.StartupResult(
            success=False, action="refused", port=port,
            detail="port occupied by unknown owner; fail closed",
            preflight=PreflightResult(port=port, occupied=True, decision="foreign"),
        ),
    )
    rc = startup.main(["--port", str(port)])
    assert rc == 1
    assert "refused" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 13: no lsof/fuser hard dependency
# ---------------------------------------------------------------------------

def test_launcher_works_without_lsof_fuser_ss(monkeypatch):
    port = _free_test_port()
    monkeypatch.setattr(startup.shutil, "which", lambda name: None)
    assert startup.optional_external_owners(port) == set()
    # Preflight with free port needs no external tools at all.
    monkeypatch.setattr(startup, "port_owner_pids", lambda p: set())
    monkeypatch.setattr(startup, "is_port_occupied", lambda h, p: False)
    pre = preflight_hub_port("127.0.0.1", port)
    assert pre.decision == "free"
    # Full run also succeeds without external tools.
    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: PreflightResult(port=port, decision="free"),
        start_fn=lambda: _FakeProc(pid=202020),
        verify_fn=_ok_verify,
        verify_timeout=1.0,
    )
    assert result.success is True


def test_no_subprocess_lsof_fuser_in_required_path(monkeypatch):
    """Required path (free port) must not shell out to lsof/fuser/ss."""
    import pathlib

    source = pathlib.Path(startup.__file__).read_text(encoding="utf-8")
    head, _, _tail = source.partition("def optional_external_owners")
    # The optional helper is the only place allowed to exec these tools.
    assert 'which("lsof")' not in head
    assert 'which("fuser")' not in head
    assert 'which("ss")' not in head
    assert '"lsof"' not in head
    assert '"fuser"' not in head


# ---------------------------------------------------------------------------
# 14: no secrets printed or persisted
# ---------------------------------------------------------------------------

def test_no_secrets_in_output(monkeypatch, capsys, tmp_path):
    port = _free_test_port()
    secret = "SECRET-TOKEN-ABC-123-XYZ"
    monkeypatch.setenv("YASIN_AGENT_SERVICE_TOKEN", secret)
    monkeypatch.setenv("YASINHUB_API_KEY", secret)
    monkeypatch.setattr(startup.time, "sleep", lambda s: None)
    result = run_startup(
        port=port,
        preflight_fn=lambda: PreflightResult(
            port=port, occupied=True, decision="foreign",
            proc_owner_pids=[909001], foreign_pids=[909001],
            detail="occupied",
        ),
        verify_timeout=1.0,
    )
    assert result.success is False
    rc = startup.main(["--port", str(port)])
    assert rc in (0, 1)
    out = capsys.readouterr().out
    assert secret not in out


def test_cmdline_sanitizer_redacts_secrets():
    nasty = "python -m yasinhub.api.server --token=SECRET-TOKEN-ABC api_key=XYZ password=hunter2"
    clean = sanitize_cmdline(nasty)
    assert "SECRET-TOKEN-ABC" not in clean
    assert "hunter2" not in clean
    assert "***" in clean
    assert "yasinhub.api.server" in clean


def test_verify_requires_all_gates(monkeypatch):
    port = _free_test_port()
    monkeypatch.setattr(startup, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(startup, "is_yasinhub_process", lambda pid: True)
    monkeypatch.setattr(startup, "is_port_occupied", lambda h, p: False)
    monkeypatch.setattr(startup, "port_owner_pids", lambda p: set())
    verdict = verify_hub_running(424242, "127.0.0.1", port)
    assert verdict.running is False  # not listening -> not RUNNING


def test_resolve_hub_port_defaults_to_7000(monkeypatch):
    monkeypatch.delenv("YASINHUB_PORT", raising=False)
    assert resolve_hub_port() == 7000


def test_live_socket_listening_detection():
    """Real loopback listener is observed as occupied (Termux-safe)."""
    port = _free_test_port()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    try:
        assert startup.is_port_occupied("127.0.0.1", port) is True
    finally:
        server.close()
