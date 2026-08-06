"""
tests/test_agent_integration.py
تست‌های لایه یکپارچه‌سازی و دستورات CLI مرتبط با Yasin-Agent.
"""

from unittest.mock import MagicMock, patch
import pytest

from yasinhub.agent_integration import AgentIntegration
from yasinhub.cli import main as cli_main


def test_agent_integration_when_not_installed():
    # شبیه‌سازی عدم حضور yasin_agent
    with patch("yasinhub.agent_integration.HAS_YASIN_AGENT", False):
        integration = AgentIntegration()
        assert integration.connected is False
        assert "یافت نشد" in integration.connection_error or "نصب" in integration.connection_error

        # بررسی رفتار متدها در حالت عدم اتصال کلاینت
        assert integration.register_agent("test_agent") is False

        status = integration.get_agent_status("test_agent")
        assert status["status"] == "unknown"
        assert "yasin_agent" in status["error"] or "یافت نشد" in status["error"]

        assert integration.start_agent("test_agent") is False
        assert integration.stop_agent("test_agent") is False
        assert integration.restart_agent("test_agent") is False

        health = integration.check_agent_health("test_agent")
        assert health["status"] == "unhealthy"
        assert "yasin_agent" in health["error"] or "یافت نشد" in health["error"]


def test_agent_integration_with_mocked_client():
    # شبیه‌سازی کلاینت واقعی با رفتارهای مختلف
    mock_client = MagicMock()
    mock_client.register_agent.return_value = True
    mock_client.get_agent_status.return_value = {"name": "test_agent", "status": "running", "jobs_completed": 5}
    mock_client.start_agent.return_value = True
    mock_client.stop_agent.return_value = True
    mock_client.restart_agent.return_value = True
    mock_client.check_agent_health.return_value = {"name": "test_agent", "status": "healthy", "uptime": "2h"}

    integration = AgentIntegration(client=mock_client)
    assert integration.connected is True

    # ۱. ثبت عامل
    assert integration.register_agent("test_agent", "توضیحات تست") is True
    mock_client.register_agent.assert_called_once_with("test_agent", "توضیحات تست")

    # ۲. مانیتورینگ وضعیت عامل
    status = integration.get_agent_status("test_agent")
    assert status["status"] == "running"
    assert status["jobs_completed"] == 5

    # ۳. مدیریت چرخه حیات عامل
    assert integration.start_agent("test_agent") is True
    assert integration.stop_agent("test_agent") is True
    assert integration.restart_agent("test_agent") is True

    # ۴. بررسی سلامت عامل
    health = integration.check_agent_health("test_agent")
    assert health["status"] == "healthy"
    assert health["uptime"] == "2h"


def test_agent_integration_fallback_restart():
    # شبیه‌سازی کلاینتی که تابع restart_agent را ندارد
    mock_client = MagicMock()
    del mock_client.restart_agent # حذف متد ری‌استارت سفارشی برای استفاده از فال‌بک
    mock_client.start_agent.return_value = True
    mock_client.stop_agent.return_value = True

    integration = AgentIntegration(client=mock_client)
    assert integration.restart_agent("test_agent") is True
    mock_client.stop_agent.assert_called_once_with("test_agent")
    mock_client.start_agent.assert_called_once_with("test_agent")


def test_agent_integration_client_exception_handling():
    mock_client = MagicMock()
    mock_client.register_agent.side_effect = Exception("خطای نامشخص در پایگاه داده")
    mock_client.get_agent_status.side_effect = Exception("یافت نشد")
    mock_client.start_agent.side_effect = Exception("خطا")
    mock_client.stop_agent.side_effect = Exception("خطا")
    mock_client.restart_agent.side_effect = Exception("خطا")
    mock_client.check_agent_health.side_effect = Exception("خطای اتصال")

    integration = AgentIntegration(client=mock_client)

    assert integration.register_agent("test_agent") is False

    status = integration.get_agent_status("test_agent")
    assert status["status"] == "error"
    assert "یافت نشد" in status["error"]

    assert integration.start_agent("test_agent") is False
    assert integration.stop_agent("test_agent") is False
    assert integration.restart_agent("test_agent") is False

    health = integration.check_agent_health("test_agent")
    assert health["status"] == "unhealthy"
    assert "خطای اتصال" in health["error"]


