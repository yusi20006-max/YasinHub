# Agent ↔ Hub Authenticated HTTP Transport

Issue **#59**.

## Goal

Deployable connectivity between a **separately running** Yasin-Agent runtime and
YasinHub, without rewriting Observer/Control contracts or Agent lifecycle authority.

## Architecture

```text
YasinHub Observer + Control
        │ AgentRuntimeAdapter (interface)
        │
        ├─ InProcessAgentRuntimeAdapter   (#54 default / tests)
        │
        └─ HttpAgentRuntimeAdapter        (#59)
                 │ HttpTransportClient
                 │ Authorization: Bearer <service token>
                 │ X-Request-Id / Idempotency-Key
                 ▼
           Remote Yasin-Agent HTTP surface (/v1/*)
                 │
                 ▼
           Yasin-MCP governance (unchanged)
```

## Enabling HTTP transport

Environment variables (Hub process):

| Variable | Required | Purpose |
|----------|----------|---------|
| `YASINHUB_AGENT_BASE_URL` | yes | Agent base URL, e.g. `https://agent.internal:8443` |
| `YASINHUB_AGENT_SERVICE_TOKEN` | yes | Shared service token (least privilege) |
| `YASINHUB_AGENT_TIMEOUT` | no | Request timeout seconds (default `10`) |
| `YASINHUB_AGENT_RETRIES` | no | Connect/5xx retries (default `2`) |

When both URL and token are set, `get_runtime_adapter()` selects
`HttpAgentRuntimeAdapter`. Otherwise the in-process adapter remains default.

**Never** put the service token in source, frontend, logs, or PWA storage.

## Wire contract (Agent HTTP surface)

Hub client expects (paths relative to base URL):

| Method | Path | Role |
|--------|------|------|
| GET | `/v1/health` | Liveness / readiness |
| GET | `/v1/executions` | List (query: task_id, session_id, status) |
| GET | `/v1/executions/{id}` | Get one |
| GET | `/v1/executions/{id}/events` | Ordered events |
| GET | `/v1/events` | Global event feed |
| POST | `/v1/executions/{id}/pause` | Control |
| POST | `/v1/executions/{id}/resume` | Control |
| POST | `/v1/executions/{id}/cancel` | Control |
| GET | `/v1/fleets` | List fleets |
| GET | `/v1/fleets/{task_id}` | Fleet detail |
| POST | `/v1/fleets/{task_id}/cancel` | Fleet cancel |

Control request body (JSON):

```json
{
  "request_id": "uuid-or-opaque",
  "actor": "integration-scoped-actor",
  "source": "hub-control"
}
```

Headers:

- `Authorization: Bearer <token>`
- `X-Request-Id: <request_id>`
- `Idempotency-Key: <action:resource:request_id>` on mutations

Responses map to existing Hub semantics: **404** unknown, **409** invalid
transition, **401/403** authentication failure.

## Identity and trust

- Service token authenticates **Hub → Agent** service identity.
- Client-supplied PWA `actor` is **not** the authenticated identity.
- `IntegrationContext.actor` is integration-scoped (resolved server-side).
- Audit records include `request_id`, `actor`, action, result — never secrets.

## Idempotency and ordering

- **Control**: client caches responses keyed by `(method, path, Idempotency-Key)`.
  Replays with the same key return the original result without a second mutation
  from Hub’s perspective.
- **Events**: `event_id` is tracked; duplicates are dropped.
- Event lists are sorted by `(sequence, timestamp)` before projection.

## Health, reconnect, stale runtime

- `HttpTransportClient.check_health()` probes `/v1/health`.
- Failures increment `consecutive_failures` and clear `healthy`.
- Transient network / 5xx errors retry with linear backoff.
- `stale` is true when no successful call has occurred within `stale_after_seconds`
  (default 30s). Callers may surface this via operator tooling.

## Security boundaries

- No credentials in repository or PWA.
- No unrestricted shell/filesystem through this transport.
- Yasin-MCP remains the tool governance boundary.
- Agent remains authoritative for lifecycle transitions.

## Replaceability

Observer routes depend only on `AgentRuntimeAdapter`. Switching transport
(in-process ↔ HTTP ↔ future WebSocket/event-bus) does not require rewriting
`/api/executions` or control endpoints.

## Out of scope

- Rewriting Yasin-Agent or Yasin-MCP
- Telegram / Discord
- New unrestricted computer-use capabilities
- Embedding credentials in the frontend
