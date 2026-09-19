"""Final production-closure regression anchors for the #194 audit."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_closure_documents_authoritative_security_boundaries():
    doc = (ROOT / "docs" / "PRODUCTION_CLOSURE_194.md").read_text(encoding="utf-8")
    required = (
        "HTTP production authentication",
        "PolicyEngine",
        "Slack ingress retains HMAC verification",
        "Confirmation and idempotency",
        "Production persistence is durable-by-default",
        "Audit append failures are observable",
        "Issue #203",
        "CI workflow remains the complete",
    )
    for marker in required:
        assert marker in doc


def test_production_ci_matrix_is_not_reduced():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for version in ("3.9", "3.10", "3.11", "3.12", "3.13", "3.14-dev"):
        assert version in ci
    assert "python -m pytest -q" in ci
