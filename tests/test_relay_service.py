"""
tests/test_relay_service.py
تست‌های مربوط به کلاس RelayService در لایه سرویس‌های اکوسیستم یاسین.
"""

from unittest.mock import MagicMock, patch
import pytest

from yasinhub.services.relay_service import RelayService


def test_relay_service_health():
    """بررسی رفتار و خروجی متد health سرویس رله"""
    service = RelayService()

    # شبیه‌سازی وضعیت کلاینت متصل
    mock_status = {"status": "active", "processed_events": 100}
    with patch.object(service.relay, "get_status", return_value=mock_status):
        health_info = service.health()
        assert health_info["service"] == "YasinHub Relay Service"
        assert health_info["status"] == mock_status


def test_relay_service_connect():
    """بررسی برقراری ارتباط با سرویس رله"""
    service = RelayService()

    with patch.object(service.relay, "connect", return_value=True):
        assert service.connect() is True

    with patch.object(service.relay, "connect", return_value=False):
        assert service.connect() is False


def test_relay_service_handle_event():
    """بررسی ارسال و پردازش رویداد در سرویس رله"""
    service = RelayService()

    payload = {"message": "hello"}
    with patch.object(service.relay, "handle_event", return_value=True) as mock_handle:
        assert service.handle_event("test_event", payload) is True
        mock_handle.assert_called_once_with("test_event", payload)


def test_relay_service_verify_channels():
    """بررسی تأیید و به‌روزرسانی کانال‌ها در سرویس رله"""
    service = RelayService()

    mock_result = {
        "status": "success",
        "verified": True,
        "channels": ["@yusinews"],
        "message": "کانال‌ها معتبر هستند"
    }

    with patch.object(service.relay, "verify_channels", return_value=mock_result) as mock_verify:
        result = service.verify_channels(["@yusinews"])
        assert result == mock_result
        mock_verify.assert_called_once_with(["@yusinews"])
