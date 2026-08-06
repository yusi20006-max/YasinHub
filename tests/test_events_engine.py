"""
tests/test_events_engine.py
مجموعه تست‌ها برای موتور رویدادها (events_engine) و اندپوینت‌های مربوطه.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from yasinhub.events_engine import (
    extract_timestamp,
    filter_events,
    parse_events_from_logs,
    cleanup_events,
    SEVERITY_MAP
)


def test_extract_timestamp():
    # ISO-like format
    assert extract_timestamp("2026-07-26T10:00:00+00:00 - ERROR - ...") == "2026-07-26T10:00:00+00:00"
    assert extract_timestamp("2026-07-26 10:00:00,123 [INFO]") == "2026-07-26 10:00:00"
    # Slash format
    assert extract_timestamp("2026/07/26 10:00:00 - AIProcessingCompleted") == "2026/07/26 10:00:00"
    # No timestamp
    assert extract_timestamp("ProcessingStarted without timestamp") is None


def test_severity_mapping():
    assert SEVERITY_MAP["ERROR"] == "ERROR"
    assert SEVERITY_MAP["DuplicateDetected"] == "WARNING"
    assert SEVERITY_MAP["PublishingCompleted"] == "SUCCESS"
    assert SEVERITY_MAP["ProcessingStarted"] == "INFO"


def test_filter_events():
    events = [
        {"service": "yasinrelay", "type": "PublishingCompleted", "severity": "SUCCESS", "timestamp": "2026-07-26T10:00:00", "message": "msg1"},
        {"service": "yasinrelay", "type": "ERROR", "severity": "ERROR", "timestamp": "2026-07-26T10:01:00", "message": "msg2"},
        {"service": "eitaa_news_v2", "type": "DuplicateDetected", "severity": "WARNING", "timestamp": "2026-07-26T10:02:00", "message": "msg3"},
    ]

    # Filter by service
    f = filter_events(events, service="yasinrelay")
    assert len(f) == 2
    assert f[0]["message"] == "msg1"

    # Filter by type
    f = filter_events(events, event_type="ERROR")
    assert len(f) == 1
    assert f[0]["message"] == "msg2"

    # Filter by severity
    f = filter_events(events, severity="WARNING")
    assert len(f) == 1
    assert f[0]["message"] == "msg3"

    # Filter by level (alias of severity)
    f = filter_events(events, level="ERROR")
    assert len(f) == 1
    assert f[0]["message"] == "msg2"

    # Limit
    f = filter_events(events, limit=2)
    assert len(f) == 2


@patch("yasinhub.events_engine.get_logs_dir")
def test_parse_events_from_logs(mock_get_logs, tmp_path):
    mock_get_logs.return_value = tmp_path

    # Create mock log file
    log1 = tmp_path / "yasinrelay.log"
    log1.write_text(
        "2026-07-26T10:00:00 - ERROR - failed to connect\n"
        "2026-07-26T10:05:00 - PublishingCompleted - 12 posts\n",
        encoding="utf-8"
    )

    log2 = tmp_path / "eitaa_news_v2.log"
    log2.write_text(
        "2026-07-26T10:02:00 - DuplicateDetected - already exists\n",
        encoding="utf-8"
    )

    events = parse_events_from_logs()

    # 3 matching events in total
    assert len(events) == 3

    # Must be sorted by timestamp descending
    assert events[0]["type"] == "PublishingCompleted"
    assert events[0]["service"] == "yasinrelay"
    assert events[0]["severity"] == "SUCCESS"
    assert events[0]["timestamp"] == "2026-07-26T10:05:00"

    assert events[1]["type"] == "DuplicateDetected"
    assert events[1]["service"] == "eitaa_news_v2"
    assert events[1]["severity"] == "WARNING"

    assert events[2]["type"] == "ERROR"


@patch("yasinhub.events_engine.get_logs_dir")
def test_cleanup_events(mock_get_logs, tmp_path):
    mock_get_logs.return_value = tmp_path
    log_file = tmp_path / "service.log"
    log_file.write_text("some logs here", encoding="utf-8")

    assert cleanup_events() is True
    # The file should be truncated to 0 bytes
    assert log_file.exists()
    assert log_file.read_text(encoding="utf-8") == ""
