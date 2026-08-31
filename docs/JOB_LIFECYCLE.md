# Production Job Lifecycle (#112)

## States

```text
queued → running → succeeded
                 → failed
                 → cancelled
running → paused → running | cancelled | failed
```

Terminal states (`succeeded`, `failed`, `cancelled`) cannot transition further.

## Durability

Set `YASIN_EXECUTION_STORE_DIR=/path` to persist execution snapshots as JSON files.
On restart the store reloads durable records.

## Recovery

```python
store.recover_stale(max_age_seconds=3600, actor="system-recovery")
```

Marks orphan/stale non-terminal executions as `failed`.

## Audit

Each lifecycle transition records a durable audit event (`lifecycle:<status>`).

## Control API

Retry/re-run create a new execution id (safe re-run). Cancel is idempotent on terminal states.
