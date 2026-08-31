"""Fail-closed behavior when Slack interactive shared state is unavailable."""

from __future__ import annotations

from yasinhub.integrations.slack.interactive import InteractionDeduper


class FailingSharedState:
    def try_acquire(self, *args, **kwargs):
        raise OSError("shared state unavailable")


def test_interaction_deduper_fails_closed_when_shared_state_unavailable():
    deduper = InteractionDeduper(store=FailingSharedState())

    assert deduper.already_processed("interactive-1") is True
    assert deduper.last_error is True
