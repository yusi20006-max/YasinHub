"""Tests for Slack Commands and Authorization (#71)."""

from __future__ import annotations

import pytest

from yasinhub.integrations.slack.permissions import (
    AuthorizationError,
    IdentityStore,
    SlackRole,
    YasinIdentity,
    authorize_command,
    load_identity_map_from_env,
)
from yasinhub.integrations.slack.commands import CommandDispatcher, parse_command
from yasinhub.integrations.slack.events import SlackInboundEvent, SlackEventType
from yasinhub.observer.execution_store import get_default_store


class TestParseCommand:
    def test_slash_status(self):
        p = parse_command("/status", "")
        assert p is not None
        assert p.name == "status"
        assert p.args == []

    def test_execution_with_id(self):
        p = parse_command("/execution", "exec_123")
        assert p is not None
        assert p.name == "execution"
        assert p.args == ["exec_123"]

    def test_run_with_task(self):
        p = parse_command("/run", "build release")
        assert p is not None
        assert p.name == "run"
        assert p.args == ["build", "release"]

    def test_malformed_empty(self):
        assert parse_command(None, "") is None


class TestPermissions:
    def test_viewer_can_status(self):
        ident = YasinIdentity("alice", SlackRole.VIEWER, "U1")
        authorize_command(ident, "status")

    def test_viewer_cannot_run(self):
        ident = YasinIdentity("alice", SlackRole.VIEWER, "U1")
        with pytest.raises(AuthorizationError) as exc:
            authorize_command(ident, "run")
        assert exc.value.reason == "forbidden"

    def test_operator_can_cancel(self):
        ident = YasinIdentity("bob", SlackRole.OPERATOR, "U2")
        authorize_command(ident, "cancel")

    def test_unmapped_user(self):
        with pytest.raises(AuthorizationError) as exc:
            authorize_command(None, "status")
        assert exc.value.reason == "unmapped_slack_user"

    def test_identity_map_from_env(self, monkeypatch):
        monkeypatch.setenv("YASIN_SLACK_IDENTITY_MAP", "U10:admin:alice,U20:viewer")
        m = load_identity_map_from_env()
        assert m["U10"].role == SlackRole.ADMIN
        assert m["U10"].yasin_user_id == "alice"
        assert m["U20"].role == SlackRole.VIEWER
        assert m["U20"].yasin_user_id == "U20"


def _store() -> IdentityStore:
    return IdentityStore(
        {
            "U_VIEW": YasinIdentity("viewer1", SlackRole.VIEWER, "U_VIEW"),
            "U_OPS": YasinIdentity("ops1", SlackRole.OPERATOR, "U_OPS"),
            "U_ADMIN": YasinIdentity("admin1", SlackRole.ADMIN, "U_ADMIN"),
        }
    )


class TestCommandDispatcher:
    def test_help_ok(self):
        d = CommandDispatcher(_store())
        result = d.dispatch(
            SlackInboundEvent(
                event_type=SlackEventType.SLASH_COMMAND,
                command="/help",
                slack_user_id="U_VIEW",
            )
        )
        assert result.ok is True
        assert "help" in result.text.lower() or "status" in result.text.lower()

    def test_unmapped_rejected(self):
        d = CommandDispatcher(_store())
        result = d.dispatch(
            SlackInboundEvent(
                event_type=SlackEventType.SLASH_COMMAND,
                command="/status",
                slack_user_id="U_UNKNOWN",
            )
        )
        assert result.ok is False
        assert "not mapped" in result.text.lower()

    def test_viewer_run_forbidden(self):
        d = CommandDispatcher(_store())
        result = d.dispatch(
            SlackInboundEvent(
                event_type=SlackEventType.SLASH_COMMAND,
                command="/run",
                text="do something",
                slack_user_id="U_VIEW",
            )
        )
        assert result.ok is False
        assert "not authorized" in result.text.lower()

    def test_operator_run(self):
        d = CommandDispatcher(_store())
        result = d.dispatch(
            SlackInboundEvent(
                event_type=SlackEventType.SLASH_COMMAND,
                command="/run",
                text="demo-task",
                slack_user_id="U_OPS",
            )
        )
        assert result.ok is True
        assert result.ok and ("queued" in result.text.lower() or "started" in result.text.lower() or "Execution" in result.text)

    def test_execution_missing(self):
        d = CommandDispatcher(_store())
        result = d.dispatch(
            SlackInboundEvent(
                event_type=SlackEventType.SLASH_COMMAND,
                command="/execution",
                text="does-not-exist-xyz",
                slack_user_id="U_VIEW",
            )
        )
        assert result.ok is False
        assert "unknown" in result.text.lower()

    def test_execution_found(self):
        store = get_default_store()
        store.create_execution(task_id="t1", execution_id="exec-test-cmd-71")
        d = CommandDispatcher(_store())
        result = d.dispatch(
            SlackInboundEvent(
                event_type=SlackEventType.SLASH_COMMAND,
                command="/execution",
                text="exec-test-cmd-71",
                slack_user_id="U_VIEW",
            )
        )
        assert result.ok is True
        assert "exec-test-cmd-71" in result.text

    def test_unknown_command(self):
        d = CommandDispatcher(_store())
        result = d.dispatch(
            SlackInboundEvent(
                event_type=SlackEventType.SLASH_COMMAND,
                command="/shell",
                text="rm -rf /",
                slack_user_id="U_ADMIN",
            )
        )
        assert result.ok is False
        assert "unknown" in result.text.lower()

    def test_status_command(self):
        d = CommandDispatcher(_store())
        result = d.dispatch(
            SlackInboundEvent(
                event_type=SlackEventType.SLASH_COMMAND,
                command="/status",
                slack_user_id="U_VIEW",
            )
        )
        assert result.ok is True
