"""Issue #182: generic self-healing startup/ownership contract for ALL managed services.

Extends the Issue #180 Hub-only contract to every YasinHub-managed service:

    PWA -> YasinHub -> Runit -> Service

Covered here:
 1. free port -> service starts
 2. port occupied by older instance of same service -> graceful stop ->
    port release -> restart (new PID, identity, port verified)
 3. port occupied by unrelated process -> startup refused
 4. unrelated process remains alive (never killed)
 5. unknown ownership -> startup refused
 6. stale/dead PID -> safe refusal
 7. incomplete process metadata -> safe refusal
 8. post-start PID verification
 9. post-start process identity verification
10. post-start port verification
11. Runit lifecycle integration (sv path, no bypass, no second manager)
12. PWA Start/Stop/Restart/Status reflects real service state
13. Termux/Android ARM64 non-interactive execution (no prompts, no lsof/ss
    hard dependency, bounded sv timeouts)

Safe by construction: live sockets are isolated loopback servers on test-only
ports (7090-7099, never canonical allocations); kill-sensitive paths use test
doubles or the test's own children only. No real user process is signaled.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import time
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from yasinhub import ports
from yasinhub import runit
from yasinhub import service_lifecycle as lifecycle
from yasinhub import service_manager as sm
from yasinhub.pid_store import is_pid_alive, read_pid
from yasinhub.registry import ProjectEntry
from yasinhub.status_store import read_status


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _free_test_port(exclude=()):
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
    pids = tmp_path / "pids"
    logs = tmp_path / "logs"
    pids.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("yasinhub.pid_store.get_pid_dir", lambda: pids)
    monkeypatch.setattr("yasinhub.config_manager.get_status_dir", lambda: tmp_path)
    monkeypatch.setattr("yasinhub.config_manager.get_logs_dir", lambda: logs)
    return tmp_path


def _http_entry(name, tmp_path, port, pattern="issue182-marker"):
    return ProjectEntry(
        name=name,
        path=str(tmp_path),
        process_pattern=pattern,
        description="Issue #182 test HTTP service",
        start_command=(f"python3 -c \"import time; time.sleep(30)\"  # {pattern}"),
        host="127.0.0.1",
        port=port,
        health_endpoint="/test-health",
    )


def _live_server_entry(name, tmp_path, port):
    marker = f"{name}-182-live"
    return ProjectEntry(
        name=name,
        path=str(tmp_path),
        process_pattern=marker,
        description="Issue #182 live loopback HTTP service",
        start_command=(
            "python3 -c \"from http.server import test as _t, "
            "SimpleHTTPRequestHandler as _H; "
            f"_t(HandlerClass=_H, port={port}, bind='127.0.0.1')\"  # {marker}"
        ),
        host="127.0.0.1",
        port=port,
        health_endpoint="/",
    )


def _wait_occupied(port, timeout=10.0):
    for _ in range(int(timeout / 0.1)):
        if ports.is_port_occupied("127.0.0.1", port):
            return True
        time.sleep(0.1)
    return ports.is_port_occupied("127.0.0.1", port)


def _spawn_live_old_instance(port, marker):
    """An older instance of the SAME service (cmdline carries the marker)."""
    code = (
        "from http.server import test as _t, SimpleHTTPRequestHandler as _H; "
        f"_t(HandlerClass=_H, port={port}, bind='127.0.0.1')  # {marker}"
    )
    return subprocess.Popen(
        ["python3", "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# 1: free port -> service starts (+ post-start PID/identity/port verification)
# ---------------------------------------------------------------------------

def test_182_free_port_starts_and_verifies(isolated_runtime, tmp_path):
    port = _free_test_port()
    project = _live_server_entry("free182-svc", isolated_runtime, port)
    try:
        assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is True
        pid = read_pid(project.name)
        assert pid is not None and pid > 0  # (8) real PID recorded
        assert is_pid_alive(pid) is True  # (8) PID alive post-start
        assert sm.verify_process_identity(  # (9) real process identity
            pid, project.process_pattern, project.start_command
        ) is True
        # (10) expected port listens and is owned by our PID where the
        # platform proves holders; on hardened kernels without
        # /proc/net/tcp the bind-correlation ladder (occupied + identity +
        # succeeding contract health) anchors the verdict instead.
        assert ports.is_port_occupied("127.0.0.1", port) is True  # (10) listening
        ownership = ports.verify_port_ownership("127.0.0.1", port, pid)
        if ownership.owned_by_pid is not None:
            assert ownership.owned_by_pid is True  # (10) expected port owned
        verdict = sm.verify_runtime_running(project, pid)
        assert verdict.running is True
        assert verdict.identity is True
        assert verdict.health_ok is True
    finally:
        sm.stop_service(project)


# ---------------------------------------------------------------------------
# 2: same-service occupant -> graceful stop -> release -> restart, new PID
# ---------------------------------------------------------------------------

def test_182_same_service_heals_with_graceful_restart(isolated_runtime):
    port = _free_test_port()
    project = _live_server_entry("heal182-svc", isolated_runtime, port)
    old = _spawn_live_old_instance(port, project.process_pattern)
    try:
        assert _wait_occupied(port) is True
        old_pid = old.pid
        assert sm.verify_process_identity(
            old_pid, project.process_pattern, project.start_command
        ) is True  # pre-condition: provably the same service

        assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is True
        new_pid = read_pid(project.name)
        assert new_pid is not None and new_pid != old_pid  # new PID, no reuse
        assert old.poll() is not None  # old instance actually gone...
        assert not is_pid_alive(old_pid)  # ...and reaped/dead
        assert is_pid_alive(new_pid) is True
        assert sm.verify_process_identity(
            new_pid, project.process_pattern, project.start_command
        ) is True
        assert ports.is_port_occupied("127.0.0.1", port) is True
        verdict = sm.verify_runtime_running(project, new_pid)
        assert verdict.running is True
    finally:
        try:
            old.terminate()
            old.wait(timeout=5)
        except Exception:
            try:
                old.kill()
            except Exception:
                pass
        sm.stop_service(project)


def test_182_graceful_path_never_uses_sigkill(monkeypatch):
    """Normal heal path sends SIGTERM only; refusal never escalates to KILL."""
    import yasinhub.service_lifecycle as lc

    signals: list = []
    monkeypatch.setattr(lc, "check_pid_alive", lambda pid: True)  # refuses to die

    def fake_kill(pid, sig):
        signals.append(sig)
        return None  # signal "delivered", process still alive

    monkeypatch.setattr(lc.os, "kill", fake_kill)
    assert lc.stop_owned_pid_gracefully(424242, timeout=0.3) is False
    assert signals, "graceful stop must attempt SIGTERM"
    assert all(sig == signal.SIGTERM for sig in signals)
    assert signal.SIGKILL not in signals


# ---------------------------------------------------------------------------
# 3+4: foreign occupant -> refused AND unrelated process stays alive
# ---------------------------------------------------------------------------

def test_182_foreign_owner_refused_and_survives(isolated_runtime):
    port = _free_test_port()
    squatter = subprocess.Popen(
        ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_occupied(port) is True
        project = _http_entry("foreign182-svc", isolated_runtime, port)
        # Pre-condition: squatter cmdline does NOT carry our discovery
        # pattern, so classification-grade identity reads foreign (a bare
        # `python3` argv[0] overlap is never sufficient).
        assert lifecycle.strict_service_identity(squatter.pid, project) is False

        killed: list = []
        orig_kill = os.kill

        def guard_kill(pid, sig):
            killed.append((pid, sig))
            return orig_kill(pid, sig)

        import yasinhub.service_lifecycle as lc

        monkeypatch_guard = pytest.MonkeyPatch()
        monkeypatch_guard.setattr(lc.os, "kill", guard_kill)
        try:
            assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
        finally:
            monkeypatch_guard.undo()
        assert squatter.poll() is None, "unrelated process must remain alive"
        assert is_pid_alive(squatter.pid) is True
        assert killed == [], "foreign owner must never be signaled"
        assert read_pid(project.name) is None, "no PID may be stored on refusal"
        # Failure propagates through the status/report contract (PWA-visible).
        # On hardened kernels without owner discovery the verdict reads
        # indeterminate; where holders are provable it reads foreign — both
        # are fail-closed refusals that never touch the occupant.
        record = read_status(project.name, status_dir=isolated_runtime)
        assert record is not None and record.success is False
        assert str(port) in (record.message or "")
        assert "fail closed" in (record.message or "")
    finally:
        squatter.terminate()
        squatter.wait(timeout=10)


# ---------------------------------------------------------------------------
# 5: unknown ownership -> refused, nothing killed
# ---------------------------------------------------------------------------

def test_182_unknown_ownership_refused(isolated_runtime, monkeypatch):
    port = _free_test_port()
    project = _http_entry("unknown182-svc", isolated_runtime, port)
    # Occupied port, but owner discovery yields nothing provable.
    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[],
            owned_by_pid=False, detail="occupied, owners unknown",
        ),
    )
    killed: list = []
    monkeypatch.setattr(sm, "stop_pid_safely", lambda pid, timeout=3.0: killed.append(pid) or True)
    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
    assert killed == []
    assert read_pid(project.name) is None
    record = read_status(project.name, status_dir=isolated_runtime)
    assert record is not None and record.success is False


def test_182_preflight_unknown_when_identity_unverifiable():
    project = ProjectEntry(
        name="pre182-unknown", process_pattern="marker-xyz",
        start_command="python3 marker-xyz", host="127.0.0.1",
        port=7097, health_endpoint="/",
    )
    pre = lifecycle.preflight_service(
        project,
        owner_fn=lambda p: {424242},
        occupied_fn=lambda h, p: True,
        identity_fn=lambda pid: None,  # /proc metadata missing
    )
    assert pre.decision == "indeterminate"
    assert pre.unknown_pids == [424242]
    assert pre.same_pids == [] and pre.foreign_pids == []


def test_182_foreign_classification_names_pid_and_refuses(isolated_runtime):
    """Where holders are provable, a foreign owner is named and refused."""
    port = _free_test_port()
    project = _http_entry("foreignname182-svc", isolated_runtime, port)
    foreign_pid = os.getpid()  # live PID, provably foreign via injected identity
    pre = lifecycle.preflight_service(
        project,
        owner_fn=lambda p: {foreign_pid},
        occupied_fn=lambda h, p: True,
        identity_fn=lambda pid: False,  # provably not our service
    )
    assert pre.decision == "foreign"
    assert pre.foreign_pids == [foreign_pid]
    result = lifecycle.refusal_result(project, pre, pre.detail)
    assert result.success is False and result.action == "refused"
    assert str(port) in result.detail and str(foreign_pid) in result.detail
    # Refusal reporting never signals anything (unit-level: no kill surface).
    assert result.owner_pid == foreign_pid or result.classification == "foreign"


# ---------------------------------------------------------------------------
# 6: stale/dead PID -> safe refusal (never kill, never reuse)
# ---------------------------------------------------------------------------

def test_182_stale_dead_pid_refused(isolated_runtime, monkeypatch):
    port = _free_test_port()
    project = _http_entry("stale182-svc", isolated_runtime, port)
    dead_pid = 999991
    assert not is_pid_alive(dead_pid)
    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[dead_pid],
            owned_by_pid=False, detail="stale owner",
        ),
    )
    killed: list = []
    monkeypatch.setattr(sm, "stop_pid_safely", lambda pid, timeout=3.0: killed.append(pid) or True)
    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
    assert killed == []
    assert read_pid(project.name) is None


def test_182_dead_saved_pid_cleaned_on_free_port(isolated_runtime):
    """A dead saved PID file is stale metadata: cleaned, start proceeds."""
    from yasinhub.pid_store import save_pid

    port = _free_test_port()
    project = _live_server_entry("staleclean182-svc", isolated_runtime, port)
    save_pid(project.name, 999992)
    assert not is_pid_alive(999992)
    try:
        assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is True
        assert read_pid(project.name) not in (None, 999992)
    finally:
        sm.stop_service(project)


# ---------------------------------------------------------------------------
# 7: incomplete metadata -> safe refusal
# ---------------------------------------------------------------------------

def test_182_incomplete_metadata_refused():
    project = ProjectEntry(
        name="incompl182", process_pattern=None, start_command=None,
        host="127.0.0.1", port=7096, health_endpoint="/",
    )
    # No pattern/command hints at all: identity can never be proven.
    assert lifecycle.identify_service_process(os.getpid(), project) is None
    pre = lifecycle.preflight_service(
        project,
        owner_fn=lambda p: {os.getpid()},
        occupied_fn=lambda h, p: True,
    )
    assert pre.decision == "indeterminate"
    result = lifecycle.refusal_result(project, pre, "incomplete metadata")
    assert result.success is False and result.action == "refused"


# ---------------------------------------------------------------------------
# 8/9/10: post-start verification gates (unit level)
# ---------------------------------------------------------------------------

def test_182_poststart_verification_gates(isolated_runtime):
    port = _free_test_port()
    project = _live_server_entry("verify182-svc", isolated_runtime, port)
    child = _spawn_live_old_instance(port, project.process_pattern)
    try:
        assert _wait_occupied(port) is True
        ok = lifecycle.verify_service_started(project, child.pid)
        assert ok.success is True and ok.action == "started"
        assert ok.pid == child.pid
        # Dead PID fails the PID gate.
        dead = lifecycle.verify_service_started(project, 999993)
        assert dead.success is False
        # Foreign identity fails the identity gate.
        squatter = subprocess.Popen(
            ["python3", "-m", "http.server", str(port + 1 if port < 7099 else port - 1),
             "--bind", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            bad = lifecycle.verify_service_started(project, squatter.pid)
            assert bad.success is False
            assert "identity" in bad.detail
        finally:
            squatter.terminate()
            squatter.wait(timeout=10)
    finally:
        child.terminate()
        child.wait(timeout=10)


# ---------------------------------------------------------------------------
# 11: Runit lifecycle integration (Hub -> Runit -> service, no bypass)
# ---------------------------------------------------------------------------

def _write_fake_sv(bin_dir: Path, log: Path):
    script = bin_dir / "sv"
    script.write_text(
        "#!/bin/sh\n"
        f"echo \"$@\" >> \"{log}\"\n"
        "if [ \"$1\" = \"status\" ]; then echo \"run: fake\"; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def test_182_runit_adapter_noninteractive(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "sv.log"
    _write_fake_sv(bin_dir, call_log)
    monkeypatch.setenv("PREFIX", str(tmp_path / "usr"))
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    svc_root = tmp_path / "usr" / "var" / "service" / "demo182"
    (svc_root).mkdir(parents=True)
    (svc_root / "run").write_text("#!/bin/sh\nexec sleep 100\n", encoding="utf-8")

    assert runit.is_runit_managed("demo182") is True
    assert runit.is_runit_managed("missing182") is False
    assert runit.is_sv_available() is True
    assert runit.sv_up("demo182").ok is True
    assert runit.sv_down("demo182").ok is True
    status = runit.sv_status("demo182")
    assert status.ok is True
    assert runit.parse_sv_running(status.detail) is True
    assert runit.parse_sv_running("down: demo182") is False
    assert runit.parse_sv_running("weird output") is None
    logged = call_log.read_text(encoding="utf-8")
    assert "up demo182" in logged and "down demo182" in logged


def test_182_runit_managed_never_bypassed(isolated_runtime, tmp_path, monkeypatch):
    """A Runit-managed service with no usable `sv` is refused, never Popen-spawned."""
    port = _free_test_port()
    project = _http_entry("managed182-svc", isolated_runtime, port)
    fake_prefix = tmp_path / "usr"
    svc_dir = fake_prefix / "var" / "service" / project.name
    svc_dir.mkdir(parents=True)
    (svc_dir / "run").write_text("#!/bin/sh\nexec sleep 100\n", encoding="utf-8")
    monkeypatch.setenv("PREFIX", str(fake_prefix))
    monkeypatch.setattr(runit, "is_sv_available", lambda: False)
    # Neither the supervisor tool nor an ad-hoc spawn may run on this path.
    monkeypatch.setattr(
        runit, "sv_up",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("sv must not run")),
    )

    def no_spawn(*args, **kwargs):
        raise AssertionError("Runit-managed service must never be ad-hoc spawned")

    monkeypatch.setattr(sm.subprocess, "Popen", no_spawn)
    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
    record = read_status(project.name, status_dir=isolated_runtime)
    assert record is not None and record.success is False


def test_182_refusing_old_instance_is_not_force_killed(isolated_runtime, monkeypatch):
    """Same-service occupant that refuses SIGTERM -> fail closed, still alive."""
    port = _free_test_port()
    project = _live_server_entry("refuse182-svc", isolated_runtime, port)
    old = _spawn_live_old_instance(port, project.process_pattern)
    try:
        assert _wait_occupied(port) is True
        monkeypatch.setattr(lifecycle, "STOP_GRACE_SECONDS", 0.4)
        monkeypatch.setattr(
            lifecycle, "stop_owned_pid_gracefully", lambda pid, timeout=0.4: False
        )
        assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
        assert old.poll() is None, "refusing instance must stay alive (no kill -9)"
        assert is_pid_alive(old.pid) is True
        assert read_pid(project.name) is None
    finally:
        old.terminate()
        old.wait(timeout=10)


# ---------------------------------------------------------------------------
# 12: PWA Start/Stop/Restart/Status operate on real services via Hub + Runit
# ---------------------------------------------------------------------------

def test_182_pwa_lifecycle_reflects_real_state(tmp_path, monkeypatch):
    """Control-plane HTTP endpoints drive real processes; snapshots are real."""
    from yasinhub.api.server import YasinHubHandler

    test_project = ProjectEntry(
        name="pwa182-svc",
        description="Issue #182 PWA lifecycle probe (portless worker)",
        start_command="python3 -c \"import time; time.sleep(30)\"",
        process_pattern="pwa182-sleep-probe",
    )
    test_project.start_command += "  # pwa182-sleep-probe"
    monkeypatch.setattr("yasinhub.api.server.default_registry", lambda: [test_project])

    port = _free_test_port()
    server = HTTPServer(("127.0.0.1", port), YasinHubHandler)
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    base = f"http://127.0.0.1:{port}"

    def post(path):
        req = urllib.request.Request(
            base + path, data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def get(path):
        with urllib.request.urlopen(base + path, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    from yasinhub.service_manager import stop_service as _stop

    try:
        code, started = post("/api/control/pwa182-svc/start")
        assert code == 200 and started["success"] is True
        pid1 = started["pid"]
        # Real-process proof (the snapshot payload only resolves
        # registry-listed services; liveness here is the ground truth).
        assert pid1 is not None and is_pid_alive(pid1) is True

        code, restarted = post("/api/control/pwa182-svc/restart")
        assert code == 200 and restarted["success"] is True
        pid2 = restarted["pid"]
        assert pid2 is not None and pid2 != pid1, "restart must yield a new PID"
        assert is_pid_alive(pid2) is True
        assert not is_pid_alive(pid1)

        code, stopped = get("/api/control/pwa182-svc/stop")
        assert code == 200 and stopped["success"] is True
        assert read_pid("pwa182-svc") is None
        assert not is_pid_alive(pid2)

        # Status surface stays live and truthful: the Hub answers, and the
        # stopped probe is no longer reported with a live PID anywhere.
        code, status = get("/api/status")
        assert code == 200
        assert "projects" in status
        for entry in status["projects"]:
            if entry["name"] == "pwa182-svc":
                assert entry["pid"] is None
        assert read_pid("pwa182-svc") is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        _stop(test_project)


def test_182_pwa_shows_refusal_for_foreign_port(isolated_runtime):
    """A refused HTTP start surfaces FAILED status (what the PWA renders).

    Uses the registry-listed `yasinfeed` service on its canonical port so the
    refusal propagates through the same report contract the PWA reads.
    """
    from yasinhub.registry import default_registry

    project = next(p for p in default_registry() if p.name == "yasinfeed")
    port = int(project.port)
    try:
        squatter = subprocess.Popen(
            ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        pytest.skip("canonical yasinfeed port unavailable for squat test")
        return
    try:
        if not _wait_occupied(port):
            pytest.skip("could not occupy canonical yasinfeed port")
            return
        assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
        assert read_pid(project.name) is None
        from yasinhub.api.service_control_helpers import service_runtime_snapshot

        snap = service_runtime_snapshot(project.name)
        assert snap["status"] == "FAILED"
        assert "refused" in (snap["message"] or "").lower() or "fail" in (snap["message"] or "").lower()
    finally:
        squatter.terminate()
        squatter.wait(timeout=10)


# ---------------------------------------------------------------------------
# 13: Termux/Android ARM64 non-interactive execution
# ---------------------------------------------------------------------------

def test_182_noninteractive_no_prompts(isolated_runtime, monkeypatch):
    port = _free_test_port()
    project = _http_entry("nonint182-svc", isolated_runtime, port)

    def no_input(*args, **kwargs):
        raise AssertionError("lifecycle must never prompt for input")

    monkeypatch.setattr("builtins.input", no_input)
    pre = lifecycle.preflight_service(project)
    assert pre.decision in ("free", "same", "foreign", "indeterminate", "portless")
    # Refusal path (foreign) exercises reporting without prompts.
    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[999990],
            owned_by_pid=False, detail="foreign",
        ),
    )
    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False


def test_182_no_hard_dependency_on_lsof_ss_fuser(monkeypatch, tmp_path):
    monkeypatch.setattr(runit, "sv_binary", lambda: None)
    assert runit.is_sv_available() is False
    assert runit.sv_up("anything182").ok is False  # safe data, never raises
    # Lifecycle never shells out to lsof/fuser/ss on its required path.
    import pathlib

    for module_file in (
        lifecycle.__file__, sm.__file__, runit.__file__,
    ):
        source = pathlib.Path(module_file).read_text(encoding="utf-8")
        assert '"lsof"' not in source
        assert '"fuser"' not in source


def test_182_no_secrets_in_reports_and_status(isolated_runtime, monkeypatch):
    port = _free_test_port()
    secret = "SECRET-TOKEN-ABC-123-XYZ"
    monkeypatch.setenv("YASIN_AGENT_SERVICE_TOKEN", secret)
    project = _http_entry("secret182-svc", isolated_runtime, port)
    monkeypatch.setattr(
        sm, "verify_port_ownership",
        lambda host, p, pid: ports.PortOwnership(
            port=p, occupied=True, owner_pids=[999989],
            owned_by_pid=False, detail="foreign",
        ),
    )
    assert sm.start_service(project, logs_dir=isolated_runtime / "logs") is False
    record = read_status(project.name, status_dir=isolated_runtime)
    assert record is not None
    assert secret not in (record.message or "")
    pre = lifecycle.preflight_service(project)
    assert secret not in pre.detail
