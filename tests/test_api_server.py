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


@patch("yasinhub.api.service_control_helpers.is_pid_alive", return_value=False)
@patch("yasinhub.api.service_control_helpers.read_pid", return_value=None)
@patch("yasinhub.api.server.build_report")
def test_api_status_endpoint(mock_build_report, mock_read_pid, mock_alive, dummy_handler):
    mock_report = MagicMock()
    mock_report.name = "yasinrelay"
    mock_report.health_state = "RUNNING"
    mock_report.last_run = "2024-01-01T00:00:00"
    mock_report.last_success = True
    mock_report.last_message = "ok"
    mock_report.metrics = {}
    mock_report.db_stats = {}
    mock_report.health = {}
    mock_report.process_running = True
    mock_build_report.return_value = [mock_report]

    dummy_handler.path = "/api/status"
    dummy_handler.do_GET()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["ecosystem"] == "Yasin"
    assert len(response_data["projects"]) == 1
    assert response_data["projects"][0]["name"] == "yasinrelay"


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


@patch("yasinhub.api.service_control_helpers.is_pid_alive", return_value=True)
@patch("yasinhub.api.service_control_helpers.read_pid", return_value=1001)
@patch("yasinhub.api.service_control_helpers.build_report")
@patch("yasinhub.api.server.default_registry")
@patch("yasinhub.api.server.start_service")
def test_api_control_start_via_get(mock_start, mock_registry, mock_build, mock_pid, mock_alive, dummy_handler):
    project = ProjectEntry(name="yasinrelay", start_command="dummy")
    mock_registry.return_value = [project]
    mock_start.return_value = True
    report = MagicMock()
    report.name = "yasinrelay"
    report.health_state = "RUNNING"
    report.last_message = "observed running"
    report.process_running = True
    report.last_run = None
    report.last_success = True
    mock_build.return_value = [report]

    dummy_handler.path = "/api/control/yasinrelay/start"
    dummy_handler.do_GET()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["service"] == "yasinrelay"
    assert response_data["action"] == "start"
    assert response_data["success"] is True
    assert response_data["pid"] == 1001
    assert response_data["status"] == "RUNNING"
    mock_start.assert_called_once_with(project)


@patch("yasinhub.api.service_control_helpers.is_pid_alive", return_value=False)
@patch("yasinhub.api.service_control_helpers.read_pid", return_value=None)
@patch("yasinhub.api.service_control_helpers.build_report")
@patch("yasinhub.api.server.default_registry")
@patch("yasinhub.api.server.stop_service")
def test_api_control_stop_via_post(mock_stop, mock_registry, mock_build, mock_pid, mock_alive, dummy_handler):
    project = ProjectEntry(name="yasinrelay", start_command="dummy")
    mock_registry.return_value = [project]
    mock_stop.return_value = True
    report = MagicMock()
    report.name = "yasinrelay"
    report.health_state = "IDLE"
    report.last_message = "stopped"
    report.process_running = False
    report.last_run = None
    report.last_success = True
    mock_build.return_value = [report]

    dummy_handler.path = "/api/control/yasinrelay/stop"
    dummy_handler.do_POST()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["service"] == "yasinrelay"
    assert response_data["action"] == "stop"
    assert response_data["success"] is True
    assert response_data["status"] == "IDLE"
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


@patch("yasinhub.api.server.parse_qs")
@patch("yasinhub.events_engine.parse_events_from_logs")
@patch("yasinhub.events_engine.filter_events")
def test_api_events_endpoint_with_params(mock_filter, mock_parse, mock_parse_qs, dummy_handler):
    mock_parse_qs.return_value = {
        "service": ["yasinrelay"],
        "limit": ["10"]
    }
    mock_parse.return_value = [{"service": "yasinrelay", "type": "PublishingCompleted"}]
    mock_filter.return_value = [{"service": "yasinrelay", "type": "PublishingCompleted"}]

    dummy_handler.path = "/api/events?service=yasinrelay&limit=10"
    dummy_handler.do_GET()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["count"] == 1
    assert response_data["events"][0]["service"] == "yasinrelay"


@patch("yasinhub.events_engine.cleanup_events")
def test_api_events_cleanup_get(mock_cleanup, dummy_handler):
    mock_cleanup.return_value = True
    dummy_handler.path = "/api/events/cleanup"
    dummy_handler.do_GET()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["success"] is True


@patch("yasinhub.config_manager.get_logs_dir")
def test_api_logs_endpoint(mock_get_logs, tmp_path, dummy_handler):
    mock_get_logs.return_value = tmp_path
    log_file = tmp_path / "testservice.log"
    log_file.write_text(
        "INFO - Starting service\n"
        "WARNING - Disk space low\n"
        "ERROR - Connection failed\n"
        "INFO - Stopping service\n",
        encoding="utf-8"
    )

    dummy_handler.path = "/api/logs/testservice"
    dummy_handler.do_GET()

    assert dummy_handler.response_code == 200
    response_data = json.loads(dummy_handler.wfile.getvalue().decode("utf-8"))
    assert response_data["service"] == "testservice"
    assert response_data["count"] == 4
