"""Regression tests for Termux/runit Yasin-Agent production service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from yasinhub.registry import DEFAULT_PROJECTS, YASIN_ECOSYSTEM_ROOT, ProjectEntry
from yasinhub.service_manager import start_service

ROOT = Path(__file__).resolve().parents[1]
RUN_SCRIPT = ROOT / "scripts" / "termux" / "yasin-agent" / "run"
LOG_SCRIPT = ROOT / "scripts" / "termux" / "yasin-agent" / "log" / "run"
INSTALL_SCRIPT = ROOT / "scripts" / "termux" / "install_yasin_agent_service.sh"
DOC = ROOT / "docs" / "TERMUX_RUNIT_YASIN_AGENT.md"


def test_runit_service_scripts_exist() -> None:
    assert RUN_SCRIPT.is_file()
    assert LOG_SCRIPT.is_file()
    assert INSTALL_SCRIPT.is_file()
    assert DOC.is_file()
    assert RUN_SCRIPT.read_text(encoding="utf-8").startswith("#!")
    assert LOG_SCRIPT.read_text(encoding="utf-8").startswith("#!")
    assert INSTALL_SCRIPT.read_text(encoding="utf-8").startswith("#!")


def test_run_script_canonical_contract() -> None:
    text = RUN_SCRIPT.read_text(encoding="utf-8")
    assert "yasineco/Yasin-agent" in text
    assert "agent_platform.server" in text
    assert "yasin-agent.token" in text
    assert "exec" in text
    assert ".venv/bin/python" in text
    assert "Yasin-agent-main" not in text
    assert "yasin-ecosystem" not in text
    assert 'if [ -f "${TOKEN_FILE}" ]' in text or "if [ -f \"${TOKEN_FILE}\" ]" in text
    assert "already in use" in text or "YASIN_AGENT_PORT" in text
    assert 'echo "$YASIN_AGENT_SERVICE_TOKEN"' not in text
    assert "echo $YASIN_AGENT_SERVICE_TOKEN" not in text


def test_log_script_has_fallback() -> None:
    text = LOG_SCRIPT.read_text(encoding="utf-8")
    assert "multilog" in text or "svlogd" in text
    assert "LOG_DIR" in text or "logs/yasin-agent" in text


def test_install_script_contracts() -> None:
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "var/service" in text or "termux-services" in text
    assert "yasin-agent.token" in text
    assert "chmod 600" in text or "0o600" in text
    assert "sv up" in text
    assert "sv status" in text
    assert "Authorization: Bearer" in text
    assert "agent_platform.server" in text
    assert "pgrep" in text or "orphan" in text.lower() or "kill" in text


def test_docs_cover_architecture_and_verification() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "runit" in text.lower() or "termux-services" in text
    assert "agent_platform.server" in text
    assert "/v1/health" in text
    assert "/v1/ready" in text
    assert "401" in text
    assert "yasineco/Yasin-agent" in text
    assert (
        "duplicate" in text.lower()
        or "single-instance" in text.lower()
        or "idempotent" in text.lower()
    )
    assert "token" in text.lower()


def test_registry_yasin_agent_canonical_path() -> None:
    agent = next(p for p in DEFAULT_PROJECTS if p.name == "yasin-agent")
    assert agent.path is not None
    assert agent.path.endswith("Yasin-agent") or agent.path.endswith("Yasin-agent/")
    assert "Yasin-agent-main" not in (agent.path or "")
    assert "yasin-ecosystem" not in (agent.path or "")
    assert agent.process_pattern == "agent_platform.server"
    assert "agent_platform.server" in (agent.start_command or "")
    assert str(YASIN_ECOSYSTEM_ROOT) in (agent.path or "") or "yasineco" in (agent.path or "")


def test_start_service_idempotent_when_agent_already_running(tmp_path) -> None:
    project = ProjectEntry(
        name="yasin-agent",
        path=str(tmp_path),
        process_pattern="agent_platform.server",
        start_command=".venv/bin/python -m agent_platform.server",
    )
    with patch("yasinhub.service_manager.read_pid", return_value=None), patch(
        "yasinhub.service_manager.check_process"
    ) as check_process, patch("yasinhub.service_manager.subprocess.Popen") as popen, patch(
        "yasinhub.service_manager.save_pid"
    ):
        check_process.return_value.running = True
        check_process.return_value.pids = ["4242"]
        assert start_service(project, logs_dir=tmp_path / "logs") is True
        popen.assert_not_called()


def test_yasin_agent_token_file_wins() -> None:
    from yasinhub.agent_token import resolve_agent_service_token
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        path = home / ".yasinhub" / "yasin-agent.token"
        path.parent.mkdir(parents=True)
        path.write_text("canonical-from-file\n", encoding="utf-8")
        assert (
            resolve_agent_service_token(
                env={"YASIN_AGENT_SERVICE_TOKEN": "stale"},
                home=home,
                persist=False,
            )
            == "canonical-from-file"
        )
