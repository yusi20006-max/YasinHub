"""
tests/test_e2e_integration.py
End-to-End Integration Validation across the Yasin Ecosystem.
Validates workflow, service discovery, status aggregation, health reporting, compatibility, and error handling.
"""

import json
import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Import YasinHub integration modules
from yasinhub.agent_integration import AgentIntegration
from yasinhub.core_integration import CoreIntegration
from yasinhub.relay_integration import RelayIntegration
from yasinhub.config_manager import ConfigManager, ValidationError
from yasinhub.registry import ProjectEntry, load_config
from yasinhub.report import build_report, ProjectReport
from yasinhub.status_store import read_status, write_status, read_all_statuses
from yasinhub.cli import main as cli_main, format_report
from yasinhub.dashboard import (
    make_header,
    make_core_panel,
    make_agent_panel,
    make_relay_panel,
    make_services_table,
    build_dashboard_layout,
)


@pytest.fixture
def mock_ecosystem():
    """Sets up highly realistic mock clients for Yasin Ecosystem."""
    # Yasin-Core Client mock
    mock_core = MagicMock()
    mock_core.get_version.return_value = "1.8.4"
    mock_core.list_agents.return_value = ["eitaa_news_agent", "yasin_translator"]
    mock_core.list_tools.return_value = ["web_search", "rss_reader", "database_connector"]
    mock_core.list_plugins.return_value = ["ai_summarizer", "memory_buffer"]
    mock_core.list_providers.return_value = ["openai", "local_llama"]
    mock_core.get_info.return_value = {"name": "Yasin Core SDK Client", "version": "1.8.4", "status": "active"}

    # Yasin-Agent Client mock
    mock_agent = MagicMock()
    mock_agent.register_agent.return_value = True
    mock_agent.get_agent_status.return_value = {
        "name": "yasin-agent",
        "status": "running",
        "active_jobs": 3,
        "uptime": "48h",
    }
    mock_agent.check_agent_health.return_value = {
        "name": "yasin-agent",
        "status": "healthy",
        "cpu_usage": "15%",
    }
    mock_agent.start_agent.return_value = True
    mock_agent.stop_agent.return_value = True
    mock_agent.restart_agent.return_value = True

    # Yasin-Relay Client mock
    mock_relay = MagicMock()
    mock_relay.connect.return_value = True
    mock_relay.get_status.return_value = {
        "status": "active",
        "queue_size": 0,
        "processed_events": 1240,
        "uptime": "120h",
    }
    mock_relay.handle_event.return_value = True

    return {
        "core": mock_core,
        "agent": mock_agent,
        "relay": mock_relay,
    }


