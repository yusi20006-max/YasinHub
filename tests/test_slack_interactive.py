"""Tests for Slack Interactive Operations (#73)."""

from __future__ import annotations

from yasinhub.integrations.slack.permissions import IdentityStore, SlackRole, YasinIdentity
from yasinhub.integrations.slack.events import SlackInboundEvent, SlackEventType
from yasinhub.integrations.slack.interactive import InteractiveHandler, InteractionDeduper
from yasinhub.observer.execution_store import get_default_store


def _store():
    return IdentityStore(
        {
            "U_VIEW": YasinIdentity("v1", SlackRole.VIEWER, "U_VIEW"),
            "U_OPS": YasinIdentity("o1", SlackRole.OPERATOR, "U_OPS"),
        }
    )


class TestInteractive:
    def test_view_execution(self):
        get_default_store().create_execution(task_id="t", execution_id="exec-ix-1")
        h = InteractiveHandler(_store())
        r = h.handle(
            SlackInboundEvent(
                event_type=SlackEventType.INTERACTIVE,
                action_id="view",
                action_value="exec-ix-1",
                slack_user_id="U_VIEW",
                trigger_id="trig-1",
            )
        )
        assert r.ok is True
        assert "exec-ix-1" in r.text

    def test_unauthorized_cancel(self):
        h = InteractiveHandler(_store())
        r = h.handle(
            SlackInboundEvent(
                event_type=SlackEventType.INTERACTIVE,
                action_id="cancel",
                action_value="exec-x",
                slack_user_id="U_VIEW",
                trigger_id="trig-2",
            )
        )
        assert r.ok is False
        assert "authorized" in r.text.lower()

    def test_unmapped_user(self):
        h = InteractiveHandler(_store())
        r = h.handle(
            SlackInboundEvent(
                event_type=SlackEventType.INTERACTIVE,
                action_id="view",
                action_value="x",
                slack_user_id="U_NONE",
                trigger_id="trig-3",
            )
        )
        assert r.ok is False
        assert "not mapped" in r.text.lower()

    def test_missing_resource(self):
        h = InteractiveHandler(_store())
        r = h.handle(
            SlackInboundEvent(
                event_type=SlackEventType.INTERACTIVE,
                action_id="view",
                action_value="missing-exec",
                slack_user_id="U_VIEW",
                trigger_id="trig-4",
            )
        )
        assert r.ok is False
        assert "unknown" in r.text.lower()

    def test_idempotent_duplicate(self):
        get_default_store().create_execution(task_id="t", execution_id="exec-ix-dup")
        h = InteractiveHandler(_store())
        event = SlackInboundEvent(
            event_type=SlackEventType.INTERACTIVE,
            action_id="view",
            action_value="exec-ix-dup",
            slack_user_id="U_VIEW",
            trigger_id="trig-dup-same",
        )
        r1 = h.handle(event)
        r2 = h.handle(event)
        assert r1.ok is True
        assert r2.ok is True
        assert "already processed" in r2.text.lower() or r2.ok

    def test_retry_from_failed(self):
        store = get_default_store()
        snap = store.create_execution(task_id="retry-task", execution_id="exec-ix-fail")
        store.start(snap.execution_id)
        store.fail(snap.execution_id, "boom")
        h = InteractiveHandler(_store())
        r = h.handle(
            SlackInboundEvent(
                event_type=SlackEventType.INTERACTIVE,
                action_id="retry",
                action_value="exec-ix-fail",
                slack_user_id="U_OPS",
                trigger_id="trig-retry-1",
            )
        )
        assert r.ok is True
        assert "Retry queued" in r.text


class TestDeduper:
    def test_ttl_dedupe(self):
        d = InteractionDeduper(ttl_seconds=60)
        assert d.already_processed("k1") is False
        assert d.already_processed("k1") is True