def test_cli_agent_subcommands_not_installed(capsys):
    with patch("yasinhub.agent_integration.HAS_YASIN_AGENT", False):
        # تست عدم امکان ثبت عامل
        code = cli_main(["agent", "register", "test_agent"])
        assert code == 1
        captured = capsys.readouterr()
        assert "خطا" in captured.out
        assert "yasin_agent نصب و متصل باشد" in captured.out

        # تست نمایش وضعیت عامل در صورت عدم نصب
        code = cli_main(["agent", "status", "test_agent"])
        assert code == 1
        captured = capsys.readouterr()
        assert "خطا" in captured.out
        assert "yasin_agent یافت نشد یا نصب نیست" in captured.out


def test_cli_agent_subcommands_success(capsys):
    mock_client = MagicMock()
    mock_client.register_agent.return_value = True
    mock_client.get_agent_status.return_value = {"name": "agent_x", "status": "idle", "last_task": "task_1"}
    mock_client.check_agent_health.return_value = {"name": "agent_x", "status": "healthy"}
    mock_client.start_agent.return_value = True
    mock_client.stop_agent.return_value = True
    mock_client.restart_agent.return_value = True

    mock_integration = AgentIntegration(client=mock_client)

    with patch("yasinhub.agent_integration.AgentIntegration", return_value=mock_integration):
        # ۱. ثبت عامل
        code = cli_main(["agent", "register", "agent_x", "--description", "توضیح عامل"])
        assert code == 0
        captured = capsys.readouterr()
        assert "با موفقیت ثبت شد" in captured.out

        # ۲. وضعیت عامل
        code = cli_main(["agent", "status", "agent_x"])
        assert code == 0
        captured = capsys.readouterr()
        assert "وضعیت عامل: agent_x" in captured.out
        assert "وضعیت فعلی: idle" in captured.out
        assert "last_task: task_1" in captured.out

        # ۳. سلامت عامل
        code = cli_main(["agent", "health", "agent_x"])
        assert code == 0
        captured = capsys.readouterr()
        assert "بررسی سلامت عامل: agent_x" in captured.out
        assert "وضعیت سلامت: healthy" in captured.out

        # ۴. شروع به کار عامل
        code = cli_main(["agent", "start", "agent_x"])
        assert code == 0
        captured = capsys.readouterr()
        assert "با موفقیت شروع به کار کرد" in captured.out

        # ۵. متوقف کردن عامل
        code = cli_main(["agent", "stop", "agent_x"])
        assert code == 0
        captured = capsys.readouterr()
        assert "با موفقیت متوقف شد" in captured.out

        # ۶. راه‌اندازی مجدد عامل
        code = cli_main(["agent", "restart", "agent_x"])
        assert code == 0
        captured = capsys.readouterr()
        assert "با موفقیت راه‌اندازی مجدد شد" in captured.out


def test_cli_agent_subcommands_failure(capsys):
    mock_client = MagicMock()
    mock_client.register_agent.return_value = False
    mock_client.get_agent_status.return_value = {"name": "agent_x", "status": "error", "error": "دیتابیس در دسترس نیست"}
    mock_client.check_agent_health.return_value = {"name": "agent_x", "status": "unhealthy", "error": "حافظه پر شده است"}
    mock_client.start_agent.return_value = False
    mock_client.stop_agent.return_value = False
    mock_client.restart_agent.return_value = False

    mock_integration = AgentIntegration(client=mock_client)

    with patch("yasinhub.agent_integration.AgentIntegration", return_value=mock_integration):
        # ثبت عامل ناموفق
        code = cli_main(["agent", "register", "agent_x"])
        assert code == 1
        captured = capsys.readouterr()
        assert "ثبت عامل 'agent_x' انجام نشد" in captured.out

        # وضعیت عامل با خطا
        code = cli_main(["agent", "status", "agent_x"])
        assert code == 1
        captured = capsys.readouterr()
        assert "خطا: دیتابیس در دسترس نیست" in captured.out

        # سلامت عامل با خطا
        code = cli_main(["agent", "health", "agent_x"])
        assert code == 1
        captured = capsys.readouterr()
        assert "وضعیت سلامت: ناسالم" in captured.out
        assert "خطا: حافظه پر شده است" in captured.out

        # شروع به کار ناموفق
        code = cli_main(["agent", "start", "agent_x"])
        assert code == 1
        captured = capsys.readouterr()
        assert "شروع به کار عامل 'agent_x' ناموفق بود" in captured.out

        # توقف ناموفق
        code = cli_main(["agent", "stop", "agent_x"])
        assert code == 1
        captured = capsys.readouterr()
        assert "متوقف کردن عامل 'agent_x' ناموفق بود" in captured.out

        # راه‌اندازی مجدد ناموفق
        code = cli_main(["agent", "restart", "agent_x"])
        assert code == 1
        captured = capsys.readouterr()
        assert "راه‌اندازی مجدد عامل 'agent_x' ناموفق بود" in captured.out