def test_e2e_successful_healthy_flow(mock_ecosystem, tmp_path):
    """
    Validates the standard, healthy end-to-end integration flow:
    YasinHub -> Yasin-Agent -> Yasin-Core -> Tools/Plugins/Memory -> YasinRelay.
    """
    # 1. Initialize Integration Layers
    core_int = CoreIntegration(client=mock_ecosystem["core"])
    agent_int = AgentIntegration(client=mock_ecosystem["agent"])
    relay_int = RelayIntegration(client=mock_ecosystem["relay"])

    # 2. Validate Communication and Compatibility (Core SDK Major Version 1 Validation)
    assert core_int.connected is True
    health = core_int.check_health()
    assert health["status"] == "healthy"
    assert health["connected"] is True
    assert health["version"] == "1.8.4"
    assert health["compatibility"] is True

    # 3. Validate Retrieval of Tools, Plugins, Agents, Providers (Runtime Info)
    info = core_int.get_runtime_info()
    assert "eitaa_news_agent" in info["agents"]
    assert "web_search" in info["tools"]
    assert "ai_summarizer" in info["plugins"]
    assert "openai" in info["providers"]

    # 4. Validate Agent Integration Workflows
    assert agent_int.connected is True
    assert agent_int.register_agent("new_assistant", "Handles coding") is True
    assert agent_int.get_agent_status("yasin-agent")["status"] == "running"
    assert agent_int.check_agent_health("yasin-agent")["status"] == "healthy"
    assert agent_int.start_agent("yasin-agent") is True
    assert agent_int.stop_agent("yasin-agent") is True
    assert agent_int.restart_agent("yasin-agent") is True

    # 5. Validate Relay Integration Workflows
    assert relay_int.connected is True
    assert relay_int.connect() is True
    assert relay_int.get_status()["status"] == "active"
    assert relay_int.handle_event("rss_alert", {"channel": "@yusinews", "items": 5}) is True

    # 6. Validate Service Discovery via Configuration Loading
    config_file = tmp_path / "config.yaml"
    # Write a custom YAML to simulate service discovery
    config_content = """
projects:
  - name: "custom_rss_bot"
    process_pattern: "custom_rss.py"
    description: "Discovered rss service"
    start_command: "python3 custom_rss.py --start"
    stop_command: "python3 custom_rss.py --stop"
  - name: "custom_agent"
    process_pattern: null
    description: "Discovered on-demand agent"
"""
    config_file.write_text(config_content, encoding="utf-8")
    discovered_projects = load_config(config_file)
    assert len(discovered_projects) == 2
    assert discovered_projects[0].name == "custom_rss_bot"
    assert discovered_projects[0].process_pattern == "custom_rss.py"
    assert discovered_projects[1].name == "custom_agent"
    assert discovered_projects[1].process_pattern is None

    # 7. Validate Runtime Status Aggregation
    # Simulate process running status check
    with patch("yasinhub.report.check_process") as mock_check:
        from yasinhub.process_checker import ProcessStatus
        mock_check.return_value = ProcessStatus(pattern="custom_rss.py", running=True, pids=["8888"])

        # Write execution status to simulated status store
        write_status("custom_rss_bot", success=True, message="Syndicated successfully", status_dir=tmp_path)
        write_status("custom_agent", success=True, message="Job done", status_dir=tmp_path)

        # Build reports based on discovered services and status store
        reports = build_report(projects=discovered_projects, status_dir=tmp_path)
        assert len(reports) == 2

        # Verify discovery of runtime process info coupled with status records
        rss_report = next(r for r in reports if r.name == "custom_rss_bot")
        assert rss_report.process_running is True
        assert rss_report.last_success is True
        assert rss_report.last_message == "Syndicated successfully"

        agent_report = next(r for r in reports if r.name == "custom_agent")
        assert agent_report.process_running is None
        assert agent_report.last_success is True
        assert agent_report.last_message == "Job done"

    # 8. Validate Health Reporting / Dashboard Assembly
    # Verify that assembling the dashboard with these components does not raise any errors
    header = make_header()
    assert header is not None

    core_panel = make_core_panel(core_int)
    assert core_panel is not None

    agent_panel = make_agent_panel(agent_int)
    assert agent_panel is not None

    relay_panel = make_relay_panel(relay_int)
    assert relay_panel is not None

    srv_table = make_services_table(reports)
    assert srv_table is not None

    layout = build_dashboard_layout(core_int, agent_int, relay_int, reports)
    assert layout is not None


def test_e2e_cli_command_flow(mock_ecosystem, tmp_path):
    """
    Validates end-to-end execution of CLI subcommands and ensures they correctly
    report information, run without crashes, and yield valid output.
    """
    core_int = CoreIntegration(client=mock_ecosystem["core"])
    agent_int = AgentIntegration(client=mock_ecosystem["agent"])
    relay_int = RelayIntegration(client=mock_ecosystem["relay"])

    # Patch the singleton instantiations
    with patch("yasinhub.core_integration.CoreIntegration", return_value=core_int), \
         patch("yasinhub.agent_integration.AgentIntegration", return_value=agent_int), \
         patch("yasinhub.relay_integration.RelayIntegration", return_value=relay_int), \
         patch("yasinhub.report.build_report") as mock_build:

        # Mock the build_report output
        mock_build.return_value = [
            ProjectReport(
                name="eitaa_news_v2",
                description="test",
                process_running=True,
                last_run="2026-07-31T12:00:00+00:00",
                last_success=True,
                last_message="Processed RSS feed",
            )
        ]

        # 1. Test "status" CLI command
        with patch("sys.stdout") as mock_stdout:
            exit_code = cli_main(["status"])
            assert exit_code == 0

        # 2. Test "core" CLI command
        with patch("sys.stdout") as mock_stdout:
            exit_code = cli_main(["core"])
            assert exit_code == 0

        # 3. Test "agent status" CLI command
        with patch("sys.stdout") as mock_stdout:
            exit_code = cli_main(["agent", "status", "yasin-agent"])
            assert exit_code == 0

        # 4. Test "agent health" CLI command
        with patch("sys.stdout") as mock_stdout:
            exit_code = cli_main(["agent", "health", "yasin-agent"])
            assert exit_code == 0

        # 5. Test "relay status" CLI command
        with patch("sys.stdout") as mock_stdout:
            exit_code = cli_main(["relay", "status"])
            assert exit_code == 0

        # 6. Test "relay event" CLI command
        with patch("sys.stdout") as mock_stdout:
            exit_code = cli_main(["relay", "event", "ping", '{"val": "pong"}'])
            assert exit_code == 0


