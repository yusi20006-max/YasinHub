"""Tests for authenticated HTTP Agent\u2194Hub transport (#59)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

import pytest

from yasinhub.adapters.agent_runtime import (
    IntegrationContext,
    get_runtime_adapter,
    set_runtime_adapter,
)
from yasinhub.adapters.http_adapter import HttpAgentRuntimeAdapter, build_adapter_from_env
from yasinhub.adapters.http_transport import (
    AuthenticationError,
    ConnectionHealth,
    HttpTransportClient,
    HttpTransportConfig,
    TransportError,
)
from yasinhub.observer.execution_store import InvalidTransitionError


class _FakeAgentHandler(BaseHTTPRequestHandler):
    state: Dict[str, Any] = {}

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send(self, code: int, body: Any = None) -> None:
        payload = b"" if body is None else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _auth_ok(self) -> bool:
        if self.state.get("fail_auth"):
            return False
        auth = self.headers.get("Authorization") or ""
        return auth == f"Bearer {self.state['token']}"

    def do_GET(self) -> None:
        self.state["requests"].append(("GET", self.path, dict(self.headers)))
        if not self._auth_ok():
            self._send(401, {"detail": "unauthorized"})
            return
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/v1/health":
            self._send(200, {"status": "ok"})
            return
        if path == "/v1/executions":
            items = list(self.state["executions"].values())
            if "status" in qs:
                items = [e for e in items if e.get("status") == qs["status"][0]]
            self._send(200, {"items": items})
            return
        if path.startswith("/v1/executions/") and path.endswith("/events"):
            eid = path.split("/")[3]
            events = [e for e in self.state["events"] if e.get("execution_id") == eid]
            self._send(200, {"items": events})
            return
        if path.startswith("/v1/executions/"):
            eid = path.rstrip("/").split("/")[-1]
            if eid in self.state["executions"]:
                self._send(200, self.state["executions"][eid])
            else:
                self._send(404, {"detail": "unknown execution"})
            return
        if path == "/v1/events":
            self._send(200, {"items": list(self.state["events"])})
            return
        if path == "/v1/fleets":
            self._send(200, {"items": list(self.state["fleets"].values())})
            return
        if path.startswith("/v1/fleets/"):
            tid = path.rstrip("/").split("/")[-1]
            if tid in self.state["fleets"]:
                self._send(200, self.state["fleets"][tid])
            else:
                self._send(404, {"detail": "unknown fleet"})
            return
        self._send(404, {"detail": "not found"})

    def do_POST(self) -> None:
        body = self._read_json()
        self.state["requests"].append(("POST", self.path, dict(self.headers), body))
        if not self._auth_ok():
            self._send(401, {"detail": "unauthorized"})
            return
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")

        if len(parts) == 4 and parts[0] == "v1" and parts[1] == "executions":
            eid, action = parts[2], parts[3]
            if eid not in self.state["executions"]:
                self._send(404, {"detail": "unknown execution"})
                return
            ex = dict(self.state["executions"][eid])
            cur = ex.get("status", "running")
            if action == "pause":
                if cur not in ("running", "queued"):
                    self._send(409, {"detail": f"invalid transition: {cur} -> paused", "current": cur, "target": "paused"})
                    return
                ex["status"] = "paused"
            elif action == "resume":
                if cur != "paused":
                    self._send(409, {"detail": f"invalid transition: {cur} -> running", "current": cur, "target": "running"})
                    return
                ex["status"] = "running"
            elif action == "cancel":
                if cur in ("completed", "cancelled", "failed"):
                    self._send(409, {"detail": f"invalid transition: {cur} -> cancelled", "current": cur, "target": "cancelled"})
                    return
                ex["status"] = "cancelled"
            else:
                self._send(404, {"detail": "unknown action"})
                return
            self.state["executions"][eid] = ex
            self._send(200, ex)
            return

        if len(parts) == 4 and parts[0] == "v1" and parts[1] == "fleets" and parts[3] == "cancel":
            tid = parts[2]
            if tid not in self.state["fleets"]:
                self._send(404, {"detail": "unknown fleet"})
                return
            fl = dict(self.state["fleets"][tid])
            fl["status"] = "cancelled"
            self.state["fleets"][tid] = fl
            self._send(200, fl)
            return

        self._send(404, {"detail": "not found"})


@pytest.fixture
def fake_agent():
    _FakeAgentHandler.state = {
        "token": "test-service-token",
        "executions": {
            "ex-1": {
                "execution_id": "ex-1",
                "task_id": "t-1",
                "session_id": "s-1",
                "status": "running",
                "agent_id": "agent-a",
            },
            "ex-2": {
                "execution_id": "ex-2",
                "task_id": "t-1",
                "session_id": "s-1",
                "status": "paused",
                "agent_id": "agent-a",
            },
        },
        "events": [
            {
                "event_id": "evt-1",
                "execution_id": "ex-1",
                "event_type": "status",
                "status": "running",
                "sequence": 1,
                "timestamp": "2026-01-01T00:00:00Z",
            },
            {
                "event_id": "evt-1",
                "execution_id": "ex-1",
                "event_type": "status",
                "status": "running",
                "sequence": 1,
                "timestamp": "2026-01-01T00:00:00Z",
            },
            {
                "event_id": "evt-2",
                "execution_id": "ex-1",
                "event_type": "log",
                "status": "running",
                "sequence": 2,
                "timestamp": "2026-01-01T00:00:01Z",
            },
        ],
        "fleets": {
            "t-1": {
                "task_id": "t-1",
                "status": "running",
                "workers": [],
            }
        },
        "requests": [],
        "fail_auth": False,
    }
    server = HTTPServer(("127.0.0.1", 0), _FakeAgentHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield {
        "base_url": base_url,
        "token": "test-service-token",
        "state": _FakeAgentHandler.state,
        "server": server,
    }
    server.shutdown()


@pytest.fixture
def client(fake_agent):
    cfg = HttpTransportConfig(
        base_url=fake_agent["base_url"],
        service_token=fake_agent["token"],
        timeout_seconds=2.0,
        connect_retries=1,
        stale_after_seconds=60.0,
    )
    return HttpTransportClient(cfg)


@pytest.fixture
def adapter(client):
    return HttpAgentRuntimeAdapter(client)


def test_config_from_env_missing():
    assert HttpTransportConfig.from_env({}) is None
    assert build_adapter_from_env({}) is None


def test_config_from_env_present():
    env = {
        "YASINHUB_AGENT_BASE_URL": "http://agent.example:9000",
        "YASINHUB_AGENT_SERVICE_TOKEN": "secret-token",
        "YASINHUB_AGENT_TIMEOUT": "5",
    }
    cfg = HttpTransportConfig.from_env(env)
    assert cfg is not None
    assert cfg.base_url == "http://agent.example:9000"
    assert cfg.service_token == "secret-token"
    assert cfg.timeout_seconds == 5.0
    ad = build_adapter_from_env(env)
    assert isinstance(ad, HttpAgentRuntimeAdapter)


def test_health_and_bearer_auth(client, fake_agent):
    h = client.check_health()
    assert h.healthy is True
    assert h.last_ok_at is not None
    reqs = [r for r in fake_agent["state"]["requests"] if r[0] == "GET"]
    assert any("Authorization" in r[2] and "Bearer test-service-token" in r[2]["Authorization"] for r in reqs)


def test_auth_failure(client, fake_agent):
    fake_agent["state"]["fail_auth"] = True
    with pytest.raises(AuthenticationError):
        client.get_json("/v1/health")


def test_get_and_list_executions(adapter, fake_agent):
    ex = adapter.get_execution("ex-1")
    assert ex is not None
    assert ex["execution_id"] == "ex-1"
    assert ex["status"] == "running"

    missing = adapter.get_execution("nope")
    assert missing is None

    items = adapter.list_executions(status="running")
    assert any(i["execution_id"] == "ex-1" for i in items)
    assert all(i["status"] == "running" for i in items)


def test_list_events_dedup(adapter):
    events = adapter.list_events(execution_id="ex-1")
    ids = [e.get("event_id") for e in events]
    assert ids.count("evt-1") == 1
    assert "evt-2" in ids


def test_control_pause_resume_cancel(adapter, fake_agent):
    ctx = IntegrationContext(request_id="req-1", actor="hub-integration", source="hub-control")
    out = adapter.pause("ex-1", context=ctx)
    assert out["status"] == "paused"

    out2 = adapter.pause("ex-1", context=ctx)
    assert out2["status"] == "paused"

    ctx2 = IntegrationContext(request_id="req-2", actor="hub-integration")
    out3 = adapter.resume("ex-1", context=ctx2)
    assert out3["status"] == "running"

    ctx3 = IntegrationContext(request_id="req-3", actor="hub-integration")
    out4 = adapter.cancel("ex-1", context=ctx3)
    assert out4["status"] == "cancelled"

    posts = [r for r in fake_agent["state"]["requests"] if r[0] == "POST"]
    assert any("Idempotency-Key" in r[2] for r in posts)
    assert any("X-Request-Id" in r[2] for r in posts)


def test_control_404_and_409(adapter):
    ctx = IntegrationContext(request_id="req-x", actor="hub")
    with pytest.raises(KeyError):
        adapter.pause("missing-ex", context=ctx)

    with pytest.raises(InvalidTransitionError) as ei:
        adapter.pause("ex-2", context=ctx)
    assert ei.value.current == "paused"
    assert ei.value.target == "paused"


def test_fleet_ops(adapter):
    fl = adapter.get_fleet("t-1")
    assert fl is not None
    assert fl["task_id"] == "t-1"
    fleets = adapter.list_fleets()
    assert any(f["task_id"] == "t-1" for f in fleets)

    ctx = IntegrationContext(request_id="req-f", actor="hub")
    cancelled = adapter.cancel_fleet("t-1", context=ctx)
    assert cancelled["status"] == "cancelled"


def test_get_runtime_adapter_selects_http(monkeypatch, fake_agent):
    set_runtime_adapter(None)
    monkeypatch.setenv("YASINHUB_AGENT_BASE_URL", fake_agent["base_url"])
    monkeypatch.setenv("YASINHUB_AGENT_SERVICE_TOKEN", fake_agent["token"])
    import yasinhub.adapters.agent_runtime as ar

    ar._adapter = None
    ad = get_runtime_adapter()
    assert isinstance(ad, HttpAgentRuntimeAdapter)
    set_runtime_adapter(None)
    monkeypatch.delenv("YASINHUB_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("YASINHUB_AGENT_SERVICE_TOKEN", raising=False)
    ar._adapter = None


def test_get_runtime_adapter_fallback_inprocess(monkeypatch):
    set_runtime_adapter(None)
    monkeypatch.delenv("YASINHUB_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("YASINHUB_AGENT_SERVICE_TOKEN", raising=False)
    import yasinhub.adapters.agent_runtime as ar

    ar._adapter = None
    ad = get_runtime_adapter()
    from yasinhub.adapters.agent_runtime import InProcessAgentRuntimeAdapter

    assert isinstance(ad, InProcessAgentRuntimeAdapter)
    set_runtime_adapter(None)
    ar._adapter = None


def test_idempotency_cache_returns_same(client, fake_agent):
    body = {"request_id": "same", "actor": "a", "source": "hub-control"}
    s1, d1 = client.post_json(
        "/v1/executions/ex-1/pause",
        body,
        request_id="same",
        idempotency_key="pause:ex-1:same",
    )
    s2, d2 = client.post_json(
        "/v1/executions/ex-1/pause",
        body,
        request_id="same",
        idempotency_key="pause:ex-1:same",
    )
    assert s1 == s2 == 200
    assert d1 == d2
    posts = [r for r in fake_agent["state"]["requests"] if r[0] == "POST" and "pause" in r[1]]
    keyed = [r for r in posts if r[2].get("Idempotency-Key") == "pause:ex-1:same"]
    assert len(keyed) == 1


def test_connection_health_stale_flag():
    h = ConnectionHealth(healthy=True, last_ok_at=0.0)
    assert h.is_stale(0.001) is True
    h2 = ConnectionHealth(healthy=True, last_ok_at=None)
    assert h2.is_stale(30.0) is True
