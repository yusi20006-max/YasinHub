"""
tests/test_pwa_integration.py
تست‌های مربوط به یکپارچگی PWA، مانیفست، سرویس ورکر و آیکون‌ها.
"""

import json
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

def test_pwa_icons_endpoint():
    for size in ["192", "512"]:
        req = MockRequest()
        handler = DummyHandler(req, ("127.0.0.1", 12345), MagicMock())
        handler.path = f"/dashboard/icon-{size}.png"
        handler.do_GET()

        assert handler.response_code == 200
        assert handler.response_headers.get("Content-Type") == "image/png"
        assert len(handler.wfile.getvalue()) > 0

def test_pwa_html_shell_endpoint():
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
