"""
tests/test_termux_control_plane_contract.py

Comprehensive test suite verifying Issue #163:
Termux-first Android ARM64 Control Plane contract & real lifecycle guarantees:
1. Start/Stop/Restart real OS processes and verify PID changes/liveness.
2. Ensure noninteractive service commands (yasinrelay, yasin-ai, yasin-agent).
3. Ensure yasin-agent is not duplicated when running.
4. Verify Hub server termination causes API requests to fail.
5. Verify Hub server restart recovers API health.
6. Verify /api/control/<service>/<action> HTTP control endpoints.
"""

import time
import socket
import urllib.request
import urllib.error
import json
from pathlib import Path
from http.server import HTTPServer
import threading

from yasinhub.registry import ProjectEntry, default_registry
from yasinhub.service_manager import start_service, stop_service, restart_service
from yasinhub.pid_store import read_pid, is_pid_alive
from yasinhub.api.server import YasinHubHandler


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def test_real_process_lifecycle_contract(tmp_path):
    """
    PRIMARY SERVICE LIFECYCLE REQUIREMENT:
    Start -> verify actual process/PID exists
    Stop -> verify PID disappears
    Start again -> verify PID
    Restart -> verify a new PID
    Status -> verify status reflects actual state
    """
    logs_dir = tmp_path / "logs"
    status_dir = tmp_path / "status"
    logs_dir.mkdir(parents=True, exist_ok=True)
    status_dir.mkdir(parents=True, exist_ok=True)

    test_project = ProjectEntry(
        name="test_dummy_service",
        description="Dummy background worker for lifecycle testing",
        start_command="python3 -c \"import time; time.sleep(30)\"",
        process_pattern="import time; time.sleep(30)"
    )

    try:
        # 1. START
        started = start_service(test_project, logs_dir=logs_dir)
        assert started is True, "Service start should return True"

        pid1 = read_pid(test_project.name)
        assert pid1 is not None, "PID file must be created on start"
        assert is_pid_alive(pid1) is True, "Actual process/PID must exist post-start"

        # 2. STOP
        stopped = stop_service(test_project)
        assert stopped is True, "Service stop should return True"

        assert read_pid(test_project.name) is None, "PID file must be removed on stop"
        assert is_pid_alive(pid1) is False, "Process PID must actually disappear after stop"

        # 3. START AGAIN
        started_again = start_service(test_project, logs_dir=logs_dir)
        assert started_again is True

        pid2 = read_pid(test_project.name)
        assert pid2 is not None
        assert is_pid_alive(pid2) is True
        assert pid2 != pid1, "New process start must yield a new PID"

        # 4. RESTART
        restarted = restart_service(test_project, logs_dir=logs_dir)
        assert restarted is True

        pid3 = read_pid(test_project.name)
        assert pid3 is not None
        assert is_pid_alive(pid3) is True
        assert pid3 != pid2, "Restart must create a new process with a new PID"
        assert is_pid_alive(pid2) is False, "Previous process must be dead"

    finally:
        # Cleanup
        stop_service(test_project)


def test_yasin_agent_runit_no_duplicate(tmp_path, monkeypatch):
    """
    Ensure yasin-agent does not get duplicated when already managed/running.
    """
    from yasinhub.process_checker import ProcessStatus

    agent_project = ProjectEntry(
        name="yasin-agent",
        path=str(tmp_path),
        process_pattern="agent_platform.server",
        description="Yasin-Agent HTTP runtime",
        start_command=".venv/bin/python -m agent_platform.server"
    )

    # Mock check_process to simulate agent already running under runit
    def mock_check_process(pattern):
        return ProcessStatus(pattern=pattern, running=True, pids=["99999"])

    monkeypatch.setattr("yasinhub.service_manager.check_process", mock_check_process)

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    result = start_service(agent_project, logs_dir=logs_dir)
    assert result is True, "Should observe already-running agent without spawning duplicate"
    assert read_pid("yasin-agent") == 99999


