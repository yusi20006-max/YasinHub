"""
tests/test_pwa_integration.py
تست‌های مربوط به یکپارچگی PWA، مانیفست، سرویس ورکر، آیکون‌ها و معناشناسی وضعیت آفلاین/خطا.
"""

import json
import struct
from unittest.mock import patch, MagicMock
from yasinhub.api.server import YasinHubHandler
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
    assert manifest["lang"] == "fa"
    assert manifest["dir"] == "rtl"
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
    assert "yasinhub-dashboard-v1" in body
    assert "install" in body
    assert "activate" in body
    assert "fetch" in body
    assert "event.waitUntil" in body  # SW runtime cache writes check

def test_pwa_icons_endpoint_and_binary_validation():
    expected_sizes = {
        "192": (192, 192),
        "512": (512, 512)
    }

    for size_str, expected_dim in expected_sizes.items():
        req = MockRequest()
        handler = DummyHandler(req, ("127.0.0.1", 12345), MagicMock())
        handler.path = f"/dashboard/icon-{size_str}.png"
        handler.do_GET()

        assert handler.response_code == 200
        assert handler.response_headers.get("Content-Type") == "image/png"

        data = handler.wfile.getvalue()
        assert len(data) > 0

        # 1. Validate PNG binary signature
        assert data[:8] == b"\x89PNG\r\n\x1a\n", f"icon-{size_str}.png has invalid PNG signature"

        # 2. Validate IHDR chunk presence & correct dimensions
        assert data[12:16] == b"IHDR", f"icon-{size_str}.png missing IHDR chunk"
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == expected_dim, f"icon-{size_str}.png size mismatch: got {width}x{height}, expected {expected_dim}"

def test_pwa_html_shell_endpoint_and_accessibility():
    req = MockRequest()
    handler = DummyHandler(req, ("127.0.0.1", 12345), MagicMock())
    handler.path = "/dashboard/"
    handler.do_GET()

    assert handler.response_code == 200
    assert handler.response_headers.get("Content-Type") == "text/html; charset=utf-8"

    body = handler.wfile.getvalue().decode("utf-8")
    assert "YasinHub Dashboard" in body
    assert "connection-status" in body
    assert "app.js" in body

    # Connection-status accessibility markup check
    assert 'role="status"' in body
    assert 'aria-live="polite"' in body
    assert 'aria-atomic="true"' in body

def test_app_js_containment_of_semantics():
    # Read dashboard/app.js to verify distinct _offline and _error handling
    from pathlib import Path
    app_js_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.js"
    content = app_js_path.read_text(encoding="utf-8")

    # Assert offline and error semantics are kept clean and separate
    assert "navigator.onLine" in content
    assert "_offline" in content
    assert "_error" in content
    assert "آفلاین" in content
    assert "خطای سرور" in content
    assert "alert" in content

    # Assert HTTP 200 + success:false logic is correctly treated
    assert "success === true" in content
    assert "refresh()" in content
