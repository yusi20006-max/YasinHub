"""
tests/test_core_integration.py
تست‌های یکپارچه‌سازی و واحد لایه اتصال به Yasin-Core.
"""

from unittest.mock import MagicMock, patch
import sys
import pytest

from yasinhub.core_integration import CoreIntegration, validate_sdk_compatibility
from yasinhub.cli import main as cli_main


def test_validate_sdk_compatibility():
    # تست سازگاری نسخه‌ها (بر پایه موتور semver واقعی Core: >=1.0.0)
    assert validate_sdk_compatibility("1.0.0") is True
    assert validate_sdk_compatibility("1.5.2") is True
    assert validate_sdk_compatibility("3.3.0") is True
    assert validate_sdk_compatibility("0.5.0") is False
    assert validate_sdk_compatibility("") is False
    assert validate_sdk_compatibility(None) is False


def test_core_integration_when_not_installed():
    # شبیه‌سازی عدم حضور yasin_core
    with patch("yasinhub.core_integration.HAS_YASIN_CORE", False):
        integration = CoreIntegration()
        assert integration.connected is False
        assert "یافت نشد" in integration.connection_error or "نصب" in integration.connection_error

        health = integration.check_health()
        assert health["status"] == "unhealthy"
        assert health["connected"] is False
        assert health["compatibility"] is False

        runtime_info = integration.get_runtime_info()
        assert runtime_info["agents"] == []
        assert runtime_info["tools"] == []


def test_core_integration_with_mocked_client():
    # شبیه‌سازی کلاینت واقعی با رفتارهای مختلف
    mock_client = MagicMock()
    mock_client.get_version.return_value = "1.2.3"
    mock_client.list_agents.return_value = ["agent_1", "agent_2"]
    mock_client.list_tools.return_value = ["tool_1"]
    mock_client.list_plugins.return_value = ["plugin_1"]
    mock_client.list_providers.return_value = ["openai"]
    mock_client.get_info.return_value = {"name": "Yasin Core SDK Client", "version": "1.2.3"}

    integration = CoreIntegration(client=mock_client)
    assert integration.connected is True

    health = integration.check_health()
    assert health["status"] == "healthy"
    assert health["connected"] is True
    assert health["version"] == "1.2.3"
    assert health["compatibility"] is True

    runtime = integration.get_runtime_info()
    assert runtime["agents"] == ["agent_1", "agent_2"]
    assert runtime["tools"] == ["tool_1"]
    assert runtime["plugins"] == ["plugin_1"]
    assert runtime["providers"] == ["openai"]


def test_core_integration_with_incompatible_version():
    mock_client = MagicMock()
    mock_client.get_version.return_value = "0.5.0"

    integration = CoreIntegration(client=mock_client)
    health = integration.check_health()
    assert health["status"] == "unhealthy"
    assert health["compatibility"] is False
    assert "ناسازگار" in health["error"]


def test_core_integration_client_exception_handling():
    mock_client = MagicMock()
    mock_client.get_version.side_effect = Exception("مشکل ارتباط با پایگاه داده")

    integration = CoreIntegration(client=mock_client)
    health = integration.check_health()
    assert health["status"] == "unhealthy"
    assert health["connected"] is False
    assert "خطا در ارتباط" in health["error"]


def test_cli_core_command_not_installed(capsys):
    with patch("yasinhub.core_integration.HAS_YASIN_CORE", False):
        code = cli_main(["core"])
        assert code == 0
        captured = capsys.readouterr()
        assert "وضعیت اتصال: عدم اتصال" in captured.out
        assert "yasin_core" in captured.out or "یافت نشد" in captured.out or "نصب" in captured.out


def test_cli_core_command_installed_and_healthy(capsys):
    mock_client = MagicMock()
    mock_client.get_version.return_value = "1.0.0"
    mock_client.list_agents.return_value = ["AI-Agent"]
    mock_client.list_tools.return_value = ["SearchTool"]
    mock_client.list_plugins.return_value = []
    mock_client.list_providers.return_value = ["mock_provider"]
    mock_client.get_info.return_value = {"name": "Yasin Core SDK Client", "version": "1.0.0"}

    mock_integration = CoreIntegration(client=mock_client)

    with patch("yasinhub.core_integration.CoreIntegration", return_value=mock_integration):
        code = cli_main(["core"])
        assert code == 0
        captured = capsys.readouterr()
        assert "وضعیت اتصال: متصل" in captured.out
        assert "نسخه SDK: 1.0.0" in captured.out
        assert "سازگاری SDK: معتبر" in captured.out
        assert "AI-Agent" in captured.out
        assert "SearchTool" in captured.out


# تست ادغام با SDK واقعی در صورت وجود و ست بودن PYTHONPATH
def test_real_sdk_integration():
    try:
        from yasin_core.sdk import YasinCoreClient
        from yasin_core.version import VERSION
        real_client_available = True
    except ImportError:
        real_client_available = False

    if real_client_available:
        integration = CoreIntegration()
        assert integration.connected is True

        health = integration.check_health()
        assert health["connected"] is True
        assert health["compatibility"] is True
        assert health["version"] == VERSION

        runtime = integration.get_runtime_info()
        assert "agents" in runtime
        assert "tools" in runtime
        assert "plugins" in runtime
