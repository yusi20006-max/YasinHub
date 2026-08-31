# Durable Audit & Event Store (#111)

## Purpose

Persist control-plane audit events across process restarts without turning
SharedState into an audit database.

## Configuration

| Env | Purpose |
|-----|---------|
| `YASIN_AUDIT_BACKEND` | `memory` (default) or `file` |
| `YASIN_AUDIT_DIR` | Directory for JSONL audit log when backend=`file` |
| `YASIN_AUDIT_RETENTION_MAX` | Max retained events (default 10000) |

## Record fields

actor, source, policy_decision, action, target (`execution_id`), result (`outcome`),
timestamp, correlation_id, external_ids, metadata (secret-redacted).

## Query

```python
from yasinhub.execution.policies import get_policy_engine
get_policy_engine().list_audit(limit=50, actor="alice", execution_id="exec_1")
```

## Security

- Secrets are redacted before persistence
- SharedState is not used as the audit store
- Control API / Policy semantics unchanged
