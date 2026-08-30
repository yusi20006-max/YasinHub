"""Regression: Slack operational actions route through Unified Control API (#84)."""

from __future__ import annotations

from yasinhub.integrations.slack.commands import CommandDispatcher
from yasinhub.integrations.slack.events import SlackEventType, SlackInboundEvent
from yasinhub.integrations.slack.permissions import IdentityStore, SlackRole, YasinIdentity
from yasinhub.observer.execution_store import get_default_store


def _ops_store():
    return IdentityStore(
        {
            "U_OPS": YasinIdentity("ops1", SlackRole.OPERATOR, "U_OPS"),
        }
    )


def test_cancel_uses_control_api_success_path():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec-slack-ctrl-1")
    store.start(snap.execution_id)
    d = CommandDispatcher(_ops_store())
    result = d.dispatch(
        SlackInboundEvent(
            event_type=SlackEventType.SLASH_COMMAND,
            command="/cancel",
            text="exec-slack-ctrl-1",
            slack_user_id="U_OPS",
            request_id="req-cancel-1",
        )
    )
    assert result.ok is True
    assert "Cancel" in result.text or "cancel" in result.text.lower()


def test_retry_uses_control_api():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec-slack-retry-1")
    store.start(snap.execution_id)
    store.fail(snap.execution_id, "boom")
    d = CommandDispatcher(_ops_store())
    result = d.dispatch(
        SlackInboundEvent(
            event_type=SlackEventType.SLASH_COMMAND,
            command="/retry",
            text="exec-slack-retry-1",
            slack_user_id="U_OPS",
            request_id="req-retry-1",
        )
    )
    assert result.ok is True
    assert "Retry" in result.text or "retry" in result.text.lower()


def test_commands_module_imports_control_api():
    import yasinhub.integrations.slack.commands as cmd
    src = open(cmd.__file__).read()
    assert "get_control_api" in src
    assert "ControlRequest" in src


def test_interactive_module_imports_control_api():
    import yasinhub.integrations.slack.interactive as ix
    src = open(ix.__file__).read()
    assert "get_control_api" in src
    assert "ControlRequest" in src
