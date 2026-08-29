"""
tests/test_pwa_integration.py
PWA manifest, service worker, icons, shell, offline/error semantics.
"""

import json
import struct
from pathlib import Path
from unittest.mock import MagicMock

from tests.test_api_server import DummyHandler, MockRequest


def test_pwa_manifest_endpoint():
    req = MockRequest()
    handler = DummyHandler(req, ("127.0.0.1", 12345), MagicMock())
    handler.path = "/dashboard/manifest.json"
    handler.do_GET()

    assert handler.response_code == 200
    assert handler.response_headers.get("Content-Type") == "application/json"

    body = handler.wfile.getvalue().decode("utf-8")
    manifest = json.loads(body)
    assert manifest["name"] == "YasinHub Dashboard"
    assert manifest["short_name"] == "YasinHub"
    assert manifest["start_url"] == "/dashboard/index.html"
    assert manifest["scope"] == "/dashboard/"
    assert manifest["display"] == "standalone"
    assert len(manifest["icons"]) == 2
    assert manifest["icons"][0]["src"] == "/dashboard/icon-192.png"
    assert manifest["icons"][1]["src"] == "/dashboard/icon-512.png"


def test_pwa_service_worker_endpoint():
    req = MockRequest()
    handler = DummyHandler(req, ("127.0.0.1", 12345), MagicMock())
    handler.path = "/dashboard/sw.js"
    handler.do_GET()

    assert handler.response_code == 200
    assert handler.response_headers.get("Content-Type") == "application/javascript"

    body = handler.wfile.getvalue().decode("utf-8")
    assert "CACHE_NAME" in body
    assert "yasinhub-dashboard" in body
    assert "install" in body
    assert "activate" in body
    assert "fetch" in body
    assert "event.waitUntil" in body


def test_pwa_icons_endpoint_and_binary_validation():
    expected_sizes = {"192": (192, 192), "512": (512, 512)}
    for size_str, expected_dim in expected_sizes.items():
        req = MockRequest()
        handler = DummyHandler(req, ("127.0.0.1", 12345), MagicMock())
        handler.path = f"/dashboard/icon-{size_str}.png"
        handler.do_GET()

        assert handler.response_code == 200
        assert handler.response_headers.get("Content-Type") == "image/png"
        data = handler.wfile.getvalue()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert data[12:16] == b"IHDR"
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == expected_dim


def test_pwa_html_shell_endpoint_and_accessibility():
    req = MockRequest()
    handler = DummyHandler(req, ("127.0.0.1", 12345), MagicMock())
    handler.path = "/dashboard/"
    handler.do_GET()

    assert handler.response_code == 200
    assert handler.response_headers.get("Content-Type") == "text/html; charset=utf-8"

    body = handler.wfile.getvalue().decode("utf-8")
    assert "YasinHub" in body
    assert "connection-status" in body
    assert "app.js" in body
    assert 'role="status"' in body
    assert 'aria-live="polite"' in body
    assert 'aria-atomic="true"' in body
    assert 'data-nav="executions"' in body


def test_app_js_containment_of_semantics():
    app_js_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.js"
    content = app_js_path.read_text(encoding="utf-8")
    assert "navigator.onLine" in content
    assert "offline" in content.lower()
    assert "stale" in content.lower()
    assert "renderRoute" in content
    api = Path(__file__).resolve().parents[1] / "dashboard" / "js" / "api.js"
    api_content = api.read_text(encoding="utf-8")
    assert "offline" in api_content
