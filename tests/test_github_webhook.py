"""Tests for GitHub webhook bridge (#66)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os

from yasinhub.integrations.github.webhook import handle_github_webhook, verify_github_signature


def test_ping():
    body = json.dumps({"zen": "Keep it logically awesome."}).encode()
    status, result = handle_github_webhook(body, headers={"X-GitHub-Event": "ping"})
    assert status == 200
    assert result.get("message") == "pong"


def test_invalid_signature_rejected():
    os.environ["YASINHUB_GITHUB_WEBHOOK_SECRET"] = "testsecret"
    try:
        body = json.dumps({"action": "opened", "pull_request": {"number": 1}}).encode()
        status, result = handle_github_webhook(
            body, headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=bad"}
        )
        assert status == 401
    finally:
        del os.environ["YASINHUB_GITHUB_WEBHOOK_SECRET"]


def test_valid_signature_accepted():
    secret = "testsecret"
    os.environ["YASINHUB_GITHUB_WEBHOOK_SECRET"] = secret
    try:
        body = json.dumps(
            {
                "action": "opened",
                "pull_request": {"number": 7, "state": "open", "merged": False},
                "repository": {"full_name": "o/r"},
            }
        ).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        status, result = handle_github_webhook(
            body, headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": sig}
        )
        assert status == 200
        assert result["success"] is True
    finally:
        del os.environ["YASINHUB_GITHUB_WEBHOOK_SECRET"]


def test_verify_helper():
    body = b"hello"
    secret = "s"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_github_signature(body, sig, secret) is True
    assert verify_github_signature(body, "sha256=xx", secret) is False
