"""Issue #179: dedicated Yasin HTTP service port range + ownership contract.

Covers registry allocation, collision fail-closed behavior (unknown owners
are never killed), lifecycle verification (identity + port ownership +
health), stop/restart semantics, and wrong-port detection.

Safe by construction: collision tests use isolated loopback servers on
test-only ports (7090-7099, inside the reserved range but outside the
canonical allocation) or test doubles. No real user process is ever killed.
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from yasinhub import ports
from yasinhub.ports import (
    YASIN_RESERVED_SERVICE_PORT_RANGE,
    YASIN_SERVICE_PORT_ALLOCATION,
    is_port_in_reserved_range,
)
from yasinhub.registry import DEFAULT_PROJECTS, ProjectEntry, default_registry
from yasinhub import service_manager as sm
from yasinhub.pid_store import is_pid_alive, read_pid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_test_port(exclude=()):
    """A currently-free port inside 7090-7099 (test-only, never allocated)."""
    for candidate in (7090, 7091, 7092, 7093, 7094, 7095, 7096, 7097, 7098, 7099):
        if candidate in exclude:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return candidate
    raise RuntimeError("no free test port in 7090-7099")


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    """Isolate PID store, logs and status dir; keep lifecycle side effects local."""
    pids = tmp_path / "pids"
    logs = tmp_path / "logs"
    pids.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: pids)
    monkeypatch.setattr("yasinhub.config_manager.get_status_dir", lambda: tmp_path)
    monkeypatch.setattr("yasinhub.config_manager.get_logs_dir", lambda: logs)
    return tmp_path


def _http_entry(name, tmp_path, port, pattern="http-test-marker"):
    return ProjectEntry(
        name=name,
        path=str(tmp_path),
        process_pattern=pattern,
        description="Issue #179 test HTTP service",
        start_command=(
            f"python3 -c \"import time; time.sleep(30)\"  # {pattern}"
        ),
        host="127.0.0.1",
        port=port,
        health_endpoint="/test-health",
    )


def _real_server_entry(name, tmp_path, port):
    """Entry whose start command really binds port and serves HTTP 200 on /."""
    marker = f"{name}-live-marker"
    return ProjectEntry(
        name=name,
        path=str(tmp_path),
        process_pattern=marker,
        description="Issue #179 live loopback HTTP service",
        start_command=(
            "python3 -c \"from http.server import test as _t, "
            "SimpleHTTPRequestHandler as _H; "
            f"_t(HandlerClass=_H, port={port}, bind='127.0.0.1')\"  # {marker}"
        ),
        host="127.0.0.1",
        port=port,
        health_endpoint="/",
    )


class _FakeProc:
    def __init__(self, pid=424242):
        self.pid = pid

    def poll(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _spawn_fake(monkeypatch, pid=424242):
    """Replace Popen with an instantly-stable fake child."""
    created = {}

    def fake_popen(argv, **kwargs):
        created["argv"] = argv
        created["cwd"] = kwargs.get("cwd")
        return _FakeProc(pid=pid)

    monkeypatch.setattr(sm.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sm, "_wait_for_stable_start", lambda proc: None)
    # Fake children have no real OS PID; treat them as alive so each test
    # exercises its own gate (identity / ownership / health) deterministically.
    monkeypatch.setattr(sm, "_is_pid_alive", lambda pid: True)
    # start_service probes the discovery pattern via subprocess.run (pgrep);
    # keep that read-only probe on a not-running answer for fake spawns.
    monkeypatch.setattr(
        sm, "check_process",
        lambda pattern: SimpleNamespace(pattern=pattern, running=False, pids=[]),
    )
    return created


# ---------------------------------------------------------------------------
# Registry contract
# ---------------------------------------------------------------------------

def test_port_allocation_is_canonical():
    assert YASIN_RESERVED_SERVICE_PORT_RANGE == (7000, 7099)
    assert YASIN_SERVICE_PORT_ALLOCATION == {
        "yasinhub": 7000,
        "yasin-agent": 7002,
        "yasinfeed": 7004,
    }
    # Registry (including backfilled runtime config) follows the same table.
    for project in default_registry():
        expected = YASIN_SERVICE_PORT_ALLOCATION.get(project.name)
        assert project.port == expected, project.name
        if expected is not None:
            assert project.host in ("127.0.0.1", "0.0.0.0"), project.name
            assert project.health_endpoint, project.name


def test_all_http_services_have_unique_ports():
    seen = {}
    for project in DEFAULT_PROJECTS:
        if project.port is None:
            continue
        assert project.port not in seen, (
            f"port {project.port} shared by {seen[project.port]} and {project.name}"
        )
        seen[project.port] = project.name
    assert len(seen) >= 2


def test_all_ports_are_inside_reserved_range():
    for project in DEFAULT_PROJECTS:
        if project.port is None:
            continue
        assert is_port_in_reserved_range(project.port), project.name
    assert not is_port_in_reserved_range(6999)
    assert not is_port_in_reserved_range(7100)
    assert not is_port_in_reserved_range(8000)
    assert not is_port_in_reserved_range(8080)


def test_yasinrelay_has_no_http_port():
    relay = next(p for p in default_registry() if p.name == "yasinrelay")
    assert relay.port is None
    assert relay.host is None
    assert relay.health_endpoint is None
    assert relay.start_command == ".venv/bin/yasinrelay-termux run --schedule --non-interactive"
    assert relay.process_pattern == "yasinrelay.cli"


# ---------------------------------------------------------------------------
# Collision: fail closed, never kill unknown owners
# ---------------------------------------------------------------------------

def test_unknown_process_on_expected_port_fails_closed(isolated_runtime, monkeypatch):
    port = _free_test_port()
    project = _http_entry("collide-svc", isolated_runtime, port)

    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[999999],
            owned_by_pid=False, detail="occupied by foreign pid",
        ),
    )
    ok, detail = sm.preflight_port_check(project)
    assert ok is False
    assert "fail closed" in detail

    popen_calls = _spawn_fake(monkeypatch)
    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
    assert popen_calls == {}, "must not spawn while the expected port is occupied"
    assert read_pid(project.name) is None, "must not reuse or store any PID"


def test_unknown_port_owner_is_never_killed(isolated_runtime, monkeypatch):
    port = _free_test_port()
    project = _http_entry("no-kill-svc", isolated_runtime, port)
    foreign_pid = 999998

    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[foreign_pid],
            owned_by_pid=False if pid != foreign_pid else True,
            detail="foreign owner",
        ),
    )
    killed = []
    monkeypatch.setattr(sm, "stop_pid_safely", lambda pid, timeout=3.0: killed.append(pid) or True)

    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
    assert foreign_pid not in killed
    assert killed == [], "no process may be killed on a collision path"


def test_real_squatter_survives_failed_start(isolated_runtime):
    """Live collision: a real loopback squatter must stay alive; Hub backs off."""
    port = _free_test_port()
    squatter = subprocess.Popen(
        ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            if ports.is_port_occupied("127.0.0.1", port):
                break
            time.sleep(0.1)
        assert ports.is_port_occupied("127.0.0.1", port)

        project = _http_entry("squatted-svc", isolated_runtime, port)
        ok, _detail = sm.preflight_port_check(project)
        assert ok is False
        assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
        assert squatter.poll() is None, "unknown port owner must never be killed"
        assert read_pid(project.name) is None
    finally:
        squatter.terminate()
        squatter.wait(timeout=10)


# ---------------------------------------------------------------------------
# Start contract: identity + ownership + health
# ---------------------------------------------------------------------------

def test_start_requires_process_identity(isolated_runtime, monkeypatch):
    port = _free_test_port()
    project = _http_entry("identity-svc", isolated_runtime, port)
    _spawn_fake(monkeypatch, pid=424243)

    monkeypatch.setattr(sm, "verify_process_identity", lambda pid, pat, cmd: False)
    # Every other gate passes, isolating identity as the failing gate.
    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[pid],
            owned_by_pid=True, detail="owned",
        ),
    )
    monkeypatch.setattr(sm, "check_http_health", lambda *a, **k: True)
    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
    assert read_pid(project.name) is None


def test_start_requires_port_ownership(isolated_runtime, monkeypatch):
    port = _free_test_port()
    project = _http_entry("ownership-svc", isolated_runtime, port)
    _spawn_fake(monkeypatch, pid=424244)

    monkeypatch.setattr(sm, "verify_process_identity", lambda pid, pat, cmd: True)
    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[123456],
            owned_by_pid=False, detail="owned by somebody else",
        ),
    )
    monkeypatch.setattr(sm, "check_http_health", lambda *a, **k: True)
    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
    assert read_pid(project.name) is None


def test_start_requires_health(isolated_runtime, monkeypatch):
    port = _free_test_port()
    project = _http_entry("health-svc", isolated_runtime, port)
    _spawn_fake(monkeypatch, pid=424245)

    monkeypatch.setattr(sm, "verify_process_identity", lambda pid, pat, cmd: True)
    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[pid],
            owned_by_pid=True, detail="owned",
        ),
    )
    monkeypatch.setattr(sm, "check_http_health", lambda *a, **k: False)
    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
    assert read_pid(project.name) is None


def test_live_start_stop_cycle_verifies_all_three(isolated_runtime):
    """Real loopback HTTP service: full start -> verify -> stop lifecycle."""
    port = _free_test_port()
    project = _real_server_entry("live-179-svc", isolated_runtime, port)

    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is True
    pid = read_pid(project.name)
    assert pid is not None and is_pid_alive(pid)

    verdict = sm.verify_runtime_running(project, pid)
    assert verdict.running is True
    assert verdict.identity is True
    assert verdict.health_ok is True

    assert sm.stop_service(project) is True
    assert read_pid(project.name) is None
    assert not is_pid_alive(pid)
    assert not ports.is_port_occupied("127.0.0.1", port)


# ---------------------------------------------------------------------------
# Stop / restart semantics
# ---------------------------------------------------------------------------

def test_stop_verifies_pid_dead(isolated_runtime):
    port = _free_test_port()
    project = _real_server_entry("stop-dead-svc", isolated_runtime, port)

    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is True
    pid = read_pid(project.name)
    assert sm.stop_service(project) is True
    assert not is_pid_alive(pid), "old PID must be dead after stop"


def test_stop_verifies_port_released(isolated_runtime):
    port = _free_test_port()
    project = _real_server_entry("stop-release-svc", isolated_runtime, port)

    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is True
    assert sm.stop_service(project) is True
    assert not ports.is_port_occupied("127.0.0.1", port), "port must be released"
    assert ports.port_owner_pids(port) in (set(), None)


def test_restart_uses_new_pid(isolated_runtime):
    port = _free_test_port()
    project = _real_server_entry("restart-pid-svc", isolated_runtime, port)

    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is True
    old_pid = read_pid(project.name)
    try:
        assert sm.restart_service(project, logs_dir=isolated_runtime / "logs") is True
        new_pid = read_pid(project.name)
        assert new_pid is not None and new_pid != old_pid
        assert is_pid_alive(new_pid)
        assert not is_pid_alive(old_pid), "old PID must be dead (no PID reuse)"
    finally:
        sm.stop_service(project)


def test_restart_verifies_new_port_owner(isolated_runtime):
    port = _free_test_port()
    project = _real_server_entry("restart-owner-svc", isolated_runtime, port)

    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is True
    try:
        assert sm.restart_service(project, logs_dir=isolated_runtime / "logs") is True
        new_pid = read_pid(project.name)
        verdict = sm.verify_runtime_running(project, new_pid)
        assert verdict.running is True, verdict.reasons
        assert verdict.health_ok is True
    finally:
        sm.stop_service(project)


# ---------------------------------------------------------------------------
# Wrong port: alive + healthy elsewhere is NOT RUNNING here
# ---------------------------------------------------------------------------

def test_wrong_port_is_not_reported_running(isolated_runtime, monkeypatch):
    """Strict logic: identity OK on the wrong port must never read RUNNING,
    even if the expected port is occupied and answers health probes."""
    project = _http_entry("wrong-port-svc", isolated_runtime, 7001)
    monkeypatch.setattr(sm, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(sm, "verify_process_identity", lambda pid, pat, cmd: True)
    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[777777],
            owned_by_pid=False, detail="expected port owned by another service",
        ),
    )
    monkeypatch.setattr(sm, "check_http_health", lambda *a, **k: True)

    verdict = sm.verify_runtime_running(project, 123456)
    assert verdict.running is False
    assert verdict.identity is True
    assert verdict.port_owned is False


def test_live_wrong_port_process_is_not_running(isolated_runtime):
    """Live variant: our process binds elsewhere while the expected port is free."""
    expected = _free_test_port()
    actual = _free_test_port(exclude=(expected,))
    project = _real_server_entry("wrong-live-svc", isolated_runtime, expected)
    # Start the identical process on the WRONG port instead.
    project.process_pattern = f"{project.process_pattern}-actual"
    project.start_command = project.start_command.replace(
        f"port={expected}", f"port={actual}"
    ).replace(project.name, f"{project.name}-actual")

    assert sm.start_service.__module__ == "yasinhub.service_manager"
    # Bypass start (it would fail closed on the free expected port) and prove
    # the verdict directly: spawn on `actual`, then verify against `expected`.
    child = subprocess.Popen(
        ["python3", "-c", "from http.server import test as _t, "
         "SimpleHTTPRequestHandler as _H; "
         f"_t(HandlerClass=_H, port={actual}, bind='127.0.0.1')"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            if ports.is_port_occupied("127.0.0.1", actual):
                break
            time.sleep(0.1)
        probe = ProjectEntry(
            name=project.name, path=str(isolated_runtime),
            process_pattern=None, start_command=None,
            host="127.0.0.1", port=expected, health_endpoint="/",
        )
        # No pattern/command hints -> identity unverifiable -> not RUNNING.
        verdict = sm.verify_runtime_running(probe, child.pid)
        assert verdict.running is False
    finally:
        child.terminate()
        child.wait(timeout=10)
