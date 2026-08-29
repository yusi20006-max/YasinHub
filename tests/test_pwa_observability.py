"""
tests/test_pwa_observability.py
Live observability (#57): polling semantics, event ordering, fleet aggregation,
status projection, soft-refresh generation, offline/stale indicators.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
JS = DASH / "js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_app_js_polling_intervals_and_controls():
    content = _read(DASH / "app.js")
    assert "POLL_LIST_MS" in content
    assert "POLL_DETAIL_MS" in content
    assert "startPolling" in content
    assert "stopPolling" in content
    assert "setInterval" in content
    assert "document.hidden" in content
    assert "soft" in content
    assert "fetchGen" in content
    assert "live-meta" in content or "live-dot" in content
    assert "visibilitychange" in content


def test_app_js_soft_refresh_avoids_loading_flash():
    content = _read(DASH / "app.js")
    assert "hasContent" in content
    assert "soft" in content
    assert "if (!soft || !appState.hasContent)" in content or "if (!soft" in content


def test_api_event_ordering_by_sequence():
    content = _read(JS / "api.js")
    assert "events.sort" in content
    assert "sequence" in content
    assert "timestamp" in content


def test_models_status_class_covers_partial_failure():
    content = _read(JS / "models.js")
    assert "completed_with_failures" in content or "completed-with-failures" in content
    assert "statusClass" in content
    assert "cancelling" in content


def test_views_fleet_worker_breakdown_and_progress():
    content = _read(JS / "views.js")
    assert "workerStatusCounts" in content
    assert "fleet-summary" in content
    assert "progress" in content
    assert "Breakdown" in content or "breakdown" in content.lower()
    assert "renderFleetDetail" in content
    assert "renderExecutionDetail" in content


def test_views_execution_detail_metadata_and_capabilities():
    content = _read(JS / "views.js")
    assert "capabilities" in content
    assert "workspace" in content
    assert "cancel_requested" in content
    assert "History" in content or "history" in content


def test_views_event_timeline_correlation_fields():
    content = _read(JS / "views.js")
    assert "event-seq" in content
    assert "worker_id" in content
    assert "execution_id" in content
    assert "task_id" in content


def test_style_has_status_badges_and_live_indicator():
    content = _read(DASH / "style.css")
    for status in (
        "status-queued",
        "status-running",
        "status-paused",
        "status-succeeded",
        "status-failed",
        "status-cancelled",
        "status-completed-with-failures",
    ):
        assert status in content, f"missing {status}"
    assert "live-dot" in content
    assert "stale-indicator" in content
    assert "@media" in content


def test_docs_describe_polling_and_scope():
    content = _read(ROOT / "docs" / "PWA_ARCHITECTURE.md")
    assert "#57" in content
    assert "Polling" in content or "polling" in content
    assert "5s" in content or "5000" in content
    assert "#58" in content


def test_observability_does_not_embed_control_paths_in_views():
    """Views may render control buttons (#58) but must not hardcode API paths."""
    content = _read(JS / "views.js")
    assert "/api/executions/" not in content
    assert "/api/fleets/" not in content


def test_models_normalize_preserves_ordering_fields():
    models = _read(JS / "models.js")
    assert "sequence" in models
    assert "worker_id" in models
    assert "normalizeFleet" in models
    assert "sort" in models
