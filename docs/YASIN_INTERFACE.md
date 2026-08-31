# Yasin Interface (Phase 4)

**Status:** Phase 4 hardened (#96 + #99 + #101 + #105)

## Architecture

```text
ChannelAdapter (Slack / CLI / PWA)
          ↓
   Yasin Interface Engine
  (Session · Intent · Context)
          ↓
       YasinHub Control API
```

## Production AI Provider

| Env | Purpose |
|-----|---------|
| `YASIN_AI_PROVIDER` | `fake` \| `null` \| `openai` \| `http` |
| `YASIN_AI_API_KEY` | API key (never commit / never logged) |
| `YASIN_AI_BASE_URL` | Must be `http://` or `https://` |
| `YASIN_AI_MODEL` | Model name (no whitespace) |
| `YASIN_AI_TIMEOUT` | 1–120 seconds (default 15) |

Invalid base URL / model → NullAIProvider.
Missing credentials → NullAIProvider (system stays healthy).

## Slack confirmation

Block Kit [Confirm] [Cancel] and text `@Yasin confirm <token>` share the same path:
identity + SharedState pending (TTL 1h, atomic consume) → Control API.

## PWA conversational surface (#105)

- Route: `POST /api/interface/chat`
- Channel: `pwa` via `PWAChannelAdapter` → same Interface Engine
- Session continuity via `client_session_id` / `thread_id`
- Confirmations use the same pending token, expiry, CAS consume, and Control API path as Slack

## Interactive dedupe (#105)

Namespace `yasin_slack_interaction_dedupe` (SharedState).

For **sensitive** actions (`yasin_confirm`, `yasin_cancel`, `cancel`, `retry`):
if SharedState is unavailable, the interaction **fails closed** (user must retry).
Control API `control_event_id` remains the final execution boundary.

## Channel adapters

`SlackChannelAdapter` / `CLIChannelAdapter` / `PWAChannelAdapter` all call the same engine path.
