# Yasin Interface (Phase 4)

**Status:** Initial implementation (#96)
**Baseline:** Control Plane on `main` including shared state (#93)

## Architecture

```text
Slack / future PWA / CLI
          ↓
   Yasin Interface
  (Session · Intent · Context)
          ↓
       YasinHub
   ┌──────┼──────┐
Memory  Runtime  Integrations
   ↓       ↓          ↓
Core   Agent      GitHub/monday
           ↓
        Yasin-AI
```

Control path:

```text
NL → Intent(CONTROL_REQUEST) → Confirmation → Control API → Policy → Audit → Idempotency → Runtime
```

**Never:** Slack → Yasin-Agent, LLM → shell/code/HTTP, free-form model output as executable ops.

## Implemented

| Capability | Status |
|------------|--------|
| `@Yasin` detection & normalize | implemented |
| Structured intents | implemented |
| Session + shared-state continuity | implemented |
| Context: execution, correlation, reconciliation | implemented |
| Fake / null AI provider | implemented |
| Yasin-Core memory adapter boundary | implemented (optional / null by default) |
| Control via Control API + confirmation | implemented |
| Prompt-injection treated as data | implemented |

## Intent kinds

`READ_STATUS`, `READ_EXECUTION`, `READ_GITHUB`, `READ_MONDAY`, `INVESTIGATE_FAILURE`, `SUMMARIZE`, `CONTROL_REQUEST`, `CONFIRM_CONTROL`, `CANCEL_CONTROL`, `UNKNOWN`

## Confirmation

State-changing NL control requires explicit `@Yasin confirm <token>`.
Plain “yes” / “do it” is **not** authorization.

## Planned / future

- Rich Slack Block Kit confirm buttons bound to tokens
- Deeper GitHub API body retrieval (still data-only)
- Production LLM provider behind `AIProvider` (not in Slack routes)
- Natural-language multi-turn investigation agents via Runtime only
- PWA / CLI channel adapters using the same engine

## Security

- External text is untrusted
- No display-name auth
- Control API remains authoritative
- Secrets redacted from context and answers
