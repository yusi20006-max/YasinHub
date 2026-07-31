"""
tests/test_dashboard.py
تست‌های واحد و یکپارچه‌سازی داشبورد مانیتورینگ سلامت اکوسیستم یاسین.
"""

from unittest.mock import MagicMock, patch
import sys
import pytest
from rich.console import Console

from yasinhub.dashboard import (
    make_header,
    make_core_panel,
    make_agent_panel,
    make_relay_panel,
    make_services_table,
    build_dashboard_layout,
    display_dashboard,
)
from yasinhub.core_integration import CoreIntegration
from yasinhub.agent_integration import AgentIntegration
from yasinhub.relay_integration import RelayIntegration
from yasinhub.report import ProjectReport


def test_make_header():
    panel = make_header()
    assert panel is not None

    console = Console()
    with console.capture() as capture:
        console.print(panel)
    output = capture.get()
    assert "مانیتورینگ" in output
    assert "سلامت" in output
    assert "یاسین" in output


def test_make_core_panel_connected():
    mock_client = MagicMock()
    mock_client.get_version.return_value = "1.2.3"
    mock_client.list_agents.return_value = ["ai-agent-1"]
    mock_client.list_tools.return_value = ["search-tool"]
    mock_client.list_plugins.return_value = []
    mock_client.list_providers.return_value = ["mock-openai"]
    mock_client.get_info.return_value = {}

    core = CoreIntegration(client=mock_client)
    panel = make_core_panel(core)

    assert panel is not None
    # بررسی رنگ سبز در صورت متصل بودن
    assert panel.border_style == "green"


def test_make_core_panel_disconnected():
    with patch("yasinhub.core_integration.HAS_YASIN_CORE", False):
        core = CoreIntegration()
        panel = make_core_panel(core)

        assert panel is not None
        assert panel.border_style == "red"


def test_make_agent_panel_connected():
    mock_client = MagicMock()
    mock_client.get_agent_status.return_value = {"status": "running", "jobs_completed": 15}
    mock_client.check_agent_health.return_value = {"status": "healthy"}

    agent = AgentIntegration(client=mock_client)
    panel = make_agent_panel(agent)

    assert panel is not None
    assert panel.border_style == "green"


def test_make_agent_panel_disconnected():
    with patch("yasinhub.agent_integration.HAS_YASIN_AGENT", False):
        agent = AgentIntegration()
        panel = make_agent_panel(agent)

        assert panel is not None
        assert panel.border_style == "red"


def test_make_relay_panel_connected():
    mock_client = MagicMock()
    mock_client.get_status.return_value = {"status": "active", "messages_relayed": 42}

    relay = RelayIntegration(client=mock_client)
    panel = make_relay_panel(relay)

    assert panel is not None
    assert panel.border_style == "green"


def test_make_relay_panel_disconnected():
    with patch("yasinhub.relay_integration.HAS_YASIN_RELAY", False):
        relay = RelayIntegration()
        panel = make_relay_panel(relay)

        assert panel is not None
        assert panel.border_style == "red"


def test_make_services_table():
    reports = [
        ProjectReport(
            name="test_service",
            description="دسکریپشن",
            process_running=True,
            last_run="2026-07-26",
            last_success=True,
            last_message="اوکی",
        )
    ]
    table = make_services_table(reports)
    assert table is not None
    assert table.title == "[bold cyan]وضعیت و سلامت سرویس‌های اکوسیستم یاسین[/bold cyan]"


def test_build_dashboard_layout():
    core = CoreIntegration()
    agent = AgentIntegration()
    relay = RelayIntegration()
    reports = []

    layout = build_dashboard_layout(core, agent, relay, reports)
    assert layout is not None
    assert layout["header"] is not None
    assert layout["body"] is not None


@patch("yasinhub.dashboard.build_report")
@patch("yasinhub.dashboard.Console.print")
def test_display_dashboard_static(mock_print, mock_build_report):
    mock_build_report.return_value = []
    display_dashboard(live_mode=False)
    mock_print.assert_called_once()


@patch("yasinhub.dashboard.build_report")
@patch("yasinhub.dashboard.Live")
@patch("yasinhub.dashboard.time.sleep", side_effect=KeyboardInterrupt)
def test_display_dashboard_live(mock_sleep, mock_live, mock_build_report):
    mock_build_report.return_value = []
    display_dashboard(live_mode=True, update_interval=1.0)
    mock_live.assert_called_once()
