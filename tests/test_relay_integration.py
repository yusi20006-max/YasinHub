"""
tests/test_relay_integration.py
تست‌های لایه یکپارچه‌سازی و دستورات CLI مرتبط با Yasin-Relay.
"""

from unittest.mock import MagicMock, patch
import pytest

from yasinhub.relay_integration import RelayIntegration
from yasinhub.cli import main as cli_main


def test_relay_integration_when_not_installed():
    # شبیه‌سازی عدم حضور yasin_relay
    with patch("yasinhub.relay_integration.HAS_YASIN_RELAY", False):
        integration = RelayIntegration()
        assert integration.connected is False
        assert "یافت نشد" in integration.connection_error or "نصب" in integration.connection_error

        # بررسی رفتار متدها در حالت عدم اتصال کلاینت
        assert integration.connect() is False

        status = integration.get_status()
        assert status["status"] == "unknown"
        assert "yasin_relay" in status["error"] or "یافت نشد" in status["error"]

        assert integration.handle_event("message", {"text": "hello"}) is False


def test_relay_integration_with_mocked_client():
    # شبیه‌سازی کلاینت واقعی با رفتارهای مختلف
    mock_client = MagicMock()
    mock_client.connect.return_value = True
    mock_client.get_status.return_value = {"status": "connected", "active_rules": 5, "processed_messages": 120}
    mock_client.handle_event.return_value = True

    integration = RelayIntegration(client=mock_client)
    assert integration.connected is True

    # ۱. اتصال به سرویس رله
    assert integration.connect() is True
    mock_client.connect.assert_called_once()

    # ۲. مانیتورینگ وضعیت سرویس رله
    status = integration.get_status()
    assert status["status"] == "connected"
    assert status["active_rules"] == 5
    assert status["processed_messages"] == 120

    # ۳. مدیریت رویدادهای رله
    assert integration.handle_event("message", {"text": "hello"}) is True
    mock_client.handle_event.assert_called_once_with("message", {"text": "hello"})


def test_relay_integration_client_exception_handling():
    mock_client = MagicMock()
    mock_client.connect.side_effect = Exception("خطای اتصال")
    mock_client.get_status.side_effect = Exception("خطای ران‌تایم")
    mock_client.handle_event.side_effect = Exception("فرمت نامعتبر")

    integration = RelayIntegration(client=mock_client)

    assert integration.connect() is False

    status = integration.get_status()
    assert status["status"] == "error"
    assert "خطای ران‌تایم" in status["error"]

    assert integration.handle_event("message", {"text": "hello"}) is False


def test_cli_relay_subcommands_not_installed(capsys):
    with patch("yasinhub.relay_integration.HAS_YASIN_RELAY", False):
        # تست عدم اتصال
        code = cli_main(["relay", "connect"])
        assert code == 1
        captured = capsys.readouterr()
        assert "خطا" in captured.out
        assert "yasin_relay نصب و متصل باشد" in captured.out

        # تست نمایش وضعیت در صورت عدم نصب
        code = cli_main(["relay", "status"])
        assert code == 1
        captured = capsys.readouterr()
        assert "خطا" in captured.out
        assert "yasin_relay یافت نشد یا نصب نیست" in captured.out


def test_cli_relay_subcommands_success(capsys):
    mock_client = MagicMock()
    mock_client.connect.return_value = True
    mock_client.get_status.return_value = {"status": "active", "uptime": "5h", "processed": 42}
    mock_client.handle_event.return_value = True

    mock_integration = RelayIntegration(client=mock_client)

    with patch("yasinhub.relay_integration.RelayIntegration", return_value=mock_integration):
        # ۱. اتصال
        code = cli_main(["relay", "connect"])
        assert code == 0
        captured = capsys.readouterr()
        assert "ارتباط با سرویس رله با موفقیت برقرار شد" in captured.out

        # ۲. وضعیت
        code = cli_main(["relay", "status"])
        assert code == 0
        captured = capsys.readouterr()
        assert "وضعیت سرویس رله Yasin-Relay" in captured.out
        assert "وضعیت فعلی: active" in captured.out
        assert "uptime: 5h" in captured.out
        assert "processed: 42" in captured.out

        # ۳. ارسال رویداد (با جیسون معتبر)
        code = cli_main(["relay", "event", "user_join", '{"user_id": 123}'])
        assert code == 0
        captured = capsys.readouterr()
        assert "با موفقیت پردازش شد" in captured.out

        # ۴. ارسال رویداد (با متن ساده به عنوان بک‌آپ)
        code = cli_main(["relay", "event", "alert", "some simple string"])
        assert code == 0
        captured = capsys.readouterr()
        assert "با موفقیت پردازش شد" in captured.out


