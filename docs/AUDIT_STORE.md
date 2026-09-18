# Durable Audit & Event Store (#111)

## Purpose

Persist control-plane audit events across process restarts without turning
SharedState into an audit database.

## Configuration

| Env | Purpose |
|-----|---------|
| `YASIN_AUDIT_BACKEND` | `file` in production; `memory` only when explicitly selected for development/test |
| `YASIN_AUDIT_DIR` | Directory for JSONL audit log; production default `~/.yasinhub/audit` |
| `YASIN_AUDIT_RETENTION_MAX` | Max retained events (default 10000) |

## Record fields

actor, source, policy_decision, action, target, result, outcome, execution_id,
timestamp, correlation_id, external_ids, metadata (secret-redacted).

`target` is canonical and falls back to `execution_id` for normal execution controls.
`result` is canonical and falls back to the legacy `outcome` value for old records.

## Operational HTTP Read Surface

`GET /api/audit` requires a Bearer-authenticated `OPERATOR`, `DEVELOPER`, or `ADMIN` principal.
Supported filters: `actor`, `execution_id`, `action`, `target`, `result`, `since`, and bounded `limit` (1–1000).
The response is served through the existing audit store and therefore retains redaction and retention behavior.
`VIEWER` and unauthenticated callers are rejected.

## Query

```python
from yasinhub.execution.policies import get_policy_engine
get_policy_engine().list_audit(limit=50, actor="alice", execution_id="exec_1")
```

## Security

- Secrets are redacted before persistence
- SharedState is not used as the audit store
- Control API / Policy semantics unchanged

## Compatibility

Existing JSONL records without `target` or `result` are normalized on read using `execution_id`/`external_ids.target` and `outcome`. Existing stored records are not rewritten solely to add these fields.

## Production durability

When `YASIN_AUTH_MODE=production` (or production is inferred from configured auth tokens), audit persistence defaults to the existing `file` backend. Explicit `YASIN_AUDIT_BACKEND=memory` is rejected in production. Startup validates the audit directory before launching the Hub.
