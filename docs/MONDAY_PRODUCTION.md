# monday.com Production Configuration

## Environment variables

| Variable | Required for live | Description |
|----------|-------------------|-------------|
| `YASINHUB_MONDAY_API_TOKEN` | yes | monday GraphQL API token |
| `YASINHUB_MONDAY_SIGNING_SECRET` | recommended | Webhook HMAC secret |
| `YASINHUB_MONDAY_ENABLED` | no | Force-enable integration (`true`/`false`) |
| `YASINHUB_MONDAY_LIVE_WRITES` | yes for writes | Must be `true` to perform GraphQL mutations |
| `YASINHUB_MONDAY_BOARD_IDS` | recommended | Comma-separated board IDs |
| `YASINHUB_MONDAY_STATUS_COLUMN` | yes for writes | Status column ID |
| `YASINHUB_MONDAY_EXECUTION_ID_COLUMN` | optional | Execution ID column |
| `YASINHUB_MONDAY_CORRELATION_COLUMN` | optional | Correlation ID column |
| `YASINHUB_MONDAY_AGENT_COLUMN` | optional | Agent column |
| `YASINHUB_MONDAY_RESULT_COLUMN` | optional | Result column |
| `YASINHUB_MONDAY_GITHUB_ISSUE_COLUMN` | optional | GitHub issue column |
| `YASINHUB_MONDAY_PR_COLUMN` | optional | PR column |
| `YASINHUB_MONDAY_CI_COLUMN` | optional | CI column |
| `YASINHUB_MONDAY_MAX_RETRIES` | no | Default `3` |
| `YASINHUB_MONDAY_RETRY_BACKOFF` | no | Default `0.5` seconds |
| `YASINHUB_MONDAY_TIMEOUT` | no | Default `30` seconds |

## Safe defaults

- Without an API token, the integration stays in **dry-run** mode.
- Without `YASINHUB_MONDAY_LIVE_WRITES=true` and a configured status column, writes are not attempted.
- Secrets never appear in health responses, board items, logs, or audit records.

## Health

```
GET /v1/integrations/monday/health
```

Returns configuration validity, live readiness, and credential presence flags (not values).

## Rollback

1. Unset `YASINHUB_MONDAY_LIVE_WRITES` or set it to `false`.
2. Optionally unset `YASINHUB_MONDAY_API_TOKEN`.
3. Webhook ingress and normalization continue to work; sync pushes become dry-run only.

## Reconciliation

```
POST /v1/integrations/monday/sync
```

Re-pushes Hub execution state to monday for items that originated from monday. Safe to re-run.
