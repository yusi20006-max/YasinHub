"""
tests/test_pwa_foundation.py
PWA foundation (#56): shell, routing, models, API client mapping,
loading/empty/error states, responsive-safe structure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.test_api_server import DummyHandler, MockRequest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
JS = DASHBOARD / "js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Static shell & module serving
# ---------------------------------------------------------------------------

def test_dashboard_index_serves_spa_shell():
    req = MockRequest()
    handler = DummyHandler(req, ("127.0.0.1", 1), MagicMock())
    handler.path = "/dashboard/index.html"
    handler.do_GET()
    assert handler.response_code == 200
    body = handler.wfile.getvalue().decode("utf-8")
    assert 'id="content"' in body
    assert 'id="sidebar"' in body
    assert 'data-nav="overview"' in body
    assert 'data-nav="executions"' in body
    assert 'data-nav="fleets"' in body
    assert 'data-nav="events"' in body
    assert 'type="module" src="app.js"' in body
    assert "connection-status" in body
    assert "stale-indicator" in body


def test_js_modules_served():
    for name in ("models.js", "api.js", "router.js", "views.js"):
        req = MockRequest()
        handler = DummyHandler(req, ("127.0.0.1", 1), MagicMock())
        handler.path = f"/dashboard/js/{name}"
        handler.do_GET()
        assert handler.response_code == 200, name
        ct = handler.response_headers.get("Content-Type", "")
        assert "javascript" in ct or "ecmascript" in ct or "text/" in ct
        body = handler.wfile.getvalue().decode("utf-8")
        assert len(body) > 50


# ---------------------------------------------------------------------------
# Models (normalize helpers)
# ---------------------------------------------------------------------------

def test_models_js_exports_and_statuses():
    content = _read(JS / "models.js")
    assert "export function normalizeExecution" in content
    assert "export function normalizeEvent" in content
    assert "export function normalizeFleet" in content
    assert "export function statusClass" in content
    for status in ("queued", "running", "paused", "succeeded", "failed", "cancelled"):
        assert status in content


def test_models_normalize_execution_shape():
    """Static analysis: normalizeExecution returns required display fields."""
    content = _read(JS / "models.js")
    for field in (
        "execution_id",
        "task_id",
        "session_id",
        "status",
        "capabilities",
        "created_at",
        "started_at",
        "finished_at",
        "error",
        "metadata",
        "history",
        "cancel_requested",
    ):
        assert field in content


def test_models_normalize_fleet_and_event():
    content = _read(JS / "models.js")
    assert "workers" in content
    assert "parent" in content or "task_id" in content
    assert "event_id" in content
    assert "sequence" in content
    assert "event_type" in content


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def test_router_hash_routes():
    content = _read(JS / "router.js")
    assert "export function parseRoute" in content
    assert "export function navigate" in content or "navigate" in content
    for route in ("overview", "executions", "execution-detail", "fleets", "fleet-detail", "events"):
        assert route in content
    assert "hashchange" in content or "onRouteChange" in content


# ---------------------------------------------------------------------------
# API client mapping to existing endpoints
# ---------------------------------------------------------------------------

def test_api_client_maps_observer_endpoints():
    content = _read(JS / "api.js")
    assert "export async function getJSON" in content or "function getJSON" in content
    for path_fragment in (
        "/api/executions",
        "/api/execution-events",
        "/api/fleets",
    ):
        assert path_fragment in content
    assert "normalizeExecution" in content
    assert "normalizeEvent" in content
    assert "normalizeFleet" in content
    # Offline / error shape
    assert "offline" in content
    assert "ok" in content


# ---------------------------------------------------------------------------
# Views: loading / empty / error / content
# ---------------------------------------------------------------------------

def test_views_loading_empty_error_states():
    content = _read(JS / "views.js")
    assert "renderLoading" in content or "state-loading" in content
    assert "renderEmpty" in content or "state-empty" in content
    assert "renderError" in content or "state-error" in content
    for view in (
        "renderOverview",
        "renderExecutionsList",
        "renderExecutionDetail",
        "renderFleetsList",
        "renderFleetDetail",
        "renderEventsTimeline",
    ):
        assert view in content


def test_app_js_boot_and_route_render():
    content = _read(DASHBOARD / "app.js")
    assert "renderRoute" in content
    assert "onRouteChange" in content or "parseRoute" in content
    assert "listExecutions" in content or "getJSON" in content
    assert "stale" in content.lower()
    assert "offline" in content.lower()
    # No WebSocket / auth / control in foundation
    assert "WebSocket" not in content
    assert "localStorage.setItem" not in content or "token" not in content.lower()


def test_no_scope_leakage_in_foundation():
    """Foundation forbids WebSocket/auth secrets; controls may exist after #58."""
    for path in (
        DASHBOARD / "app.js",
        JS / "api.js",
        JS / "views.js",
        JS / "router.js",
        JS / "models.js",
    ):
        content = _read(path)
        assert "WebSocket" not in content
        assert "new WebSocket" not in content
        # Control helpers may exist after #58; foundation still forbids secrets/shell
        assert "localStorage" not in content
        assert "sessionStorage" not in content


def test_style_responsive_foundation():
    css = _read(DASHBOARD / "style.css")
    assert "@media" in css
    assert "sidebar" in css
    assert "connection-status" in css or "stale" in css


def test_pwa_architecture_doc_exists():
    doc = ROOT / "docs" / "PWA_ARCHITECTURE.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "#56" in text or "Issue" in text
    assert "hash" in text.lower() or "routing" in text.lower()
    assert "Observer" in text
