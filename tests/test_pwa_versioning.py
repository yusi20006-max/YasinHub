"""Regression coverage for canonical PWA version/build identity."""

from pathlib import Path

from yasinhub.pwa_version import PWA_VERSION, version_payload

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"


def _read(name: str) -> str:
    return (DASHBOARD / name).read_text(encoding="utf-8")


def test_package_and_pwa_share_canonical_version():
    import yasinhub

    assert yasinhub.__version__ == PWA_VERSION
    assert PWA_VERSION == "1.0.0"


def test_public_version_payload_is_secret_free_and_machine_readable():
    payload = version_payload()
    assert payload["service"] == "YasinHub"
    assert payload["pwa_version"] == PWA_VERSION
    assert isinstance(payload["build"], str)
    assert payload["build"]


def test_pwa_displays_runtime_version_identity():
    html = _read("index.html")
    assert 'id="pwa-version"' in html
    assert "/api/version" in html
    assert "PWA v" in html
    assert "Build" in html


def test_service_worker_cache_identity_is_version_and_build_aware():
    sw = _read("sw.js")
    assert "CACHE_PREFIX = \"yasinhub-dashboard-\"" in sw
    assert "pwa_version" in sw
    assert "build" in sw
    assert "startsWith(CACHE_PREFIX)" in sw
    assert "caches.delete(key)" in sw


def test_service_worker_keeps_live_api_out_of_app_shell_cache():
    sw = _read("sw.js")
    assert 'url.pathname.startsWith("/api/")' in sw
    assert 'status: 503' in sw
