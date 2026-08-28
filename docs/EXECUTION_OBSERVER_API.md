# Execution Observer + Fleet + Control Plane API

YasinHub Issues **#50**, **#51**, **#52**.

## Architecture

```
YasinHub          — Observer API, Fleet data layer, Control plane
    ↓
Yasin-Agent       — Execution lifecycle, multi-agent harness, worker fleet (#26–#28)
    ↓
Yasin-MCP         — Tool governance / authorization
```

YasinHub does **not** implement an execution engine, grant capabilities, share credentials, or bypass Yasin-MCP.

## Issue #50 — Execution Observer API

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/executions` | List executions (`task_id`, `session_id`, `status` query filters) |
| GET | `/api/executions/{execution_id}` | Single execution snapshot |
| GET | `/api/executions/{execution_id}/events` | Structured events for one execution |
| GET | `/api/execution-events` | Query events (`execution_id`, `task_id`, `session_id`, `worker_id`, `event_type`, `limit`) |

### Execution snapshot fields

`execution_id`, `task_id`, `session_id`, `agent_id`, `workspace`, `capabilities` (sorted), `status`, timestamps, `error`, `result`, `metadata`, `history`, `cancel_requested`.

### Guarantees

- **No secrets** in responses (key/pattern redaction).
- **Deterministic** JSON (`sort_keys`, sorted capabilities, ordered history/events by sequence).
- Unknown execution → **404**.

### Lifecycle states

`queued` → `running` ↔ `paused` → `succeeded` | `failed` | `cancelled`

## Issue #51 — Fleet / Worker Dashboard Data Layer

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/fleets` | List parent/fleet snapshots |
| GET | `/api/fleets/{task_id}` | One fleet with ordered workers |

### Structure

```
Parent Task (task_id)
  └── Worker (worker_id)
        ├── role, objective, status, progress
        ├── execution_id, session_id
        ├── result / failure / cancellation_state
```

Workers are always ordered by `worker_id`.

### Fleet aggregation (deterministic)

| Worker set | Fleet status |
|------------|--------------|
| all succeeded | `succeeded` |
| any failed + any succeeded/cancelled | `completed_with_failures` |
| all failed | `failed` |
| all cancelled | `cancelled` |
| any running/queued/paused | `running` (or `cancelling` while cancel propagates) |

Events correlate: **parent → worker → session → execution** via `task_id`, `worker_id`, `session_id`, `execution_id`.

## Issue #52 — Control Plane

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/executions/{id}/pause` | Cooperative pause (only from `running`) |
| POST | `/api/executions/{id}/resume` | Resume (only from `paused`) |
| POST | `/api/executions/{id}/cancel` | Cancel non-terminal execution |
| POST | `/api/fleets/{task_id}/cancel` | Propagate cancel to workers |

### Request body (optional JSON)

```json
{ "actor": "pwa-user", "request_id": "optional-correlation-id" }
```

### Responses

- **200** — action applied; returns updated `execution` or `fleet`.
- **400** — malformed body.
- **404** — unknown execution/fleet.
- **409** — invalid transition (`error: "invalid transition"`, `current`, `target`).

Control events include `actor` / `request_id` for audit and never contain secrets.

Parent cancellation sets worker `cancellation_state` and cancels linked non-terminal executions.

## Out of scope

Telegram, Discord, unrestricted shell/filesystem, computer-use, credential sharing, MCP redesign, new privilege grants.
