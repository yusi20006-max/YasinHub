"""Focused #191 cross-channel identity and role enforcement tests."""

from __future__ import annotations

from yasinhub.auth.models import AuthMode, Role, YasinPrincipal
from yasinhub.auth import reset_auth_for_tests
from yasinhub.integrations.slack.permissions import SlackRole, YasinIdentity, IdentityStore
from yasinhub.integrations.slack.commands import CommandDispatcher
from yasinhub.integrations.slack.events import SlackInboundEvent, SlackEventType


def test_slack_control_carries_canonical_role():
    from yasinhub.execution.control_api import ControlRequest, get_control_api
    captured = []
    api = get_control_api()
    original = api.handle
    api.handle = lambda req: captured.append(req) or type("R", (), {"success": True, "execution": None, "error": None})()
    try:
        dispatcher = CommandDispatcher(
            IdentityStore({"U123": YasinIdentity("alice", SlackRole.OPERATOR, "U123")})
        )
        result = dispatcher.dispatch(
            SlackInboundEvent(
                event_type=SlackEventType.SLASH_COMMAND,
                command="/cancel",
                text="exec-1",
                slack_user_id="U123",
            )
        )
        assert result.ok
        assert captured and captured[-1].role == Role.OPERATOR
    finally:
        api.handle = original


def test_unmapped_slack_control_is_rejected_before_control_api(monkeypatch):
    from yasinhub.interface.engine import YasinInterface
    from yasinhub.interface.session import SessionStore
    from yasinhub.interface.intents import Intent, IntentKind
    from yasinhub.storage.shared_state import MemorySharedState
    from yasinhub.integrations.slack.permissions import IdentityStore

    reset_auth_for_tests(mode=AuthMode.PRODUCTION, tokens={})
    iface = YasinInterface(session_store=SessionStore(MemorySharedState()))
    session = iface.sessions.create(
        channel="slack", source="slack", thread_id="t191",
        slack_user_id="U-NOT-MAPPED", yasin_user_id="U-NOT-MAPPED",
    )
    intent = Intent(kind=IntentKind.CONTROL_REQUEST, raw_text="cancel execution exec-1", execution_id="exec-1", control_operation="cancel")
    resp = iface._handle_control_request(intent, session, actor="U-NOT-MAPPED", source="slack")
    assert resp.success is False
    assert resp.error == "unmapped_slack_user"