def test_canonical_noninteractive_service_commands():
    """
    Ensure managed service registry commands are noninteractive and canonical.
    - YasinRelay: python3 -m yasinrelay.cli run
    - Yasin-AI: yasin serve
    - Yasin-Agent: .venv/bin/python -m agent_platform.server
    """
    from yasinhub.registry import DEFAULT_PROJECTS
    projects = DEFAULT_PROJECTS

    relay = next((p for p in projects if p.name == "yasinrelay"), None)
    assert relay is not None
    assert relay.start_command == "python3 -m yasinrelay.cli run"

    ai = next((p for p in projects if p.name == "yasin-ai"), None)
    assert ai is not None
    assert ai.start_command == "yasin serve"

    agent = next((p for p in projects if p.name == "yasin-agent"), None)
    assert agent is not None
    assert "agent_platform.server" in agent.start_command


def test_hub_api_server_failure_and_recovery_lifecycle():
    """
    Verify that closing/killing the Hub process causes LIVE API requests to fail,
    and restarting Hub restores live API recovery.
    """
    port = get_free_port()
    server = HTTPServer(("127.0.0.1", port), YasinHubHandler)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.2)

    health_url = f"http://127.0.0.1:{port}/api/health"

    # 1. LIVE API HEALTHY
    req = urllib.request.urlopen(health_url, timeout=2)
    assert req.status == 200
    data = json.loads(req.read().decode("utf-8"))
    assert data["status"] == "ok"

    # 2. CLOSE / KILL HUB SERVER PROCESS
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=2)

    # 3. VERIFY LIVE API REQUESTS FAIL
    failed = False
    try:
        urllib.request.urlopen(health_url, timeout=1)
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        failed = True

    assert failed is True, "LIVE API requests must fail when Hub process is stopped"

    # 4. RESTART HUB SERVER
    server2 = HTTPServer(("127.0.0.1", port), YasinHubHandler)
    server_thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
    server_thread2.start()
    time.sleep(0.2)

    try:
        # 5. VERIFY API RECOVERY
        req2 = urllib.request.urlopen(health_url, timeout=2)
        assert req2.status == 200
        data2 = json.loads(req2.read().decode("utf-8"))
        assert data2["status"] == "ok"
    finally:
        server2.shutdown()
        server2.server_close()
        server_thread2.join(timeout=2)


def test_pwa_api_control_endpoint_execution(tmp_path, monkeypatch):
    """
    Verify /api/control/<service>/<action> endpoints execute real Control Plane commands.
    """
    test_project = ProjectEntry(
        name="test_pwa_svc",
        description="Test service for PWA API control",
        start_command="python3 -c \"import time; time.sleep(30)\"",
        process_pattern="import time; time.sleep(30)"
    )

    monkeypatch.setattr("yasinhub.api.server.default_registry", lambda: [test_project])

    port = get_free_port()
    server = HTTPServer(("127.0.0.1", port), YasinHubHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.2)

    base_url = f"http://127.0.0.1:{port}"

    try:
        # START via API
        req = urllib.request.Request(
            f"{base_url}/api/control/test_pwa_svc/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=3)
        res_data = json.loads(resp.read().decode("utf-8"))
        assert res_data["success"] is True
        assert res_data["action"] == "start"

        pid = read_pid("test_pwa_svc")
        assert pid is not None
        assert is_pid_alive(pid) is True

        # RESTART via API
        req = urllib.request.Request(
            f"{base_url}/api/control/test_pwa_svc/restart",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=3)
        res_data = json.loads(resp.read().decode("utf-8"))
        assert res_data["success"] is True

        new_pid = read_pid("test_pwa_svc")
        assert new_pid is not None
        assert new_pid != pid
        assert is_pid_alive(new_pid) is True

        # STOP via API
        req = urllib.request.Request(
            f"{base_url}/api/control/test_pwa_svc/stop",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=3)
        res_data = json.loads(resp.read().decode("utf-8"))
        assert res_data["success"] is True

        assert read_pid("test_pwa_svc") is None
        assert is_pid_alive(new_pid) is False

    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
        stop_service(test_project)
