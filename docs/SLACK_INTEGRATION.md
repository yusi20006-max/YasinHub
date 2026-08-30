# Slack Integration (Foundation)

**Status:** Implemented foundation (#70). Commands, notifications, and interactive controls are layered in subsequent issues.

**Architecture reference:** `YASIN-DOCS/docs/architecture/YASIN_SLACK_INTEGRATION.md`

## Principle

Slack is an **operational interface**. YasinHub remains the Control Plane and source of truth. Slack never talks directly to Yasin-Agent.

```text
Slack Event
  → Verification (HMAC signature + timestamp)
  → Slack Adapter
  → Normalized SlackInboundEvent
  → YasinHub control surfaces
  → ExecutionRuntime / Observer
  → Yasin-Agent
```

Outbound:

```text
YasinHub event
  → Slack Adapter
  → Slack Web API (best-effort)
```

## Configuration (environment)

| Variable | Purpose |
|---|---|
| `YASIN_SLACK_ENABLED` | Explicit enable (`true`/`false`). Auto-enables when bot token + signing secret are set. |
| `YASIN_SLACK_BOT_TOKEN` | Bot User OAuth token (`xoxb-...`) |
| `YASIN_SLACK_SIGNING_SECRET` | App signing secret for request verification |
| `YASIN_SLACK_APP_TOKEN` | Optional app-level token |
| `YASIN_SLACK_DEFAULT_CHANNEL` | Default channel (default `#yasin`) |
| `YASIN_SLACK_ALERTS_CHANNEL` | Alerts channel (default `#yasin-alerts`) |
| `YASIN_SLACK_AGENT_CHANNEL` | Agent/execution channel (default `#yasin-agent`) |
| `YASIN_SLACK_FEATURE_COMMANDS` | Feature flag (default true) |
| `YASIN_SLACK_FEATURE_NOTIFICATIONS` | Feature flag (default true) |
| `YASIN_SLACK_FEATURE_INTERACTIVE` | Feature flag (default true) |
| `YASIN_SLACK_TIMESTAMP_MAX_AGE` | Replay window in seconds (default 300) |

Slack is **optional**. Without credentials, YasinHub runs normally and Slack routes return `503`.

## HTTP routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/integrations/slack/health` | Safe health / config summary (secrets redacted) |
| `POST` | `/api/integrations/slack/events` | Events API + URL verification |
| `POST` | `/api/integrations/slack/commands` | Slash commands (handler expands in #71) |
| `POST` | `/api/integrations/slack/interactions` | Interactive components (handler expands in #73) |

All `POST` routes require a valid `X-Slack-Signature` and `X-Slack-Request-Timestamp`.

## Package layout

```text
yasinhub/integrations/slack/
├── __init__.py
├── config.py         # env config
├── verification.py   # HMAC + replay protection
├── client.py         # outbound Slack Web API + Null client
├── events.py         # inbound normalization
└── adapter.py        # facade used by routes

yasinhub/api/slack_routes.py
```

## Security

- Request signature verification (HMAC-SHA256, `v0` scheme).
- Timestamp skew / replay rejection.
- Secrets never appear in health payloads or structured logs.
- Invalid signatures → `401`.
- Disabled integration → `503` (does not crash the process).
- Outbound failures are isolated; they must not fail Yasin executions.

## Local testing

```bash
python -m pytest tests/test_slack_foundation.py -q
python -m pytest -q
```

## Implemented vs planned

| Capability | Status |
|---|---|
| Config + optional enable | Implemented (#70) |
| Signature verification | Implemented (#70) |
| Event normalization | Implemented (#70) |
| Outbound client abstraction | Implemented (#70) |
| Health route | Implemented (#70) |
| Slash commands + authz | Planned (#71) |
| Lifecycle notifications + threads | Planned (#72) |
| Interactive buttons | Planned (#73) |
