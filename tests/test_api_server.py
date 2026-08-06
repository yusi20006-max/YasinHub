"""
tests/test_api_server.py
تست‌های مربوط به HTTP API Server و اندپوینت‌های کنترلی و اطلاعاتی.
"""

import json
from io import BytesIO
from unittest.mock import patch, MagicMock
import pytest
from yasinhub.api.server import YasinHubHandler
from yasinhub.registry import ProjectEntry


class MockRequest:
    def __init__(self):
        pass

    def makefile(self, *args, **kwargs):
        return BytesIO(b"")

    def sendall(self, data):
        pass


class DummyHandler(YasinHubHandler):
    def __init__(self, request, client_address, server):
        self.request = request
        self.client_address = client_address
        self.server = server
        self.wfile = BytesIO()
        self.headers = {}
        self.command = "GET"
        self.path = "/"
        self.response_code = None
        self.response_headers = {}

    def setup(self):
        pass

    def handle(self):
        pass

    def finish(self):
        pass

    def send_response(self, code, message=None):
        self.response_code = code

    def send_header(self, keyword, value):
        self.response_headers[keyword] = value

    def end_headers(self):
        pass


@pytest.fixture
def dummy_handler():
    req = MockRequest()
    handler = DummyHandler(req, ("127.0.0.1", 12345), MagicMock())
    return handler


@patch("yasinhub.api.server.build_report")
def test_api_status_endpoint(mock_build_report, dummy_handler):
    mock_report = MagicMock()
    mock_report.name = "test_srv"
    mock_report.health_state = "RUNNING"
    mock_report.last_run = "2026-07-26"
    mock_report.last_success = True
    mock_report.last_message = "All good"
    mock_report.metrics = {"cpu": 1.2}
    mock_report.db_stats = {"total_posts": 100}
    mock_report.health = {}
    mock_build_report.return_value = [mock_report]

    dummy_handler.path = "/api/status"
    dummy_handler.do_GET()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["ecosystem"] == "Yasin"
    assert len(response_data["projects"]) == 1
    assert response_data["projects"][0]["name"] == "test_srv"
    assert response_data["projects"][0]["status"] == "RUNNING"


@patch("yasinhub.api.server.default_registry")
def test_api_services_endpoint(mock_registry, dummy_handler):
    mock_registry.return_value = [
        ProjectEntry(name="eitaa_news_v2", description="test description", path="/dummy/path")
    ]

    dummy_handler.path = "/api/services"
    dummy_handler.do_GET()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["ecosystem"] == "Yasin"
    assert len(response_data["services"]) == 1
    assert response_data["services"][0]["name"] == "eitaa_news_v2"


@patch("yasinhub.api.server.default_registry")
@patch("yasinhub.api.server.start_service")
def test_api_control_start_via_get(mock_start, mock_registry, dummy_handler):
    project = ProjectEntry(name="yasinrelay", start_command="dummy")
    mock_registry.return_value = [project]
    mock_start.return_value = True

    dummy_handler.path = "/api/control/yasinrelay/start"
    dummy_handler.do_GET()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["service"] == "yasinrelay"
    assert response_data["action"] == "start"
    assert response_data["success"] is True
    mock_start.assert_called_once_with(project)


@patch("yasinhub.api.server.default_registry")
@patch("yasinhub.api.server.stop_service")
def test_api_control_stop_via_post(mock_stop, mock_registry, dummy_handler):
    project = ProjectEntry(name="yasinrelay", start_command="dummy")
    mock_registry.return_value = [project]
    mock_stop.return_value = True

    dummy_handler.path = "/api/control/yasinrelay/stop"
    dummy_handler.do_POST()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["service"] == "yasinrelay"
    assert response_data["action"] == "stop"
    assert response_data["success"] is True
    mock_stop.assert_called_once_with(project)


@patch("yasinhub.api.server.default_registry")
@patch("yasinhub.api.server.read_pid")
@patch("yasinhub.api.server.is_pid_alive")
@patch("yasinhub.api.server.build_report")
def test_api_metrics_endpoint_with_pid(mock_build_report, mock_is_alive, mock_read_pid, mock_registry, dummy_handler):
    project = ProjectEntry(name="yasin-ai", start_command="dummy")
    mock_registry.return_value = [project]
    mock_read_pid.return_value = 9999
    mock_is_alive.return_value = True

    dummy_handler.path = "/api/metrics/yasin-ai"
    dummy_handler.do_GET()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["service"] == "yasin-ai"
    assert response_data["pid"] == 9999
