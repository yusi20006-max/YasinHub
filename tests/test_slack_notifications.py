"""Tests for Slack Execution Notifications and Threads (#72)."""

from __future__ import annotations

from yasinhub.integrations.slack.config import SlackConfig
from yasinhub.integrations.slack.client import NullSlackClient, SlackMessageResult
from yasinhub.integrations.slack.adapter import SlackAdapter
from yasinhub.integrations.slack.notifications import SlackNotifier


class RecordingClient(NullSlackClient):
    def __init__(self):
        self.posts = []

    def post_message(self, channel, text, *, thread_ts=None, blocks=None, metadata=None):
        self.posts.append({"channel": channel, "text": text, "thread_ts": thread_ts})
        return SlackMessageResult(ok=True, channel=channel, ts=f"ts-{len(self.posts)}")


def _adapter(client):
    cfg = SlackConfig(
        enabled=True,
        bot_token="xoxb-t",
        signing_secret="s",
        feature_notifications=True,
        agent_channel="#yasin-agent",
        alerts_channel="#yasin-alerts",
    )
    return SlackAdapter(config=cfg, client=client)


class TestSlackNotifier:
    def test_filters_unknown_events(self):
        client = RecordingClient()
        n = SlackNotifier(adapter=_adapter(client), config=_adapter(client).config)
        r = n.notify_execution_event("debug.log", "exec_1")
        assert r.ok is False
        assert r.error == "filtered"
        assert client.posts == []

    def test_started_goes_to_agent_channel(self):
        client = RecordingClient()
        n = SlackNotifier(adapter=_adapter(client), config=_adapter(client).config)
        r = n.notify_execution_event("execution.started", "exec_1", status="running", task_id="t1")
        assert r.ok is True
        assert client.posts[0]["channel"] == "#yasin-agent"
        assert "exec_1" in client.posts[0]["text"]

    def test_failed_goes_to_alerts(self):
        client = RecordingClient()
        n = SlackNotifier(adapter=_adapter(client), config=_adapter(client).config)
        r = n.notify_execution_event("execution.failed", "exec_2", status="failed", error="boom")
        assert r.ok is True
        assert client.posts[0]["channel"] == "#yasin-alerts"

    def test_thread_correlation(self):
        client = RecordingClient()
        n = SlackNotifier(adapter=_adapter(client), config=_adapter(client).config)
        n.notify_execution_event("execution.started", "exec_t", status="running")
        n.notify_execution_event("execution.completed", "exec_t", status="succeeded")
        assert client.posts[0]["thread_ts"] is None
        assert client.posts[1]["thread_ts"] == "ts-1"

    def test_disabled_is_safe(self):
        cfg = SlackConfig(enabled=False)
        n = SlackNotifier(adapter=SlackAdapter(config=cfg, client=NullSlackClient()), config=cfg)
        r = n.notify_execution_event("execution.started", "x")
        assert r.ok is False

    def test_client_failure_does_not_raise(self):
        class FailClient(NullSlackClient):
            def post_message(self, *a, **k):
                return SlackMessageResult(ok=False, error="slack_api_error")

        cfg = SlackConfig(enabled=True, bot_token="t", signing_secret="s", feature_notifications=True)
        n = SlackNotifier(adapter=SlackAdapter(config=cfg, client=FailClient()), config=cfg)
        r = n.notify_execution_event("execution.started", "e1")
        assert r.ok is False
        assert n.failure_count >= 1
