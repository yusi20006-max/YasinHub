"""Tests for production monday integration (#79)."""

from __future__ import annotations

from unittest import mock

import pytest

from yasinhub.integrations.monday.client import MondayClient, MondayClientError
from yasinhub.integrations.monday.config import MondayConfig, MondayConfigError, get_monday_config
from yasinhub.integrations.monday.sync import MondaySyncService
from yasinhub.observer.execution_store import get_default_store


def test_config_valid_when_disabled():
    cfg = MondayConfig(enabled=False)
    ok, issues = cfg.validate()
    assert ok is True
    assert issues == []


def test_config_invalid_live_without_token():
    cfg = MondayConfig(enabled=True, live_writes_enabled=True, api_token=None, status_column_id="st")
    ok, issues = cfg.validate()
    assert ok is False
    assert any("token" in i for i in issues)


def test_config_invalid_live_without_status_column():
    cfg = MondayConfig(
        enabled=True, live_writes_enabled=True, api_token="tok", status_column_id=None
    )
    ok, issues = cfg.validate()
    assert ok is False
    assert any("status_column" in i for i in issues)


def test_live_ready():
    cfg = MondayConfig(
        enabled=True,
        live_writes_enabled=True,
        api_token="tok",
        status_column_id="status",
    )
    assert cfg.is_live_ready() is True


def test_safe_dict_hides_secrets():
    cfg = MondayConfig(api_token="super-secret-token", signing_secret="sig-secret")
    d = cfg.as_safe_dict()
    assert d["has_api_token"] is True
    assert "super-secret-token" not in str(d)
    assert "sig-secret" not in str(d)


def test_require_valid_for_live_raises():
    cfg = MondayConfig(live_writes_enabled=True, api_token=None)
    with pytest.raises(MondayConfigError):
        cfg.require_valid_for_live()


def test_client_missing_token():
    client = MondayClient(MondayConfig(api_token=None))
    with pytest.raises(MondayClientError):
        client.execute("{ me { id } }")


def test_client_retry_on_retriable_error():
    cfg = MondayConfig(api_token="tok", max_retries=2, retry_backoff_seconds=0)
    client = MondayClient(cfg)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=30):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("timeout")

        class Resp:
            def read(self):
                return b'{"data": {"me": {"id": "1"}}}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return Resp()

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        data = client.execute("{ me { id } }")
    assert data["me"]["id"] == "1"
    assert calls["n"] == 3


def test_health_check_dry_run():
    client = MondayClient(MondayConfig(api_token=None))
    h = client.health_check()
    assert h["ok"] is False
    assert h["mode"] == "dry-run"


def test_sync_dry_run_without_live():
    store = get_default_store()
    store.clear()
    snap = store.create_execution(
        task_id="t",
        metadata={"source": "monday", "board_id": "b", "item_id": "i"},
    )
    svc = MondaySyncService(MondayConfig(api_token=None))
    result = svc.push_execution_to_monday(snap.execution_id)
    assert result["success"] is True
    assert result.get("dry_run") is True
    store.clear()


def test_get_monday_config_from_env(monkeypatch):
    monkeypatch.setenv("YASINHUB_MONDAY_API_TOKEN", "t")
    monkeypatch.setenv("YASINHUB_MONDAY_LIVE_WRITES", "true")
    monkeypatch.setenv("YASINHUB_MONDAY_STATUS_COLUMN", "status_col")
    cfg = get_monday_config()
    assert cfg.api_token == "t"
    assert cfg.live_writes_enabled is True
    assert cfg.is_live_ready() is True
