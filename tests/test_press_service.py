import pytest
from unittest.mock import MagicMock, patch
from yasinhub.press_integration import PressIntegration
from yasinhub.services.press_service import PressService


def test_press_integration_when_not_installed():
    """Verify PressIntegration behavior when yasin_press is not installed/imported."""
    with patch("yasinhub.press_integration.HAS_YASIN_PRESS", False):
        integration = PressIntegration()
        assert integration.connected is False
        assert "یافت نشد یا نصب نیست" in integration.connection_error

        status = integration.get_status()
        assert status["status"] == "unknown"
        assert "یافت نشد یا نصب نیست" in status["error"]

        health = integration.check_health()
        assert health["status"] == "unhealthy"
        assert "یافت نشد یا نصب نیست" in health["error"]

        rewrites = integration.get_rewrites()
        assert rewrites == []


def test_press_integration_with_mocked_client():
    """Verify PressIntegration handles connection and method calls with a mocked SDK client."""
    mock_client = MagicMock()
    mock_client.get_status.return_value = {"status": "active", "db_version": "1.0.4"}
    mock_client.check_health.return_value = {"status": "healthy"}
    mock_client.get_rewrites.return_value = [
        {"id": "1", "original_title": "Old Title", "rewritten_title": "New Title", "status": "completed"}
    ]

    integration = PressIntegration(client=mock_client)
    assert integration.connected is True

    status = integration.get_status()
    assert status["status"] == "active"
    assert status["db_version"] == "1.0.4"

    health = integration.check_health()
    assert health["status"] == "healthy"

    rewrites = integration.get_rewrites(limit=5)
    assert len(rewrites) == 1
    assert rewrites[0]["id"] == "1"
    assert rewrites[0]["rewritten_title"] == "New Title"


def test_press_integration_client_exception_handling():
    """Verify that PressIntegration catches client exceptions during calls and fails gracefully."""
    mock_client = MagicMock()
    mock_client.get_status.side_effect = Exception("SDK Connection Refused")
    mock_client.check_health.side_effect = Exception("SDK Timeout")
    mock_client.get_rewrites.side_effect = Exception("Database Failure")

    integration = PressIntegration(client=mock_client)
    assert integration.connected is True

    status = integration.get_status()
    assert status["status"] == "error"
    assert "SDK Connection Refused" in status["error"]

    health = integration.check_health()
    assert health["status"] == "unhealthy"
    assert "SDK Timeout" in health["error"]

    rewrites = integration.get_rewrites()
    assert rewrites == []


def test_press_service_health_healthy():
    """Verify PressService.health() behavior when the integration reports healthy status."""
    mock_integration = MagicMock()
    mock_integration.check_health.return_value = {"status": "healthy"}

    service = PressService(press_integration=mock_integration)
    res = service.health()

    assert res["service"] == "YasinPress Service"
    assert res["status"] == "healthy"
    assert res["error"] is None


def test_press_service_health_unhealthy():
    """Verify PressService.health() behavior when the integration is unhealthy or fails."""
    mock_integration = MagicMock()
    mock_integration.check_health.return_value = {"status": "unhealthy", "error": "Database is down"}

    service = PressService(press_integration=mock_integration)
    res = service.health()

    assert res["service"] == "YasinPress Service"
    assert res["status"] == "unhealthy"
    assert res["error"] == "Database is down"


def test_press_service_get_status():
    """Verify PressService.get_status() accurately forwards call to integration."""
    mock_integration = MagicMock()
    mock_integration.get_status.return_value = {"status": "active", "total_posts": 42}

    service = PressService(press_integration=mock_integration)
    res = service.get_status()

    assert res["status"] == "active"
    assert res["total_posts"] == 42


def test_press_service_get_rewrites():
    """Verify PressService.get_rewrites() accurately forwards call to integration."""
    mock_integration = MagicMock()
    mock_integration.get_rewrites.return_value = [{"id": "100"}]

    service = PressService(press_integration=mock_integration)
    res = service.get_rewrites(limit=15)

    assert len(res) == 1
    assert res[0]["id"] == "100"
    mock_integration.get_rewrites.assert_called_once_with(limit=15)
