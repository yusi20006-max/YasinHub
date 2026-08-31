"""Failure-follow-up parsing used by channel session continuity."""

from yasinhub.interface.intents import IntentKind
from yasinhub.interface.parser import parse_intent


def test_why_did_it_fail_is_failure_investigation_follow_up():
    intent = parse_intent("why did it fail")
    assert intent.kind is IntentKind.INVESTIGATE_FAILURE
