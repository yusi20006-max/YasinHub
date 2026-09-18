"""Focused #190 mutation-surface regression tests."""

from __future__ import annotations

import pytest

from yasinhub.auth import AuthMode, Role, YasinPrincipal, reset_auth_for_tests
from yasinhub.execution.policies import PolicyEngine


@pytest.fixture(autouse=True)
def _auth():
    reset_auth_for_tests(
        mode=AuthMode.PRODUCTION,
        tokens={
            "operator-token": YasinPrincipal("operator-user", Role.OPERATOR, auth_method="bearer_token"),
            "viewer-token": YasinPrincipal("viewer-user", Role.VIEWER, auth_method="bearer_token"),
        },
    )
    yield
    reset_auth_for_tests()


def test_events_cleanup_is_not_a_viewer_mutation():
    engine = PolicyEngine()
    assert not engine.evaluate(action="events_cleanup", role=Role.VIEWER).allowed
    assert engine.evaluate(action="events_cleanup", role=Role.OPERATOR).allowed
