"""Regression: Slack ops via Unified Control API (#84)."""
from yasinhub.integrations.slack.commands import CommandDispatcher
from yasinhub.integrations.slack.events import SlackEventType, SlackInboundEvent
from yasinhub.integrations.slack.permissions import IdentityStore, SlackRole, YasinIdentity
from yasinhub.observer.execution_store import get_default_store

def _ops():
    return IdentityStore({"U_OPS": YasinIdentity("ops1", SlackRole.OPERATOR, "U_OPS")})

def test_commands_imports_control_api():
    import yasinhub.integrations.slack.commands as c
    assert "get_control_api" in open(c.__file__).read()

def test_interactive_imports_control_api():
    import yasinhub.integrations.slack.interactive as i
    assert "get_control_api" in open(i.__file__).read()

def test_cancel_via_control_api():
    store = get_default_store()
    snap = store.create_execution(task_id="t", execution_id="exec-sc-1")
    store.start(snap.execution_id)
    r = CommandDispatcher(_ops()).dispatch(SlackInboundEvent(
        event_type=SlackEventType.SLASH_COMMAND, command="/cancel", text="exec-sc-1",
        slack_user_id="U_OPS", request_id="r1"))
    assert r.ok
