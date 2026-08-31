# Yasin Interface (Phase 4)

**Status:** Phase 4 production path (#96 + #99 + #101 + #105 + #109 + #110)

## Architecture

```text
ChannelAdapter (Slack / CLI / PWA)
          ↓
   Yasin Interface Engine
  (Session · Intent · Context)
          ↓
       YasinHub Control API
```

All three channel adapters use the same `YasinInterface.handle(...)` path. Adapters do not implement provider, session, context, or control-policy logic.

## Production AI Provider

| Env | Purpose |
|-----|---------|
| `YASIN_AI_PROVIDER` | `fake` \| `null` \| `openai` \| `http` \| `openai_compatible` |
| `YASIN_AI_API_KEY` | API key (never commit or log) |
| `YASIN_AI_BASE_URL` | Absolute HTTP(S) OpenAI-compatible API root; no URL credentials/query/fragment |
| `YASIN_AI_MODEL` | Non-empty model name |
| `YASIN_AI_TIMEOUT` | Seconds; default 15, maximum 120 |

Production configuration is validated before an HTTP provider is constructed. Invalid provider/base URL/model/timeout configuration, or missing credentials, degrades to `NullAIProvider` without exposing secrets. Direct `HttpAIProvider` construction rejects invalid configuration with `ValueError`.

HTTP failures, timeouts, malformed/empty responses, and unavailable endpoints return controlled `AICompletion` errors; provider credentials are never included in logs or user-facing error text. OpenAI-compatible endpoints use the single HTTP provider path rather than vendor-specific integrations.


## Production AI runtime (#110)

- `sanitize_ai_context` bounds and redacts context before any provider call.
- Actor / source / session / intent metadata may be included; credentials and raw headers never are.
- `cancel_requested` in context short-circuits the provider (no network call).
- `ai_runtime_status()` exposes non-secret readiness for operations.
- Missing or invalid credentials degrade to `NullAIProvider`; Control API is never bypassed.
- Model output cannot execute shell, code, HTTP, or privileged operations.

## Slack confirmation UX

```text
@Yasin retry execution exec_1842
        ↓
control proposal + Block Kit [Confirm] [Cancel]
        ↓
identity + shared pending token validation
        ↓
Control API
```

Button value is only the confirmation token. Authorization comes from identity + policy. Pending confirmation state is shared, so workers do not maintain independent confirmation truth. Expired/consumed tokens cannot execute, and Control API `control_event_id` idempotency remains authoritative.

Legacy text confirmation cannot bypass the pending-token validation path.

## Interactive deduplication

Slack interactive duplicate detection uses the existing `SharedState` abstraction with an atomic `try_acquire` operation and a bounded TTL. There is no second persistence implementation. If the shared-state backend is temporarily unavailable, the deduper **fails closed**: interactive actions are refused and no mutating path is entered. Control API `control_event_id` idempotency remains an additional authoritative boundary when SharedState is healthy.

## Channel adapters

```python
from yasinhub.interface import get_channel_adapter, ChannelMessage
adapter = get_channel_adapter("cli")
resp = adapter.handle(ChannelMessage(text="status of execution exec_1", channel="cli", source="cli", actor="ops"))
```

Slack, CLI, and PWA all route through the same interface engine; no channel duplicates intent parsing, session handling, context gathering, or AI-provider selection.

## Security

- External text is untrusted
- Identity-based authorization remains default-deny
- Slack HMAC/replay protection remains upstream of interactive handling
- Control API remains the only control boundary for mutations
- Confirmation state is one-time and SharedState-backed
- Interactive dedupe is atomic and shared across workers
- Secrets are redacted and never logged
- No direct Agent execution is introduced
