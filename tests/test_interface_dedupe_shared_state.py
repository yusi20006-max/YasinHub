from yasinhub.integrations.slack.interactive import InteractionDeduper


class FakeSharedState:
    def __init__(self):
        self.owners = {}

    def try_acquire(self, namespace, key, owner, *, ttl_seconds):
        if (namespace, key) in self.owners:
            return False
        self.owners[(namespace, key)] = (owner, ttl_seconds)
        return True


def test_interaction_dedupe_uses_shared_state_atomically():
    store = FakeSharedState()
    first = InteractionDeduper(store=store, ttl_seconds=300)
    second = InteractionDeduper(store=store, ttl_seconds=300)

    assert first.already_processed("trigger-123") is False
    assert second.already_processed("trigger-123") is True
    assert ("yasin_slack_interaction_dedupe", "trigger-123") in store.owners