def test_e2e_error_handling_and_compatibility(tmp_path):
    """
    Validates robust error handling across the entire ecosystem integration pipeline:
    - Library not installed (backward compatibility fallbacks)
    - Corrupted status files
    - Invalid config file (corrupted YAML)
    - Client SDKs throwing unexpected communication exceptions
    - Incompatible major SDK version
    """
    # 1. Test Library Not Installed Fallback (Backward Compatibility)
    with patch("yasinhub.core_integration.HAS_YASIN_CORE", False), \
         patch("yasinhub.agent_integration.HAS_YASIN_AGENT", False), \
         patch("yasinhub.relay_integration.HAS_YASIN_RELAY", False):

        core_int = CoreIntegration()
        agent_int = AgentIntegration()
        relay_int = RelayIntegration()

        # Connections should fail gracefully, but not crash
        assert core_int.connected is False
        assert agent_int.connected is False
        assert relay_int.connected is False

        # Status & health reporting must degrade gracefully
        health = core_int.check_health()
        assert health["status"] == "unhealthy"
        assert health["connected"] is False

        agent_health = agent_int.check_agent_health("any_agent")
        assert agent_health["status"] == "unhealthy"

        relay_status = relay_int.get_status()
        assert relay_status["status"] == "unknown"

        # Dashboard rendering when SDKs are absent must render offline/error panels safely
        core_panel = make_core_panel(core_int)
        agent_panel = make_agent_panel(agent_int)
        relay_panel = make_relay_panel(relay_int)

        from rich.console import Console
        console = Console(record=True, width=100)

        console.print(core_panel)
        core_text = console.export_text()
        assert "عدم اتصال" in core_text or "Disconnected" in core_text

        console.print(agent_panel)
        agent_text = console.export_text()
        assert "عدم اتصال" in agent_text or "Disconnected" in agent_text

        console.print(relay_panel)
        relay_text = console.export_text()
        assert "عدم اتصال" in relay_text or "Disconnected" in relay_text

    # 2. Test Incompatible Core SDK Version
    mock_incompatible_core = MagicMock()
    mock_incompatible_core.get_version.return_value = "0.5.0"  # Below the >=1.0.0 compatibility floor
    core_incompat = CoreIntegration(client=mock_incompatible_core)
    health_incompat = core_incompat.check_health()
    assert health_incompat["status"] == "unhealthy"
    assert health_incompat["compatibility"] is False
    assert "ناسازگار" in health_incompat["error"]

    # Dashboard should reflect SDK compatibility error
    core_panel_incompat = make_core_panel(core_incompat)
    assert core_panel_incompat is not None

    # 3. Test Client SDK Exceptions (Communication Breakdown)
    mock_broken_core = MagicMock()
    mock_broken_core.get_version.side_effect = Exception("Core service completely unreachable")
    mock_broken_core.list_agents.side_effect = Exception("Timeout reading agents")

    core_broken = CoreIntegration(client=mock_broken_core)
    health_broken = core_broken.check_health()
    assert health_broken["status"] == "unhealthy"
    assert "Core service completely unreachable" in health_broken["error"]

    runtime_broken = core_broken.get_runtime_info()
    assert runtime_broken["agents"] == []
    assert "Core service completely unreachable" in runtime_broken["error"] or "Timeout reading agents" in runtime_broken["error"]

    # Dashboard rendering with broken clients must handle exceptions gracefully
    core_panel_broken = make_core_panel(core_broken)
    assert core_panel_broken is not None

    # 4. Test Corrupted Status JSON Files
    corrupt_file = tmp_path / "eitaa_news_v2.json"
    corrupt_file.write_text("{broken json file: [unclosed brackets", encoding="utf-8")
    status_record = read_status("eitaa_news_v2", status_dir=tmp_path)
    assert status_record is not None
    assert "خراب/نامعتبر" in status_record.message

    all_statuses = read_all_statuses(status_dir=tmp_path)
    assert all_statuses["eitaa_news_v2"].message == "فایل وضعیت خراب/نامعتبر است"

    # 5. Test Corrupted Configuration YAML File
    corrupt_config = tmp_path / "config.yaml"
    corrupt_config.write_text("invalid_yaml: [[: unclosed brackets", encoding="utf-8")

    # Validation should catch it or fallback gracefully to default registry
    loaded_projects = load_config(corrupt_config)
    assert len(loaded_projects) > 0  # Should fallback to default projects safely
