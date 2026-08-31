# Yasin Interface (Phase 4)

**Status:** Phase 4 production path (#96 + #99)

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
| `YASIN_AI_API_KEY` | API key (never commit) |
| `YASIN_AI_BASE_URL` | OpenAI-compatible base URL |
| `YASIN_AI_MODEL` | Model name |
| `YASIN_AI_TIMEOUT` | Seconds (default 15) |

Missing credentials → `NullAIProvider` (system stays healthy).

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

Button value is only the confirmation token. Authorization comes from identity + policy.

## Channel adapters

```python
from yasinhub.interface import get_channel_adapter, ChannelMessage
adapter = get_channel_adapter("cli")
resp = adapter.handle(ChannelMessage(text="status of execution exec_1", channel="cli", source="cli", actor="ops"))
```

## Security

- External text is untrusted
- Control API remains authoritative
- Confirmation one-time via SharedState
- Secrets redacted
