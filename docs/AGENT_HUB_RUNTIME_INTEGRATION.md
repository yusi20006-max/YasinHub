# Yasin-Agent ↔ YasinHub Runtime Integration

Issue **#54**.

## Architecture

```text
YasinHub
  Observer + Control Plane
          │
          │ Integration Adapter  (transport-agnostic)
          │
          ▼
Yasin-Agent
  ExecutionRuntime
  CollaborationHarness
  WorkerFleet
          │
          ▼
Yasin-MCP
  Governance / Authorization
```

### Authority

| Concern | Owner |
|---------|--------|
| Execution lifecycle / state machine | **Yasin-Agent** |
| Tool governance / authorization | **Yasin-MCP** |
| Observation, projection, control API surface | **YasinHub** |

YasinHub **must not**:

- implement a second execution state machine
- grant capabilities or share credentials
- bypass Yasin-MCP
- expose unrestricted shell / filesystem access

## Integration Adapter

Module: `yasinhub.adapters.agent_runtime`

### Interface

```python
class AgentRuntimeAdapter:
    def get_execution(execution_id) -> Optional[dict]
    def list_executions(...) -> list[dict]
    def list_events(...) -> list[dict]
    def pause(execution_id, *, context: IntegrationContext) -> dict
    def resume(execution_id, *, context: IntegrationContext) -> dict
    def cancel(execution_id, *, context: IntegrationContext) -> dict
    def cancel_fleet(task_id, *, context: IntegrationContext) -> dict
    def get_fleet(task_id) -> Optional[dict]
    def list_fleets() -> list[dict]
```

### Default implementation

`InProcessAgentRuntimeAdapter`:

- When bound to a real Agent `ExecutionRuntime` / `WorkerFleet`, control commands
  are forwarded to Agent and state is projected into the Hub Observer store.
- When unbound (tests / standalone Hub), control falls back to the local
  Observer store so existing #50/#51/#52 contracts remain green.
- Event ingestion is idempotent on `event_id` and order-preserving by sequence.

### Binding

```python
from yasinhub.adapters.agent_runtime import bind_agent_runtime

adapter = bind_agent_runtime(runtime=agent_runtime, fleet=worker_fleet)
```

### Transport boundary

The adapter is intentionally transport-agnostic. Future transports may include:

- in-process (current default)
- HTTP
- WebSocket
- event bus / message queue
- MCP bridge

Observer HTTP routes must not be rewritten when the transport changes.

## Control bridge

| Hub endpoint | Adapter method | Agent target |
|--------------|----------------|--------------|
| `POST /api/executions/{id}/pause` | `pause` | `ExecutionRuntime.pause` |
| `POST /api/executions/{id}/resume` | `resume` | `ExecutionRuntime.resume` |
| `POST /api/executions/{id}/cancel` | `cancel` | `ExecutionRuntime.cancel` |
| `POST /api/fleets/{task_id}/cancel` | `cancel_fleet` | `WorkerFleet.cancel` / harness cancel |

Invalid transitions → **409**. Unknown execution/fleet → **404**. Malformed body → **400**.

## Identity / audit boundary

- Client-supplied `actor` is **not** trusted as authenticated identity.
- `IntegrationContext` carries `request_id`, authenticated `actor` (integration-scoped), and optional `actor_hint`.
- Audit records include: `request_id`, `actor`, `execution_id` / `task_id` / `worker_id`, `timestamp`, `action`, `result`.
- Secrets (tokens, passwords, API keys, credentials) are never persisted or emitted in events, responses, or logs.

## Event ingestion

Agent events are projected into the existing Observer:

- Fields preserved: `execution_id`, `task_id`, `session_id`, `agent_id`, `worker_id`, `event_type`, `status`, `sequence`, `timestamp`, non-sensitive metadata.
- Duplicate `event_id` → ignored.
- Out-of-order events do not corrupt projected state; authoritative re-sync via `get_execution` is preferred when bound.

## Fleet correlation

```text
parent task (task_id)
  ├── worker A → execution A (session A)
  ├── worker B → execution B (session B)
  └── worker C → execution C (session C)
```

Sessions and executions remain independent. Aggregation is deterministic (same rules as #51). Partial failure and cancellation propagation are preserved.

## Backward compatibility

- #50 Observer APIs unchanged
- #51 Fleet APIs unchanged
- #52 Control response contracts unchanged
- Existing tests remain green when no external runtime is bound

## Out of scope

PWA UI, Telegram, Discord, new execution engine, MCP governance changes, unrestricted shell/filesystem, credential sharing between workers.