def test_cli_relay_subcommands_failure(capsys):
    mock_client = MagicMock()
    mock_client.connect.return_value = False
    mock_client.get_status.return_value = {"status": "error", "error": "رله غیرفعال است"}
    mock_client.handle_event.return_value = False

    mock_integration = RelayIntegration(client=mock_client)

    with patch("yasinhub.relay_integration.RelayIntegration", return_value=mock_integration):
        # اتصال ناموفق
        code = cli_main(["relay", "connect"])
        assert code == 1
        captured = capsys.readouterr()
        assert "خطا" in captured.out

        # وضعیت با خطا
        code = cli_main(["relay", "status"])
        assert code == 1
        captured = capsys.readouterr()
        assert "خطا: رله غیرفعال است" in captured.out

        # ارسال رویداد ناموفق
        code = cli_main(["relay", "event", "user_join", '{"user_id": 123}'])
        assert code == 1
        captured = capsys.readouterr()
        assert "ناموفق بود" in captured.out


def test_relay_integration_verify_channels_fallback_and_custom():
    # ۱. سناریوی عدم اتصال کلاینت
    with patch("yasinhub.relay_integration.HAS_YASIN_RELAY", False):
        integration = RelayIntegration()
        result = integration.verify_channels(["channel1"])
        assert result["status"] == "error"
        assert result["verified"] is False
        assert "کلاینت متصل نیست" in result["error"]

    # ۲. سناریوی کلاینت متصل بدون وجود متد verify_channels در SDK
    mock_client_old = MagicMock(spec=[])  # فاقد متد
    integration_old = RelayIntegration(client=mock_client_old)
    result = integration_old.verify_channels(["channel1"])
    assert result["status"] == "success"
    assert result["verified"] is True
    assert "channel1" in result["channels"]

    # ۳. سناریوی کلاینت متصل همراه با متد verify_channels در SDK
    mock_client_new = MagicMock()
    mock_result = {"status": "success", "verified": True, "channels": ["channel2"]}
    mock_client_new.verify_channels.return_value = mock_result
    integration_new = RelayIntegration(client=mock_client_new)

    result = integration_new.verify_channels(["channel2"])
    assert result == mock_result
    mock_client_new.verify_channels.assert_called_once_with(["channel2"])


def test_cli_relay_verify_channels_success(capsys):
    mock_client = MagicMock()
    mock_result = {
        "status": "success",
        "verified": True,
        "channels": ["@yusinews", "telegram_main"],
        "message": "کانال‌ها با موفقیت تأیید شدند"
    }
    mock_client.verify_channels.return_value = mock_result
    mock_integration = RelayIntegration(client=mock_client)

    with patch("yasinhub.relay_integration.RelayIntegration", return_value=mock_integration):
        code = cli_main(["relay", "verify-channels", "@yusinews", "telegram_main"])
        assert code == 0
        captured = capsys.readouterr()
        assert "وضعیت تأیید کانال‌ها" in captured.out
        assert "وضعیت: success" in captured.out
        assert "کانال‌های تأیید شده: @yusinews, telegram_main" in captured.out
        assert "پیام: کانال‌ها با موفقیت تأیید شدند" in captured.out


def test_cli_relay_verify_channels_failure(capsys):
    mock_client = MagicMock()
    mock_result = {
        "status": "error",
        "verified": False,
        "error": "عدم دسترسی به کانال‌ها"
    }
    mock_client.verify_channels.return_value = mock_result
    mock_integration = RelayIntegration(client=mock_client)

    with patch("yasinhub.relay_integration.RelayIntegration", return_value=mock_integration):
        code = cli_main(["relay", "verify-channels", "@invalid_channel"])
        assert code == 1
        captured = capsys.readouterr()
        assert "تأیید کانال‌ها ناموفق بود" in captured.out
        assert "عدم دسترسی به کانال‌ها" in captured.out
