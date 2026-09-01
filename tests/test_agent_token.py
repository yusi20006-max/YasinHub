"""Canonical shared token contract tests."""

from __future__ import annotations

from pathlib import Path

from yasinhub.agent_token import (
    ensure_token_file,
    resolve_agent_service_token,
    token_path,
)


def test_token_path_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = token_path(home=tmp_path)
    assert p == tmp_path / ".yasinhub" / "yasin-agent.token"


def test_file_wins_over_stale_env(tmp_path):
    path = token_path(home=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("file-token-canonical\n", encoding="utf-8")
    path.chmod(0o600)

    env = {
        "YASIN_AGENT_SERVICE_TOKEN": "stale-env-token-should-lose",
        "YASINHUB_AGENT_SERVICE_TOKEN": "also-stale",
    }
    got = resolve_agent_service_token(env=env, home=tmp_path, persist=False)
    assert got == "file-token-canonical"


def test_env_used_and_persisted_when_file_missing(tmp_path):
    env = {"YASIN_AGENT_SERVICE_TOKEN": "from-env-only"}
    got = resolve_agent_service_token(env=env, home=tmp_path, persist=True)
    assert got == "from-env-only"
    path = token_path(home=tmp_path)
    assert path.is_file()
    assert path.read_text(encoding="utf-8").strip() == "from-env-only"
    assert path.stat().st_mode & 0o777 == 0o600


def test_generate_when_nothing_set(tmp_path):
    got = resolve_agent_service_token(env={}, home=tmp_path, persist=True)
    assert isinstance(got, str) and len(got) >= 16
    path = token_path(home=tmp_path)
    assert path.read_text(encoding="utf-8").strip() == got
    assert path.stat().st_mode & 0o777 == 0o600


def test_ensure_token_file(tmp_path):
    p = ensure_token_file(home=tmp_path)
    assert p.is_file()
    assert p.stat().st_mode & 0o777 == 0o600
