# Yasin Interface (Phase 4)

**Status:** Phase 4 hardened (#96 + #99 + #101)

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

`validate_ai_config()` returns structured status without secrets.

## Slack confirmation

```text
@Yasin retry execution exec_…
        ↓
Block Kit [Confirm] [Cancel]  (value = token only)
        ↓
identity + SharedState pending (TTL 1h, atomic consume)
        ↓
Control API
```

- Expired tokens cannot execute
- Duplicate confirms are safe (consume + Control API idempotency)
- Unauthorized actors cannot confirm another user's request
- Text `@Yasin confirm <token>` uses the same secure path (no bypass)

## Interactive dedupe

Namespace `slack_interaction_dedupe` on SharedState (TTL 300s).
Control API `control_event_id` remains authoritative for execution.

## Channel adapters

`SlackChannelAdapter` / `CLIChannelAdapter` / `PWAChannelAdapter` all call the same engine path.
